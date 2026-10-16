import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
import time

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app import recipient_discovery as discovery
from app.models import FollowUp, RecipientCandidate, RecipientDiscovery, utc_now
from app.recipient_research import adapt_candidate, matches_company, usable_url


def application(client,**changes):
    response=client.post('/api/applications',json={'company':'Example','job_title':'Engineer','date_applied':'2026-10-01','email_reference':'message-123',**changes})
    assert response.status_code == 201,response.text
    return response.json()


def followup(client,app):
    return client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]


def pause(client):
    client.portal.call(client.app.state.recipient_jobs.close)


def test_missing_filter_inheritance_manual_choice_and_draft_guard(client):
    app=application(client)
    item=followup(client,app)
    url=f"/api/applications/{app['id']}/followups/{item['id']}"
    assert client.get('/api/followups?recipient=missing').json()['total'] == 1
    assert client.get('/api/recipients/queue').json()['missing_followups'] == 1
    client.patch(url,json={'body':'Hello','status':'READY'})
    changed=client.patch(url,json={'recipient_email':'recruiter@example.com','recipient_name':'Recruiter','expected_revision':2})
    assert changed.status_code == 200,changed.text
    assert changed.json()['status'] == 'PREPARED' and changed.json()['approved_revision'] is None
    assert client.get('/api/followups?recipient=missing').json()['total'] == 0
    assert client.get('/api/followups?recipient=assigned').json()['total'] == 1
    inherited=client.post(f"/api/applications/{app['id']}/followups",json={}).json()
    assert inherited['recipient_email'] == 'recruiter@example.com'
    assert client.patch(url,json={'recipient_email':'not-an-email'}).status_code == 422
    assert client.get('/api/followups?recipient=bad').status_code == 422
    assert client.get(url+'/ai-request').json()['recipient']['email'] == 'recruiter@example.com'


def test_bulk_queue_deduplicates_by_job_and_excludes_phone_closed_sent_and_archived(client):
    pause(client)
    app=application(client)
    client.post(f"/api/applications/{app['id']}/followups",json={})
    application(client,contact_email='known@example.com')
    phone=application(client,phone_number='+33612345678',contact_type='PHONE')
    closed=application(client)
    client.patch(f"/api/applications/{closed['id']}",json={'status':'CLOSED','outcome':'UNSUCCESSFUL'})
    archived=application(client)
    record=followup(client,archived)
    client.patch(f"/api/applications/{archived['id']}/followups/{record['id']}",json={'archived':True})
    result=client.post('/api/recipients/queue-missing').json()
    assert result == {'queued':1,'applications':1,'concurrency_limit':5}
    assert client.post('/api/recipients/queue-missing').json()['queued'] == 0
    assert client.post(f"/api/applications/{closed['id']}/recipients/fetch").status_code == 422
    assert client.get('/api/recipients/queue').json()['missing_followups'] == 2


def test_claims_are_globally_limited_and_expired_work_recovers(client):
    pause(client)
    for _ in range(9): application(client)
    client.post('/api/recipients/queue-missing')
    engine=client.app.state.engine
    with ThreadPoolExecutor(max_workers=10) as pool:
        claimed=list(pool.map(lambda _:discovery.claim(engine),range(10)))
    assert sum(c is not None for c in claimed) == 5
    assert client.get('/api/recipients/queue').json()['running'] == 5
    assert client.get('/api/recipients/queue').json()['queued'] == 4
    old=next(c for c in claimed if c)
    with Session(engine) as session:
        session.get(RecipientDiscovery,old['id']).lease_until=utc_now()-timedelta(seconds=1)
        session.commit()
    recovered=discovery.claim(engine)
    assert recovered
    assert not discovery.complete(engine,old,{'candidates':[],'outcome':'COMPLETED'})
    assert client.get('/api/recipients/queue').json()['running'] == 5


