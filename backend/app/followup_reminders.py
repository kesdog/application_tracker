"""Persistent scheduled notices independent of mailbox access and agents."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from app.followup_templates import current_settings
from app.models import Application, ApplicationStatus, FollowUp, FollowUpNotice, FollowUpStatus, utc_now


def in_quiet_hours(now: datetime, values: dict) -> bool:
    clock = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(values["timezone"])).strftime("%H:%M")
    start, end = values["quiet_start"], values["quiet_end"]
    return False if start == end else start <= clock < end if start < end else clock >= start or clock < end


def synchronize(session: Session, now: datetime | None = None):
    now = now or utc_now()
    values = current_settings(session)
    actionable = {}
    rows = session.execute(select(FollowUp, Application).join(Application).where(
        Application.deleted_at.is_(None), Application.status != ApplicationStatus.CLOSED,
        Application.followup_paused.is_(False), FollowUp.archived_at.is_(None),
        FollowUp.status.in_((FollowUpStatus.PREPARED, FollowUpStatus.READY)),
    )).all()
    for item, _ in rows:
        due = max(item.due_at, item.snoozed_until or item.due_at)
        key = due.isoformat()
        actionable[item.id] = key
        session.execute(insert(FollowUpNotice).values(followup_id=item.id, schedule_key=key, due_at=due, state="PENDING")
                        .on_conflict_do_nothing(index_elements=["followup_id", "schedule_key"]))
    for notice in session.scalars(select(FollowUpNotice)):
        if actionable.get(notice.followup_id) != notice.schedule_key:
            notice.state = "SUPERSEDED"
        elif notice.read_at is None:
            notice.state = "AVAILABLE" if values["notifications_enabled"] and notice.due_at <= now and not in_quiet_hours(now, values) else "PENDING"
    session.commit()


def notices(session: Session) -> list[dict]:
    from app.work_schemas import FollowUpRead
    rows = session.execute(select(FollowUpNotice, FollowUp, Application).join(FollowUp, FollowUpNotice.followup_id == FollowUp.id)
        .join(Application, FollowUp.application_id == Application.id).where(FollowUpNotice.state == "AVAILABLE", FollowUpNotice.read_at.is_(None))
        .order_by(FollowUpNotice.due_at, FollowUpNotice.id)).all()
    return [{"id": notice.id, "followup": FollowUpRead.model_validate(item).model_dump(mode="json"),
             "application": {"id": app.id, "company": app.company, "job_title": app.job_title}} for notice, item, app in rows]
