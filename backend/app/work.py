from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.applications import ApplicationNotFound, InvalidApplication, get_application
from app.activity import record_audit, record_event
from app.config import Settings
from app.models import ActorType, Application, ApplicationStatus, ContactType, FollowUp, FollowUpChannel, FollowUpStatus, Note, Task, TaskStatus, utc_now
from app.work_schemas import FollowUpCreate, FollowUpUpdate, NoteCreate, NoteUpdate, TaskCreate, TaskUpdate
from app import followup_templates as templates


def effective_settings(application, settings: Settings, session: Session | None = None) -> dict:
    global_values = templates.current_settings(session, settings) if session else settings.model_dump()
    return {
        name: getattr(application, name) if getattr(application, name) is not None else global_values[name]
        for name in ("followup_delay_days", "max_followup_suggestions")
    }


def automatic_due_at(application: Application, settings: Settings, *, after: datetime | None = None, session: Session) -> datetime:
    delay = effective_settings(application, settings, session)["followup_delay_days"]
    return templates.calendar_due(application, templates.current_settings(session, settings), delay, after)


def automatic_channel(application: Application) -> FollowUpChannel:
    return FollowUpChannel.PHONE if application.contact_type == ContactType.PHONE else FollowUpChannel.EMAIL


def can_schedule_automatic_followup(application: Application, settings: Settings, session: Session) -> bool:
    return (
        application.deleted_at is None
        and application.status != ApplicationStatus.CLOSED
        and application.outcome is None
        and not application.followup_paused
        and effective_settings(application, settings, session)["max_followup_suggestions"] > 0
    )


def schedule_automatic_followup(
    session: Session, application: Application, settings: Settings, *, after: datetime | None = None,
    actor_type: ActorType = ActorType.SYSTEM, actor_reference: str | None = None, parent_followup_id: str | None = None,
) -> FollowUp | None:
    if not can_schedule_automatic_followup(application, settings, session):
        return None
    automatic_count = session.scalar(
        select(func.count()).select_from(FollowUp).where(
            FollowUp.application_id == application.id, FollowUp.is_automatic.is_(True),
        )
    ) or 0
    if automatic_count >= effective_settings(application, settings, session)["max_followup_suggestions"]:
        return None
    sequence = (session.scalar(select(func.max(FollowUp.sequence_number)).where(FollowUp.application_id == application.id)) or 0) + 1
    item = FollowUp(
        application_id=application.id, sequence_number=sequence,
        due_at=automatic_due_at(application, settings, after=after, session=session),
        is_automatic=True, channel=automatic_channel(application), template_reference="Default follow-up", parent_followup_id=parent_followup_id,
    )
    session.add(item)
    session.flush()
    templates.prepare(session, application, item, settings)
    record_event(
        session, application.id, "FOLLOWUP_CREATED", f"Automatic follow-up #{sequence} scheduled for {item.due_at.date().isoformat()}",
        actor_type=actor_type, actor_reference=actor_reference,
        metadata={"followup_id": item.id, "automatic": True, "due_at": item.due_at},
    )
    return item


def ensure_initial_followups(session: Session, settings: Settings) -> int:
    """Backfill the first reminder for active applications exactly once."""
    created = 0
    templates.current_settings(session, settings)
    applications = session.scalars(select(Application).where(Application.deleted_at.is_(None))).all()
    for application in applications:
        existing = session.scalar(select(FollowUp.id).where(
            FollowUp.application_id == application.id, FollowUp.is_automatic.is_(True),
        ))
        if existing is None and schedule_automatic_followup(session, application, settings) is not None:
            created += 1
    from app.models import TimelineEvent
    for item in session.scalars(select(FollowUp).where(FollowUp.prepared_at.is_(None), FollowUp.status != FollowUpStatus.SENT)):
        application = session.get(Application, item.application_id)
        if application.deleted_at is not None:
            continue
        archived_at = item.archived_at
        templates.prepare(session, application, item, settings)
        item.archived_at = archived_at
        # Only recover a draft where the old activity explicitly links the note.
        for event in session.scalars(select(TimelineEvent).where(TimelineEvent.application_id == application.id,
                                  TimelineEvent.event_type == "NOTE_CREATED").order_by(TimelineEvent.created_at, TimelineEvent.id)):
            if event.event_metadata.get("followup_id") == item.id:
                note = session.get(Note, event.event_metadata.get("note_id"))
                if note and note.application_id == application.id:
                    item.body = note.content
    session.commit()
    return created