def test_stale_job_results_are_discarded_and_selection_is_scoped_revision_checked(client):
    pause(client)
    app=application(client)
    item=followup(client,app)
    url=f"/api/applications/{app['id']}/followups/{item['id']}"
    client.post(f"/api/applications/{app['id']}/recipients/fetch")
    claimed=discovery.claim(client.app.state.engine)
    client.patch(f"/api/applications/{app['id']}",json={'company':'Changed'})
    assert discovery.complete(client.app.state.engine,claimed,{'candidates':[{'email':'old@example.com'}],'outcome':'COMPLETED'})
    assert client.get(f"/api/applications/{app['id']}/recipients").json()['candidates'] == []
    client.post(f"/api/applications/{app['id']}/recipients/fetch")
    claimed=discovery.claim(client.app.state.engine)
    discovery.complete(client.app.state.engine,claimed,{'candidates':[{'email':'hr@example.com','name':'HR','source_url':'https://example.com/careers'}],'outcome':'COMPLETED'})
    candidate=client.get(f"/api/applications/{app['id']}/recipients").json()['candidates'][0]
    other=application(client)
    other_item=followup(client,other)
    assert client.post(f"/api/applications/{other['id']}/followups/{other_item['id']}/recipient",json={'candidate_id':candidate['id'],'expected_revision':1}).status_code == 404
    assert client.post(url+'/recipient',json={'candidate_id':candidate['id'],'expected_revision':99}).status_code == 409
    selected=client.post(url+'/recipient',json={'candidate_id':candidate['id'],'expected_revision':1})
    assert selected.status_code == 200,selected.text
    assert selected.json()['recipient_email'] == 'hr@example.com'
    assert selected.json()['recipient_source_url'] == 'https://example.com/careers'
    manual=client.patch(url,json={'recipient_email':'manual@example.com','expected_revision':2}).json()
    assert manual['recipient_source_url'] is None


class GateResearch:
    def __init__(self):
        self.gate=asyncio.Event()
        self.five_started=Event()
        self.active=0
        self.peak=0

    async def discover(self,context):
        self.active+=1
        self.peak=max(self.peak,self.active)
        if self.active == 5:self.five_started.set()
        try:
            await self.gate.wait()
            return {'candidates':[],'warnings':[],'outcome':'NO_RESULTS'}
        finally:
            self.active-=1


def test_background_workers_process_five_at_a_time_and_drain_queue(tmp_path):
    researcher=GateResearch()
    with TestClient(create_app(Settings(app_data_dir=tmp_path,_env_file=None),recipient_researcher=researcher)) as client:
        for _ in range(8):application(client)
        assert client.post('/api/recipients/queue-missing').json()['queued'] == 8
        assert researcher.five_started.wait(4)
        queue=client.get('/api/recipients/queue').json()
        assert queue['running'] == 5 and queue['queued'] == 3
        assert researcher.peak == 5
        client.portal.call(researcher.gate.set)
        until=time.monotonic()+5
        while time.monotonic() < until:
            queue=client.get('/api/recipients/queue').json()
            if queue['running'] == queue['queued'] == 0:break
            time.sleep(.02)
        assert queue['running'] == queue['queued'] == 0
        assert researcher.peak == 5


def test_research_filters_ads_brokers_wrong_company_and_extracts_text_emails_without_ownership_guess():
    assert not usable_url('https://www.bing.com/aclick?x=1')
    assert not usable_url('https://rocketreach.co/person')
    assert not usable_url('https://user:password@example.com/contact')
    assert matches_company('Powens',{'url':'https://careers.powens.com/','title':'Careers','snippet':''})
    assert not matches_company('Finaxys',{'url':'https://unrelated.org/','title':'Other firm','snippet':'Recruitment'})
    from webtoolbox.contacts import extract_contacts, assess_employer
    from webtoolbox import merge_and_rank
    html = """<p>Write to recrutement@example.com</p><p>media@example.com</p>
    <div class="person"><h3>Justine Michel</h3><p class="role">Chief People Officer</p></div>
    <div class="person"><h3>Damien Mat</h3><p class="role">Lead Software Engineer</p></div>"""
    raw = [assess_employer(c, 'Example') for c in extract_contacts(html, 'https://example.com/contact')]
    candidates = [adapt_candidate(c) for c in merge_and_rank(raw)]
    useful = [c for c in candidates if not c['excluded']]
    assert len(useful) == 3
    by_name = {c['name']: c for c in useful}
    assert by_name['Justine Michel']['email'] is None
    assert by_name[None]['email'] == 'recrutement@example.com' and by_name[None]['kind'] == 'recruiter_hr'
    assert by_name['Damien Mat']['kind'] == 'technical_lead'
    assert all(c['vacancy_match'] == 'unknown' and c['company_match'] == 'unknown' for c in useful)
    assert all(c['deliverability'] == 'not_checked' for c in useful)
    assert next(c for c in candidates if c['email'] == 'media@example.com')['excluded']



