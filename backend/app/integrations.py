"""Explicit integration interfaces and a safe local fallback for email drafts."""
from datetime import timedelta, timezone
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.activity import record_audit, record_event
from app.applications import InvalidApplication, get_application
from app.models import ActorType, FollowUp, FollowUpChannel, FollowUpStatus, Note, NoteType, utc_now
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
    application = get_application(session, application_id)
    item = child(session, FollowUp, application_id, followup_id)
    if item.channel == FollowUpChannel.PHONE:
        raise InvalidApplication("Phone-only follow-ups do not have an email draft")
    if item.status == FollowUpStatus.SENT or item.archived_at:
        raise InvalidApplication("Reopen the follow-up before drafting")
    if provider.is_connected():
        reference = provider.create_draft(application, item, data.content)
        result = DraftResult(location="MAILBOX", note_id=None, message_reference=reference, message="Draft placed in the connected mailbox. Nothing was sent.")
    else:
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
