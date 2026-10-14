"""Tracker-owned persistent jobs with a global five-job lease limit."""
import asyncio
from datetime import timedelta, timezone
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app import invalidation, work
from app.applications import ApplicationNotFound, InvalidApplication, get_application
from app.followup_templates import RevisionConflict
from app.models import Application, ApplicationStatus, FollowUp, FollowUpChannel, FollowUpStatus, RecipientCandidate, RecipientDiscovery, utc_now
from app.work_schemas import FollowUpUpdate

LIMIT=5
ACTIVE=('QUEUED','RUNNING')


def context(application):
    return {'company':application.company,'job_title':application.job_title}


def eligible(application):
    return application and not application.deleted_at and application.status != ApplicationStatus.CLOSED and application.outcome is None


def missing_query():
    return select(FollowUp).join(Application).where(Application.deleted_at.is_(None),Application.status != ApplicationStatus.CLOSED,
        Application.outcome.is_(None),FollowUp.status != FollowUpStatus.SENT,FollowUp.archived_at.is_(None),
        FollowUp.channel != FollowUpChannel.PHONE,func.length(func.trim(func.coalesce(FollowUp.recipient_email,''))) == 0)


def queue_locked(session,application):
    job=session.scalar(select(RecipientDiscovery).where(RecipientDiscovery.application_id == application.id))
    if job and job.state in ACTIVE:
        return job,False
    if job is None:
        job=RecipientDiscovery(application_id=application.id)
        session.add(job)
    job.state='QUEUED'
    job.context=context(application)
    job.requested_at=utc_now()
    job.started_at=job.completed_at=job.lease_until=job.lease_id=job.error=None
    job.warnings=[]
    return job,True


def enqueue(session,application_id):
    session.execute(text('BEGIN IMMEDIATE'))
    application=get_application(session,application_id)
    if not eligible(application):
        raise InvalidApplication('Recipient searches require an open application')
    job,_=queue_locked(session,application)
    session.commit()
    return job_read(job)


def enqueue_missing(session):
    session.execute(text('BEGIN IMMEDIATE'))
    ids=session.scalars(missing_query().with_only_columns(FollowUp.application_id).distinct()).all()
    count=0
    for application_id in ids:
        _,created=queue_locked(session,session.get(Application,application_id))
        count+=int(created)
    session.commit()
    return {'queued':count,'applications':len(ids),'concurrency_limit':LIMIT}


def job_read(job):
    if not job:
        return None
    return {'id':job.id,'state':job.state,'requested_at':job.requested_at.replace(tzinfo=timezone.utc),
        'started_at':job.started_at.replace(tzinfo=timezone.utc) if job.started_at else None,
        'completed_at':job.completed_at.replace(tzinfo=timezone.utc) if job.completed_at else None,
        'attempts':job.attempts,'error':job.error,'warnings':job.warnings}


def application_state(session,application_id):
    app=get_application(session,application_id)
    candidates=session.scalars(select(RecipientCandidate).where(RecipientCandidate.application_id == application_id).order_by(RecipientCandidate.created_at,RecipientCandidate.id))
    followups=session.scalars(select(FollowUp).where(FollowUp.application_id == application_id,FollowUp.channel != FollowUpChannel.PHONE,
        FollowUp.status != FollowUpStatus.SENT,FollowUp.archived_at.is_(None)).order_by(FollowUp.sequence_number))
    return {'job':job_read(session.scalar(select(RecipientDiscovery).where(RecipientDiscovery.application_id == application_id))),
        'followups':[{'id':f.id,'sequence_number':f.sequence_number,'revision':f.revision,'recipient_email':f.recipient_email,'recipient_name':f.recipient_name} for f in followups],
        'candidates':[{'id':c.id,**c.value,'context_current':c.context == context(app)} for c in candidates],
        'missing_followups':session.scalar(select(func.count()).select_from(missing_query().where(FollowUp.application_id == application_id).subquery())) or 0}


def queue_state(session):
    counts=dict(session.execute(select(RecipientDiscovery.state,func.count()).group_by(RecipientDiscovery.state)).all())
    return {'queued':counts.get('QUEUED',0),'running':counts.get('RUNNING',0),'failed':counts.get('FAILED',0),
        'missing_followups':session.scalar(select(func.count()).select_from(missing_query().subquery())) or 0,'concurrency_limit':LIMIT}


