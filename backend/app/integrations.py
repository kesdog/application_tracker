"""Explicit integration interfaces and a safe local fallback for email drafts."""
from datetime import timedelta, timezone
from typing import Protocol
import hashlib
import json
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from app.activity import record_audit, record_event
from app.applications import InvalidApplication, get_application
from app.models import ActorType, ApplicationStatus, FollowUp, FollowUpChannel, FollowUpStatus, MailDraftOperation, Note, NoteType, utc_now
from app.followup_templates import RevisionConflict, TAG
from app.work import child


class MailProvider(Protocol):
    def is_connected(self) -> bool: ...
    def create_draft(self, application, followup: FollowUp, content: str) -> str: ...
    def open_message(self, reference: str) -> str: ...


class CalendarProvider(Protocol):
    def is_connected(self) -> bool: ...
    def create_event(self, application, interview) -> str: ...
    def update_event(self, reference: str, application, interview) -> None: ...


class DisconnectedMailProvider:
    def is_connected(self) -> bool:
        return False

    def create_draft(self, application, followup: FollowUp, content: str) -> str:
        raise RuntimeError("No mail provider is connected")

    def open_message(self, reference: str) -> str:
        raise RuntimeError("No mail provider is connected")


class DisconnectedCalendarProvider:
    def is_connected(self) -> bool:
        return False

    def create_event(self, application, interview) -> str:
        raise RuntimeError("No calendar provider is connected")

    def update_event(self, reference: str, application, interview) -> None:
        raise RuntimeError("No calendar provider is connected")


class DraftRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    content: str = Field(min_length=1)
    expected_revision: int | None = Field(default=None, ge=1, strict=True)
    operation_id: UUID = Field(default_factory=uuid4)


class DraftResult(BaseModel):
    location: str
    note_id: str | None
    message_reference: str | None
    message: str


