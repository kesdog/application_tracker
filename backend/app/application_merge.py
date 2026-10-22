"""Reviewed duplicate consolidation; retain originals and immutable history."""
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from app import applications
from app.activity import record_audit, record_event
from app.models import ApplicationDocument, FollowUp, FollowUpStatus, Interview, MailImportReceipt, Note, Task, utc_now
from app.schemas import ApplicationRead, ApplicationUpdate

FIELDS = {'job_title', 'company', 'date_applied', 'intermediary', 'phone_number', 'contact_email', 'contact_name',
          'contact_type', 'location', 'remote_policy', 'contract_type', 'source', 'description', 'requirements', 'deadline', 'deadline_kind', 'job_url'}
CHILDREN = (Note, Task, Interview, ApplicationDocument, FollowUp)


class MergeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_id: str
    source_revision: int = Field(ge=1)
    target_revision: int = Field(ge=1)
    take_source_fields: list[str] = Field(default_factory=list)
    confirmed: bool = False


def preview(session, source_id, target_id):
    if source_id == target_id:
        raise applications.InvalidApplication('Choose two different applications')
    source, target = [applications.get_application(session, item) for item in (source_id, target_id)]
    return {'source': ApplicationRead.model_validate(source).model_dump(mode='json'),
        'target': ApplicationRead.model_validate(target).model_dump(mode='json'), 'fields': sorted(FIELDS),
        'counts': {kind.__tablename__: session.scalar(select(func.count()).select_from(kind).where(kind.application_id == source_id)) for kind in CHILDREN}}


def merge(session, settings, target_id, data):
    if not data.confirmed or set(data.take_source_fields) - FIELDS:
        raise applications.InvalidApplication('Review the field choices and confirm the merge')
    session.execute(text('BEGIN IMMEDIATE'))
    plan = preview(session, data.source_id, target_id)
    source = applications.get_application(session, data.source_id)
    target = applications.get_application(session, target_id)
    if data.source_revision != source.revision:
        raise applications.ApplicationRevisionConflict(source, {})
    if data.target_revision != target.revision:
        raise applications.ApplicationRevisionConflict(target, {})
    refs = list(dict.fromkeys([*(target.email_reference or '').splitlines(), *(source.email_reference or '').splitlines()]))
    if len('\n'.join(refs)) > 2048:
        raise applications.InvalidApplication('Combined email references exceed 2,048 characters. Review and shorten the references before consolidating; both originals are unchanged.')
    changes = {field: getattr(source, field) for field in data.take_source_fields}
    changes.update(email_reference='\n'.join(refs) or None, followup_paused=True)
    applications.update_application(session, target_id, ApplicationUpdate(**changes, expected_revision=target.revision), settings=settings, commit=False)
    followups = list(session.scalars(select(FollowUp).where(FollowUp.application_id == source.id).order_by(FollowUp.sequence_number)))
    remap = {item.id: str(uuid4()) for item in followups}
    sequence = session.scalar(select(func.max(FollowUp.sequence_number)).where(FollowUp.application_id == target_id)) or 0
    # Clone work rather than reparenting distributed IDs: the sync protocol
    # intentionally forbids moving an existing entity between applications.
    for kind in CHILDREN:
        for item in session.scalars(select(kind).where(kind.application_id == source.id)).all():
            values = {column.name: getattr(item, column.name) for column in kind.__table__.columns if column.name not in {'id', 'application_id'}}
            values['id'] = remap[item.id] if kind is FollowUp else str(uuid4())
            values['application_id'] = target_id
            if kind is FollowUp:
                sequence += 1
                values.update(sequence_number=sequence, revision=1, approved_revision=None, is_automatic=False,
                    parent_followup_id=remap.get(item.parent_followup_id),
                    status=FollowUpStatus.SENT if item.status == FollowUpStatus.SENT else FollowUpStatus.PREPARED,
                    archived_at=item.archived_at or (None if item.status == FollowUpStatus.SENT else utc_now()))
            session.add(kind(**values))
    for receipt in session.scalars(select(MailImportReceipt).where(MailImportReceipt.application_id == source.id)):
        receipt.application_id = target_id
    source.deleted_at = utc_now()
    source.followup_paused = True
    record_event(session, target_id, 'APPLICATION_MERGED', 'Duplicate application consolidated; review reminders before resuming',
        metadata={'source_id': source.id, 'copied_work': plan['counts'], 'source_fields': data.take_source_fields})
    record_event(session, source.id, 'APPLICATION_MERGED', 'Original retained in Trash after consolidation', metadata={'target_id': target_id})
    record_audit(session, target_id, 'APPLICATION', target_id, 'MERGE', new={'source_id': source.id, 'copied_work': plan['counts']})
    session.commit()
    return {'target_id': target_id, 'source_id': source.id, 'copied': plan['counts']}