def claim(engine,stopping=None):
    with Session(engine) as session:
        session.execute(text('BEGIN IMMEDIATE'))
        if stopping is not None and stopping.is_set():
            session.rollback()
            return None
        now=utc_now()
        for expired in session.scalars(select(RecipientDiscovery).where(RecipientDiscovery.state=='RUNNING',RecipientDiscovery.lease_until <= now)):
            expired.state='QUEUED'
            expired.lease_id=expired.lease_until=None
        session.flush()
        running=session.scalar(select(func.count()).select_from(RecipientDiscovery).where(RecipientDiscovery.state=='RUNNING')) or 0
        if running >= LIMIT:
            session.commit()
            return None
        for job in session.scalars(select(RecipientDiscovery).where(RecipientDiscovery.state=='QUEUED').order_by(RecipientDiscovery.requested_at,RecipientDiscovery.id)):
            app=session.get(Application,job.application_id)
            if not eligible(app) or context(app) != job.context:
                job.state='CANCELLED'
                job.error='Application closed or changed; request a new search if needed.'
                job.completed_at=now
                continue
            job.state='RUNNING'
            job.lease_id=str(uuid4())
            job.lease_until=now+timedelta(seconds=180)
            job.started_at=now
            job.attempts+=1
            result={'id':job.id,'lease_id':job.lease_id,'application_id':job.application_id,'context':dict(job.context)}
            session.commit()
            invalidation.publish(session,'recipient.updated',job.application_id)
            return result
        session.commit()
        return None


def complete(engine,claimed,result=None,error=None,requeue=False):
    with Session(engine) as session:
        session.execute(text('BEGIN IMMEDIATE'))
        job=session.get(RecipientDiscovery,claimed['id'])
        if not job or job.state != 'RUNNING' or job.lease_id != claimed['lease_id']:
            return False
        app=session.get(Application,job.application_id)
        if not eligible(app) or context(app) != job.context:
            job.state='CANCELLED'
            job.error='Application changed; old discovery results were discarded.'
        elif requeue:
            job.state='QUEUED'
        elif error:
            job.state='FAILED'
            job.error=error[:500]
        else:
            job.state=result.get('outcome','COMPLETED')
            job.warnings=result.get('warnings',[])[:20]
            session.execute(delete(RecipientCandidate).where(RecipientCandidate.application_id == job.application_id))
            for value in result.get('candidates',[])[:30]:
                session.add(RecipientCandidate(application_id=job.application_id,context=dict(job.context),value=value))
        job.lease_id=job.lease_until=None
        job.completed_at=None if job.state == 'QUEUED' else utc_now()
        session.commit()
        invalidation.publish(session,'recipient.updated',job.application_id)
        return True


def choose(session,application_id,followup_id,candidate_id,revision,settings):
    session.execute(text('BEGIN IMMEDIATE'))
    candidate=session.get(RecipientCandidate,candidate_id)
    app=get_application(session,application_id)
    if not candidate or candidate.application_id != application_id:
        raise ApplicationNotFound('Recipient candidate not found for this application')
    if candidate.context != context(app):
        raise RevisionConflict('The job changed since discovery. Fetch recipients again.')
    if not candidate.value.get('email'):
        raise InvalidApplication('No published email was found for this person. Enter a confirmed address manually.')
    if not eligible(app):
        raise InvalidApplication('Reopen the application before choosing a recipient')
    item=work.update_followup(session,application_id,followup_id,
        FollowUpUpdate(recipient_email=candidate.value['email'],recipient_name=candidate.value.get('name'),
                       recipient_source_url=candidate.value['source_url'],expected_revision=revision),settings=settings,commit=False)
    return work.finish(session,item)


class RecipientScheduler:
    def __init__(self,engine,settings,researcher=None):
        self.engine=engine
        self.stop=asyncio.Event()
        self.tasks=[]
        self.researcher=researcher
        self.available=True
        if researcher is None:
            try:
                from app.recipient_research import PublicRecipientResearch
                self.researcher=PublicRecipientResearch(settings.app_data_dir/'recipient-web-cache.sqlite3')
            except ImportError:
                self.available=False

    def start(self):
        if self.available:
            self.tasks=[asyncio.create_task(self.worker()) for _ in range(LIMIT)]

    async def close(self):
        self.stop.set()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        if self.researcher and hasattr(self.researcher,'close'):
            await self.researcher.close()

    async def worker(self):
        while not self.stop.is_set():
            claim_task=asyncio.create_task(asyncio.to_thread(claim,self.engine,self.stop))
            try:
                claimed=await asyncio.shield(claim_task)
            except asyncio.CancelledError:
                # Cancelling an asyncio future cannot stop the SQLite thread.
                # Wait for its claim and release that lease before closing.
                claimed=await claim_task
                if claimed:
                    await asyncio.to_thread(complete,self.engine,claimed,requeue=True)
                raise
            if not claimed:
                try:
                    await asyncio.wait_for(self.stop.wait(),timeout=1)
                except TimeoutError:
                    pass
                continue
            try:
                result=await asyncio.wait_for(self.researcher.discover(claimed['context']),timeout=120)
                await asyncio.to_thread(complete,self.engine,claimed,result)
            except asyncio.CancelledError:
                await asyncio.to_thread(complete,self.engine,claimed,requeue=True)
                raise
            except Exception as exc:
                await asyncio.to_thread(complete,self.engine,claimed,error=f'Discovery failed ({type(exc).__name__}). Retry or enter a recipient manually.')