def reschedule_pending_automatic_followups(session: Session, application: Application, settings: Settings) -> int:
    changed = 0
    for item in session.scalars(select(FollowUp).where(
        FollowUp.application_id == application.id,
        FollowUp.is_automatic.is_(True),
        FollowUp.status.in_((FollowUpStatus.PREPARED, FollowUpStatus.READY)), FollowUp.archived_at.is_(None),
    )):
        parent = session.get(FollowUp, item.parent_followup_id) if item.parent_followup_id else None
        due_at = automatic_due_at(application, settings, session=session, after=parent.sent_at if parent else None)
        if item.due_at != due_at:
            item.due_at = due_at
            item.revision += 1
            if item.status == FollowUpStatus.READY:
                item.approved_revision = item.revision
            changed += 1
    if changed:
        record_event(
            session, application.id, "FOLLOWUP_CHANGED", "Automatic follow-up schedule updated",
            actor_type=ActorType.HUMAN, metadata={"automatic": True, "count": changed},
        )
    return changed


def get_work(session: Session, application_id: str, settings: Settings) -> dict:
    application = get_application(session, application_id)
    return {
        "notes": list(session.scalars(select(Note).where(Note.application_id == application_id).order_by(Note.created_at.desc(), Note.id))),
        "tasks": list(session.scalars(select(Task).where(Task.application_id == application_id).order_by(Task.due_at.is_(None), Task.due_at, Task.id))),
        "followups": list(session.scalars(select(FollowUp).where(FollowUp.application_id == application_id).order_by(FollowUp.sequence_number))),
        **effective_settings(application, settings, session),
        "outcome_review": outcome_review(session, application, settings),
    }


def outcome_review(session, application, settings):
    """An advisory derived from actual sends, never an inferred rejection."""
    from app.models import TimelineEvent, Interview
    threshold = templates.current_settings(session, settings)['unsuccessful_review_after']
    last_reply = session.scalar(select(func.max(TimelineEvent.created_at)).where(
        TimelineEvent.application_id == application.id, TimelineEvent.event_type == 'EMPLOYER_REPLY_RECORDED'))
    query = select(func.count()).select_from(FollowUp).where(
        FollowUp.application_id == application.id, FollowUp.status == FollowUpStatus.SENT)
    if last_reply:
        query = query.where(FollowUp.sent_at > last_reply)
    count = session.scalar(query) or 0
    interview = session.scalar(select(Interview.id).where(Interview.application_id == application.id).limit(1))
    return {'threshold': threshold, 'unanswered_sent_count': count, 'last_reply_at': last_reply.replace(tzinfo=timezone.utc) if last_reply else None,
            'needs_review': bool(threshold and count >= threshold and not interview and
                application.status == ApplicationStatus.SUBMITTED and application.outcome is None and application.deleted_at is None)}


def outcome_reviews(session, settings, page=1, page_size=20):
    threshold = templates.current_settings(session, settings)['unsuccessful_review_after']
    if not threshold:
        return {'items': [], 'total': 0, 'page': page, 'page_size': page_size}
    candidates = session.scalars(select(Application).where(Application.deleted_at.is_(None),
        Application.status == ApplicationStatus.SUBMITTED, Application.outcome.is_(None),
        Application.id.in_(select(FollowUp.application_id).where(FollowUp.status == FollowUpStatus.SENT)
            .group_by(FollowUp.application_id).having(func.count() >= threshold)))
        .order_by(Application.date_applied, Application.id))
    rows = []
    for application in candidates:
        review = outcome_review(session, application, settings)
        if review['needs_review']:
            rows.append({'application': {'id': application.id, 'company': application.company, 'job_title': application.job_title}, **review})
    start = (page - 1) * page_size
    return {'items': rows[start:start + page_size], 'total': len(rows), 'page': page, 'page_size': page_size}