def test_shutdown_requeues_inflight_work_and_restart_finishes_it(tmp_path):
    gate=GateResearch()
    settings=Settings(app_data_dir=tmp_path,_env_file=None)
    with TestClient(create_app(settings,recipient_researcher=gate)) as client:
        app=application(client)
        client.post(f"/api/applications/{app['id']}/recipients/fetch")
        until=time.monotonic()+4
        while gate.active == 0 and time.monotonic() < until:time.sleep(.02)
        assert gate.active == 1
    class InstantResearch:
        async def discover(self,context):return {'candidates':[],'warnings':[],'outcome':'NO_RESULTS'}
    with TestClient(create_app(settings,recipient_researcher=InstantResearch())) as client:
        until=time.monotonic()+4
        while time.monotonic() < until:
            state=client.get(f"/api/applications/{app['id']}/recipients").json()
            if state['job']['state'] == 'NO_RESULTS':break
            time.sleep(.02)
        assert state['job']['state'] == 'NO_RESULTS'
        assert state['job']['attempts'] == 2


def test_queued_closed_job_never_runs_and_missing_recipient_blocks_mailbox_work(client):
    from tests.followups.test_draft_tasks import activate
    pause(client)
    app=application(client)
    item=followup(client,app)
    url=f"/api/applications/{app['id']}/followups/{item['id']}"
    activate(client)
    client.patch(url,json={'body':'Hello'})
    assert client.post(url+'/draft-task',json={'expected_revision':2}).status_code == 422
    client.post(f"/api/applications/{app['id']}/recipients/fetch")
    client.patch(f"/api/applications/{app['id']}",json={'status':'CLOSED','outcome':'UNSUCCESSFUL'})
    assert discovery.claim(client.app.state.engine) is None
    assert client.get(f"/api/applications/{app['id']}/recipients").json()['job']['state'] == 'CANCELLED'


def test_vacancy_url_changes_invalidate_research_and_failed_diagnostics_are_visible(client):
    pause(client)
    app=application(client,job_url='https://example.com/jobs/1')
    client.post(f"/api/applications/{app['id']}/recipients/fetch")
    claimed=discovery.claim(client.app.state.engine)
    assert claimed['context']['job_url'] == 'https://example.com/jobs/1'
    client.patch(f"/api/applications/{app['id']}",json={'job_url':'https://example.com/jobs/2'})
    discovery.complete(client.app.state.engine,claimed,{'candidates':[],'outcome':'NO_RESULTS'})
    assert client.get(f"/api/applications/{app['id']}/recipients").json()['job']['state'] == 'CANCELLED'
    client.post(f"/api/applications/{app['id']}/recipients/fetch")
    claimed=discovery.claim(client.app.state.engine)
    discovery.complete(client.app.state.engine,claimed,{'candidates':[],'outcome':'FAILED',
        'error':'Research incomplete. Retry.', 'warnings':['Provider rate_limited']})
    job=client.get(f"/api/applications/{app['id']}/recipients").json()['job']
    assert job['state'] == 'FAILED' and job['error'] == 'Research incomplete. Retry.'
    assert job['warnings'] == ['Provider rate_limited']


def test_saved_candidates_are_presented_in_toolbox_priority_order(client):
    pause(client)
    app=application(client)
    client.post(f"/api/applications/{app['id']}/recipients/fetch")
    claimed=discovery.claim(client.app.state.engine)
    candidates=[{'email':'general@example.com','contact_priority':{'score':120}},
        {'email':'jobs@example.com','contact_priority':{'score':300}},
        {'name':'Named Recruiter','email':None,'contact_priority':{'score':400}}]
    discovery.complete(client.app.state.engine,claimed,{'candidates':candidates,'outcome':'COMPLETED'})
    saved=client.get(f"/api/applications/{app['id']}/recipients").json()['candidates']
    assert [c['contact_priority']['score'] for c in saved] == [400,300,120]