def draft_followup(
    session: Session, application_id: str, followup_id: str, data: DraftRequest,
    provider: MailProvider, *, actor_type: ActorType = ActorType.HUMAN,
    actor_reference: str | None = None,
) -> DraftResult:
    operation_id = str(data.operation_id)
    request_hash = hashlib.sha256(json.dumps([application_id, followup_id, data.content, data.expected_revision]).encode()).hexdigest()
    receipt = session.get(MailDraftOperation, operation_id)
    if receipt:
        if receipt.request_hash != request_hash:
            raise RevisionConflict('This draft operation ID belongs to a different request. Review the existing draft before continuing.')
        if receipt.result is None:
            raise RevisionConflict('This draft is in progress or its external result is uncertain. Check the mailbox and reconcile it before starting another operation.')
        return DraftResult.model_validate(receipt.result)
    application = get_application(session, application_id)
    item = child(session, FollowUp, application_id, followup_id)
    if data.expected_revision is not None and item.revision != data.expected_revision:
        raise RevisionConflict('The follow-up changed. Reload and review before drafting.')
    if item.channel == FollowUpChannel.PHONE:
        raise InvalidApplication("Phone-only follow-ups do not have an email draft")
    if item.status == FollowUpStatus.SENT or item.archived_at:
        raise InvalidApplication("Reopen the follow-up before drafting")
    if application.status == ApplicationStatus.CLOSED:
        raise InvalidApplication('Reopen the application before drafting')
    connected = provider.is_connected()
    if connected:
        if not item.recipient_email:
            raise InvalidApplication('Choose a recipient before creating a mailbox draft')
        if TAG.search(data.content) or TAG.search(item.subject or ''):
            raise InvalidApplication('Fill or remove unresolved variables before creating a mailbox draft')
    original_revision = item.revision
    receipt = MailDraftOperation(id=operation_id, application_id=application_id,
        followup_id=followup_id, request_hash=request_hash)
    session.add(receipt)
    try:
        session.commit()  # Durable before the external side effect, including timeouts/crashes.
    except IntegrityError:
        session.rollback()
        raise RevisionConflict('This draft operation was already started. Retry the same operation ID to retrieve its result.') from None
    if connected:
        session.refresh(item)
        session.refresh(application)
        if item.revision != original_revision or item.status == FollowUpStatus.SENT or item.archived_at or application.status == ApplicationStatus.CLOSED or application.deleted_at:
            session.delete(receipt)
            session.commit()
            raise RevisionConflict('The follow-up changed before draft creation. Reload and review before retrying.')
        reference = provider.create_draft(application, item, data.content)
        result = DraftResult(location="MAILBOX", note_id=None, message_reference=reference, message="Draft placed in the connected mailbox. Nothing was sent.")
        session.rollback()
        session.execute(text('BEGIN IMMEDIATE'))
        session.refresh(item)
        session.refresh(application)
        if item.revision != original_revision or item.status == FollowUpStatus.SENT or item.archived_at or application.status == ApplicationStatus.CLOSED or application.deleted_at:
            result.message += ' The tracker context changed during creation. Review the mailbox draft; the newer tracker message was preserved.'
            receipt.result = result.model_dump(mode='json')
            record_event(session, application_id, 'EMAIL_DRAFT_CREATED', result.message, actor_type=actor_type,
                actor_reference=actor_reference, metadata={'operation_id': operation_id, 'followup_id': followup_id})
            session.commit()
            return result
    else:
        session.execute(text('BEGIN IMMEDIATE'))
        session.refresh(item)
        session.refresh(application)
        if item.revision != original_revision or item.status == FollowUpStatus.SENT or item.archived_at or application.status == ApplicationStatus.CLOSED or application.deleted_at:
            session.delete(receipt)
            session.commit()
            raise RevisionConflict('The follow-up changed before saving the local draft. Reload and review before retrying.')
        note = Note(application_id=application_id, content=data.content, type=NoteType.EMAIL_DRAFT, created_by=actor_type.value)
        session.add(note)
        session.flush()
        record_event(session, application_id, "NOTE_CREATED", "Email draft saved as a note", actor_type=actor_type, actor_reference=actor_reference, metadata={"note_id": note.id, "followup_id": item.id})
        record_audit(session, application_id, "NOTE", note.id, "CREATE", new={"content": data.content, "type": NoteType.EMAIL_DRAFT}, actor_type=actor_type, actor_reference=actor_reference)
        result = DraftResult(location="LOCAL_NOTE", note_id=note.id, message_reference=None, message="Draft saved as a local note. It was not placed in a mailbox or sent.")
    if item.body != data.content or item.status != FollowUpStatus.PREPARED:
        previous = {"status": item.status, "body": item.body, "revision": item.revision, "approved_revision": item.approved_revision}
        item.body = data.content
        item.status = FollowUpStatus.PREPARED
        item.revision += 1
        item.approved_revision = None
        record_event(session, application_id, "FOLLOWUP_DRAFTED", f"Follow-up #{item.sequence_number} drafted", actor_type=actor_type, actor_reference=actor_reference, metadata={"followup_id": item.id})
        record_audit(session, application_id, "FOLLOWUP", item.id, "UPDATE", previous=previous, new={name: getattr(item, name) for name in previous}, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
    receipt.result = result.model_dump(mode='json')
    record_event(session, application_id, 'EMAIL_DRAFT_CREATED', result.message,
        actor_type=actor_type, actor_reference=actor_reference,
        metadata={'followup_id': followup_id, 'operation_id': operation_id, 'location': result.location})
    session.commit()
    return result


def calendar_file(application, interview) -> str:
    """Generate an importable calendar file only after an explicit download."""
    def escaped(value: str) -> str:
        return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    start = interview.scheduled_at.replace(tzinfo=timezone.utc)
    end = start + timedelta(minutes=interview.duration or 60)
    stamp = utc_now().replace(tzinfo=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fields = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Application Tracker//EN",
        "BEGIN:VEVENT", f"UID:{interview.id}@application-tracker.local", f"DTSTAMP:{stamp}",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}", f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{escaped(interview.type.value.title() + ' interview - ' + application.company)}",
    ]
    if interview.location:
        fields.append(f"LOCATION:{escaped(interview.location)}")
    if interview.meeting_url:
        fields.append(f"URL:{interview.meeting_url}")
    fields.extend(["END:VEVENT", "END:VCALENDAR", ""])
    return "\r\n".join(fields)


def followup_calendar_file(application, item, origin) -> str:
    """Explicit, offline fallback; importing this event does not send a message."""
    from app.models import utc_now
    def escaped(value):
        return value.replace("\\", "\\\\").replace("\r", "").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")
    start = max(item.due_at, item.snoozed_until or item.due_at)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Application Tracker//Follow-up reminder//EN", "BEGIN:VEVENT",
        f"UID:followup-{item.id}@application-tracker", f"DTSTAMP:{utc_now().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}", f"DTEND:{(start + timedelta(minutes=15)).strftime('%Y%m%dT%H%M%SZ')}",
        "SUMMARY:" + escaped("Review follow-up - " + application.company),
        "DESCRIPTION:Review the prepared message in Application Tracker. Sending is a separate manual action.",
        f"URL:{origin}/#/followups/{application.id}/{item.id}", "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:PT0M",
        "DESCRIPTION:Review your follow-up", "END:VALARM", "END:VEVENT", "END:VCALENDAR"]
    folded = []
    for line in lines:
        chunk = ""
        for char in line:
            if len((chunk + char).encode("utf-8")) > 75:
                folded.append(chunk)
                chunk = " "
            chunk += char
        folded.append(chunk)
    return "\r\n".join(folded) + "\r\n"