def child(session, model, application_id, item_id):
    get_application(session, application_id)
    item = session.scalar(select(model).where(model.id == item_id, model.application_id == application_id))
    if item is None:
        raise ApplicationNotFound("Record not found for this application")
    return item


def finish(session, item):
    session.commit()
    session.refresh(item)
    return item


def create_note(
    session: Session, application_id: str, data: NoteCreate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Note:
    get_application(session, application_id)
    item = Note(application_id=application_id, created_by=actor_reference or actor_type.value, **data.model_dump(exclude={"employer_reply"}))
    session.add(item); session.flush()
    record_event(session, application_id, "NOTE_ADDED", f"{item.type.value.title()} note added", actor_type=actor_type, actor_reference=actor_reference, metadata={"note_id": item.id})
    if data.employer_reply:
        record_event(session, application_id, "EMPLOYER_REPLY_RECORDED", "Employer reply recorded; unanswered follow-up count reset", actor_type=actor_type, actor_reference=actor_reference, metadata={"note_id": item.id})
    record_audit(session, application_id, "NOTE", item.id, "CREATE", new=data.model_dump(), actor_type=actor_type, actor_reference=actor_reference)
    return finish(session, item)


def update_note(
    session: Session, application_id: str, item_id: str, data: NoteUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Note:
    item = child(session, Note, application_id, item_id)
    changes = {name: value for name, value in data.model_dump(exclude_unset=True).items() if value != getattr(item, name)}
    previous = {name: getattr(item, name) for name in changes}
    for name, value in changes.items():
        setattr(item, name, value)
    if changes:
        record_event(session, application_id, "NOTE_CHANGED", "Note updated", actor_type=actor_type, actor_reference=actor_reference, metadata={"note_id": item.id, "fields": sorted(changes)})
        record_audit(session, application_id, "NOTE", item.id, "UPDATE", previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
    return finish(session, item)


def create_task(
    session: Session, application_id: str, data: TaskCreate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None, commit: bool = True,
) -> Task:
    get_application(session, application_id)
    item = Task(application_id=application_id, **data.model_dump())
    session.add(item); session.flush()
    record_event(session, application_id, "TASK_CREATED", f"Task created: {item.title}", actor_type=actor_type, actor_reference=actor_reference, metadata={"task_id": item.id})
    record_audit(session, application_id, "TASK", item.id, "CREATE", new=data.model_dump(), actor_type=actor_type, actor_reference=actor_reference)
    return finish(session, item) if commit else item


def update_task(
    session: Session, application_id: str, item_id: str, data: TaskUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> Task:
    item = child(session, Task, application_id, item_id)
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes and changes["status"] != item.status:
        changes["completed_at"] = utc_now() if changes["status"] == TaskStatus.COMPLETED else None
    changes = {name: value for name, value in changes.items() if value != getattr(item, name)}
    previous = {name: getattr(item, name) for name in changes}
    for name, value in changes.items():
        setattr(item, name, value)
    if changes:
        event_type = "TASK_COMPLETED" if changes.get("status") == TaskStatus.COMPLETED else "TASK_CHANGED"
        summary = f"Task completed: {item.title}" if event_type == "TASK_COMPLETED" else f"Task updated: {item.title}"
        record_event(session, application_id, event_type, summary, actor_type=actor_type, actor_reference=actor_reference, metadata={"task_id": item.id})
        record_audit(session, application_id, "TASK", item.id, "UPDATE", previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
    return finish(session, item)


def create_followup(
    session: Session, application_id: str, data: FollowUpCreate, settings: Settings, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None,
) -> FollowUp:
    # Take SQLite's write lock before reading the next sequence number. API calls
    # supply a fresh session; simultaneous creates serialize within busy_timeout.
    session.execute(text("BEGIN IMMEDIATE"))
    application = get_application(session, application_id)
    if data.channel in (FollowUpChannel.PHONE, FollowUpChannel.BOTH) and not application.phone_number:
        raise InvalidApplication("Add a phone number to the application before choosing a phone follow-up")
    sequence = (session.scalar(select(func.max(FollowUp.sequence_number)).where(FollowUp.application_id == application_id)) or 0) + 1
    due_at = data.due_at or utc_now() + timedelta(days=effective_settings(application, settings, session)["followup_delay_days"])
    # The suggestion cap is not a limit on manual creation. No email is sent here.
    item = FollowUp(application_id=application_id, sequence_number=sequence, due_at=due_at, template_reference=data.template_reference, channel=data.channel,
                    instructions=data.instructions, customization=data.customization.model_dump(exclude_none=True))
    session.add(item); session.flush()
    templates.prepare(session, application, item, settings)
    if data.subject is not None:
        item.subject = templates.render(templates.normalize(data.subject), item.variable_snapshot)["text"]
    if data.body is not None:
        item.body = templates.render(templates.normalize(data.body), item.variable_snapshot)["text"]
    record_event(session, application_id, "FOLLOWUP_CREATED", f"Follow-up #{sequence} created", actor_type=actor_type, actor_reference=actor_reference, metadata={"followup_id": item.id})
    record_audit(session, application_id, "FOLLOWUP", item.id, "CREATE", new={"sequence_number": sequence, "due_at": due_at, "template_reference": data.template_reference, "channel": data.channel}, actor_type=actor_type, actor_reference=actor_reference)
    return finish(session, item)


def update_followup(
    session: Session, application_id: str, item_id: str, data: FollowUpUpdate, *,
    actor_type: ActorType = ActorType.HUMAN, actor_reference: str | None = None, settings: Settings | None = None, template_metadata: dict | None = None, commit: bool = True,
) -> FollowUp:
    if commit:
        session.execute(text("BEGIN IMMEDIATE"))
    item = child(session, FollowUp, application_id, item_id)
    changes = data.model_dump(exclude_unset=True)
    if template_metadata:
        changes.update(template_metadata)
    expected = changes.pop("expected_revision", None)
    if expected is not None and expected != item.revision:
        raise templates.RevisionConflict("This follow-up changed in another session. Reload before saving.")
    application = get_application(session, application_id)
    if "archived" in changes:
        changes["archived_at"] = utc_now() if changes.pop("archived") else None
    if 'recipient_email' in changes and changes['recipient_email'] != item.recipient_email and 'recipient_source_url' not in changes:
        changes['recipient_source_url'] = None
    if changes.get("status") == FollowUpStatus.CANCELLED:
        changes.update(status=FollowUpStatus.PREPARED, archived_at=utc_now())
    if changes.get("status") in (FollowUpStatus.READY, FollowUpStatus.SENT) and (changes.get("archived_at", item.archived_at) or (changes.get("status") == FollowUpStatus.READY and application.status.value == "CLOSED")):
        raise InvalidApplication("Reopen the follow-up and application before completing it")
    if actor_type == ActorType.AGENT and changes.get("status") == FollowUpStatus.READY:
        raise InvalidApplication("Ready approval must be recorded by the user")
    if actor_type == ActorType.AGENT and {"subject", "body", "instructions", "customization", "recipient_email", "recipient_name", "recipient_source_url"} & set(changes) and (application.status == ApplicationStatus.CLOSED or item.archived_at):
        raise InvalidApplication("Reopen the application and follow-up before accepting an agent revision")
    if "sent_at" in changes and changes.get("status", item.status) != FollowUpStatus.SENT:
        raise InvalidApplication("A sent timestamp requires status SENT")
    if changes.get("status", item.status) == FollowUpStatus.SENT and "sent_at" in changes and changes["sent_at"] is None:
        raise InvalidApplication("A sent follow-up requires its actual send time")
    if item.status == FollowUpStatus.SENT and any(k in changes for k in ("subject", "body", "instructions", "customization", "recipient_email", "recipient_name", "recipient_source_url")):
        raise InvalidApplication("Reopen the follow-up before editing sent content")
    content_changes = {k for k in ("subject", "body", "instructions", "customization", "channel", "template_snapshot", "variable_snapshot", "recipient_email", "recipient_name", "recipient_source_url") if k in changes and changes[k] != getattr(item, k)}
    if content_changes and item.status == FollowUpStatus.READY:
        changes.update(status=FollowUpStatus.PREPARED, approved_revision=None)
    if any(templates.TAG.search(changes.get(k, "")) for k in ("subject", "body")):
        values = templates.context_values(session, application, item, item.template_snapshot or templates.current_settings(session, settings))
        values.update({k: v for k, v in changes.get("customization", {}).items() if v is not None})
        for name in ("subject", "body"):
            if name in changes:
                changes[name] = templates.render(templates.normalize(changes[name]), values)["text"]
    if changes.get("status") == FollowUpStatus.READY:
        subject, body = changes.get("subject", item.subject), changes.get("body", item.body)
        if item.channel != FollowUpChannel.PHONE and (not subject.strip() or not body.strip() or templates.TAG.search(subject) or templates.TAG.search(body)):
            raise InvalidApplication("Fill or remove highlighted variables and provide a subject and message before marking ready")
        changes["approved_revision"] = item.revision + 1
    elif "status" in changes and changes["status"] != FollowUpStatus.SENT:
        changes["approved_revision"] = None
    if "channel" in changes and changes["channel"] in (FollowUpChannel.PHONE, FollowUpChannel.BOTH) and not get_application(session, application_id).phone_number:
        raise InvalidApplication("Add a phone number to the application before choosing a phone follow-up")
    if "status" in changes and changes["status"] != item.status:
        changes["sent_at"] = changes.get("sent_at") or utc_now() if changes["status"] == FollowUpStatus.SENT else None
    changes = {name: value for name, value in changes.items() if value != getattr(item, name)}
    old_status, old_sent_at = item.status, item.sent_at
    if changes:
        changes["revision"] = item.revision + 1
        if changes.get("status", item.status) == FollowUpStatus.READY:
            changes["approved_revision"] = changes["revision"]
    previous = {name: getattr(item, name) for name in changes}
    for name, value in changes.items():
        setattr(item, name, value)
    if changes:
        status = changes.get("status")
        event_type = "FOLLOWUP_SENT" if status == FollowUpStatus.SENT else "FOLLOWUP_READY" if status == FollowUpStatus.READY else "FOLLOWUP_DRAFTED" if {"subject", "body"} & set(changes) else "FOLLOWUP_CHANGED"
        if status == FollowUpStatus.SENT:
            method = "email and phone" if item.channel == FollowUpChannel.BOTH else "phone" if item.channel == FollowUpChannel.PHONE else "email"
            summary = f"Follow-up #{item.sequence_number} completed by {method}"
        else:
            summary = f"Follow-up #{item.sequence_number} {status.value.lower()}" if status else f"Follow-up #{item.sequence_number} updated"
        record_event(session, application_id, event_type, summary, actor_type=actor_type, actor_reference=actor_reference, metadata={"followup_id": item.id})
        record_audit(session, application_id, "FOLLOWUP", item.id, "UPDATE", previous=previous, new=changes, actor_type=actor_type, actor_reference=actor_reference, reversible=True)
        if old_status == FollowUpStatus.SENT and item.status != FollowUpStatus.SENT:
            remove_untouched_successor(session, item)
        elif old_status == FollowUpStatus.SENT and item.sent_at != old_sent_at:
            reschedule_untouched_successor(session, item, settings or Settings())
        if item.status == FollowUpStatus.SENT and old_status != FollowUpStatus.SENT and item.is_automatic:
            schedule_automatic_followup(session, application, settings=settings or Settings(), after=item.sent_at, actor_type=actor_type, actor_reference=actor_reference, parent_followup_id=item.id)
    if commit:
        return finish(session, item)
    session.flush()
    return item


def remove_untouched_successor(session: Session, item: FollowUp):
    from app.models import FollowUpNotice
    successor = session.scalar(select(FollowUp).where(FollowUp.parent_followup_id == item.id))
    if successor:
        if successor.archived_at:
            # Keep edited historical content. It no longer depends on this send.
            successor.parent_followup_id = None
            return
        if successor.revision != 1 or successor.status != FollowUpStatus.PREPARED:
            raise InvalidApplication("The next follow-up has been edited. Archive it before undoing the earlier send.")
        for notice in session.scalars(select(FollowUpNotice).where(FollowUpNotice.followup_id == successor.id)):
            session.delete(notice)
        session.delete(successor)


def reschedule_untouched_successor(session: Session, item: FollowUp, settings: Settings):
    successor = session.scalar(select(FollowUp).where(FollowUp.parent_followup_id == item.id))
    if successor and successor.status == FollowUpStatus.PREPARED and successor.revision == 1 and not successor.archived_at:
        application = get_application(session, item.application_id)
        successor.due_at = automatic_due_at(application, settings, after=item.sent_at, session=session)


def proposed_message(session: Session, application_id: str, item_id: str, settings: Settings, *, latest=True) -> dict:
    item = child(session, FollowUp, application_id, item_id)
    application = get_application(session, application_id)
    general = templates.current_settings(session, settings)
    snapshot = general if latest or not item.template_snapshot else item.template_snapshot
    values = templates.context_values(session, application, item, snapshot)
    return {"subject": templates.render(snapshot["subject_template"], values), "body": templates.render(snapshot["body_template"], values),
            "template_snapshot": {k: snapshot[k] for k in ("subject_template", "body_template", "revision", "language", "tone", "signature", "instructions")},
            "variable_snapshot": values, "expected_revision": item.revision}


def apply_message(session: Session, application_id: str, item_id: str, settings: Settings, expected_revision: int, *, latest=True):
    proposed = proposed_message(session, application_id, item_id, settings, latest=latest)
    return update_followup(session, application_id, item_id, FollowUpUpdate(subject=proposed["subject"]["text"], body=proposed["body"]["text"], expected_revision=expected_revision), settings=settings,
                           template_metadata={"template_snapshot": proposed["template_snapshot"], "variable_snapshot": proposed["variable_snapshot"]})


def ai_request(session: Session, application_id: str, item_id: str, settings: Settings) -> dict:
    from app.followup_ai import current_request
    return current_request(session, application_id, item_id, settings)


def resolved_message(session: Session, application_id: str, item_id: str, settings: Settings) -> dict:
    request = ai_request(session, application_id, item_id, settings)
    return {"subject": templates.render(request["subject"], request["variables"]),
            "body": templates.render(request["body"], request["variables"]),
            "variables": request["variables"], "revision": request["expected_revision"]}


def queue_draft_task(session: Session, application_id: str, item_id: str, settings: Settings, revision: int):
    session.execute(text('BEGIN IMMEDIATE'))
    from app import agent_auth
    from app.models import Task, TaskStatus
    from sqlalchemy import select
    if not agent_auth.draft_availability(session)["can_draft"]:
        raise InvalidApplication("Use an agent token with read, draft and tasks permissions within the last 15 minutes before requesting a draft. You can still copy the message.")
    item = child(session, FollowUp, application_id, item_id)
    app = get_application(session, application_id)
    if item.revision != revision:
        raise templates.RevisionConflict("The follow-up changed. Reload it before requesting a draft.")
    if item.channel == FollowUpChannel.PHONE or item.status == FollowUpStatus.SENT or item.archived_at or app.status == ApplicationStatus.CLOSED:
        raise InvalidApplication("Only an open email follow-up can be queued for drafting")
    if not item.recipient_email:
        raise InvalidApplication('Choose or enter a recipient before requesting a mailbox draft')
    rendered = resolved_message(session, application_id, item_id, settings)
    if any(rendered[field][problem] for field in ("subject", "body") for problem in ("missing", "unknown")):
        raise InvalidApplication("Fill or remove unresolved variables before requesting a draft")
    title = f"AI: Write follow-up #{item.sequence_number} to draft"
    marker = f"Follow-up: {item.id}; revision: {item.revision}"
    from app.followup_ai import draft_task, request as build_request
    existing = draft_task(session, application_id, build_request(session, application_id, item_id, settings, action='write_mailbox_draft')['operation_id'])
    if existing:
        return existing
    import json
    task = create_task(session, application_id, TaskCreate(title=title, description=marker), commit=False)
    request = build_request(session, application_id, item_id, settings, action="write_mailbox_draft")
    description = marker + "\nUse your mailbox tools to write the saved message to a draft; never send email. Recheck this operation with get_followup_request before any mailbox write. Report the structured result with report_followup_result; the tracker completes this task when a draft is recorded.\n" + json.dumps(request, ensure_ascii=False, indent=2)
    task.description = description
    return finish(session, task)


def jsonable_application(application):
    from app.schemas import ApplicationRead
    return ApplicationRead.model_validate(application).model_dump(mode="json")
