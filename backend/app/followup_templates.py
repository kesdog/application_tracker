"""One deterministic template and instruction contract for humans and agents."""
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Application, ApplicationDocument, FollowUp, GeneralSettings, Interview, Note, Task

TAG = re.compile(r"\{([^{}\n]+)\}")
ALIASES = {"company": "company_name", "company name": "company_name", "job_title": "position_name", "position name": "position_name"}
FIELD_NAMES = {"company": "company_name", "job_title": "position_name"}
DEFAULT_SUBJECT = "Following up on my application — {position_name}"
DEFAULT_BODY = "Hello,\n\nI'm following up on my application for {position_name} at {company_name}, submitted on {date_applied}. I'm still interested in the opportunity and would appreciate any update on the next steps.\n\nBest regards,\n{signature}"


class Customization(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str | None = Field(default=None, max_length=80)
    tone: str | None = Field(default=None, max_length=120)
    signature: str | None = Field(default=None, max_length=3000)


class GeneralSettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject_template: str = Field(default=DEFAULT_SUBJECT, min_length=1, max_length=3000)
    body_template: str = Field(default=DEFAULT_BODY, min_length=1, max_length=50000)
    signature: str = Field(default="", max_length=3000)
    language: str = Field(default="English", max_length=80)
    tone: str = Field(default="Professional and concise", max_length=120)
    instructions: str = Field(default="", max_length=12000)
    followup_delay_days: int = Field(default=7, ge=0, le=3650)
    max_followup_suggestions: int = Field(default=2, ge=0, le=100)
    timezone: str = "Europe/Paris"
    reminder_time: str = "09:00"
    notifications_enabled: bool = True
    quiet_start: str = "20:00"
    quiet_end: str = "08:00"
    daily_digest: bool = True
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Choose a valid IANA timezone, for example Europe/Paris") from exc
        return value

    @field_validator("reminder_time", "quiet_start", "quiet_end")
    @classmethod
    def valid_time(cls, value):
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Use HH:MM in 24-hour time")
        return value


class RevisionConflict(ValueError):
    pass


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: str = Field(max_length=3000)
    body: str = Field(max_length=50000)
    application_id: str | None = None
    customization: Customization = Field(default_factory=Customization)


def current_settings(session: Session, settings: Settings | None = None) -> dict:
    record = session.get(GeneralSettings, 1)
    if record is None:
        runtime = settings or Settings()
        values = GeneralSettingsInput(followup_delay_days=runtime.followup_delay_days,
                                     max_followup_suggestions=runtime.max_followup_suggestions).model_dump(exclude={"expected_revision"})
        record = GeneralSettings(id=1, values=values, revision=1)
        session.add(record)
        session.flush()
    return {**record.values, "revision": record.revision}


def normalize(template: str) -> str:
    return TAG.sub(lambda m: "{" + ALIASES.get(m[1].strip(), m[1].strip()) + "}", template)


def save_settings(session: Session, data: GeneralSettingsInput, settings: Settings) -> dict:
    session.execute(text("BEGIN IMMEDIATE"))
    current_settings(session, settings)
    record = session.get(GeneralSettings, 1)
    if data.expected_revision is not None and data.expected_revision != record.revision:
        raise RevisionConflict("Settings changed in another session. Reload before saving.")
    values = data.model_dump(exclude={"expected_revision"})
    for name in ("subject_template", "body_template"):
        values[name] = normalize(values[name])
        unknown = [m[1] for m in TAG.finditer(values[name]) if m[1] not in {v["key"] for v in variables()}]
        if unknown:
            raise ValueError("Unknown template variables: " + ", ".join(sorted(set(unknown))))
    if record.values != values:
        record.values = values
        record.revision += 1
    session.commit()
    return current_settings(session, settings)


def variables() -> list[dict]:
    result = []
    advanced = {"id", "deleted_at", "posting_http_status", "posting_final_url", "posting_check_method", "posting_check_reason", "posting_check_failures", "posting_last_checked_at", "followup_customization"}
    for column in Application.__table__.columns:
        key = FIELD_NAMES.get(column.name, column.name)
        result.append({"key": key, "label": column.name.replace("_", " ").capitalize(),
                       "group": "Advanced" if column.name in advanced else "Application",
                       "aliases": [a for a, canonical in ALIASES.items() if canonical == key]})
    for key, label, group in (("signature", "Signature", "Preferences"), ("language", "Language", "Preferences"),
                              ("tone", "Tone", "Preferences"), ("notes", "Application notes", "Related work"),
                              ("documents", "Document filenames and references", "Related work"),
                              ("tasks", "Tasks", "Related work"), ("interviews", "Interviews", "Related work"),
                              ("followup_number", "Follow-up number", "Follow-up"), ("followup_due_at", "Due date", "Follow-up"),
                              ("previous_sent_at", "Previous sent date", "Follow-up")):
        result.append({"key": key, "label": label, "group": group, "aliases": []})
    return result


def text_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(jsonable_encoder(value), ensure_ascii=False, sort_keys=True)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def effective_preferences(application: Application, item: FollowUp | None, general: dict) -> dict:
    result = {name: general[name] for name in ("language", "tone", "signature")}
    for overrides in (application.followup_customization or {}, item.customization if item else {}):
        result.update({k: v for k, v in (overrides or {}).items() if v is not None})
    result["instructions"] = [v for v in (general["instructions"], application.followup_instructions, item.instructions if item else "") if v]
    return result


def context_values(session: Session, application: Application, item: FollowUp | None, general: dict) -> dict:
    values = {FIELD_NAMES.get(c.name, c.name): text_value(getattr(application, c.name)) for c in Application.__table__.columns}
    prefs = effective_preferences(application, item, general)
    values.update({name: text_value(prefs[name]) for name in ("signature", "language", "tone")})
    related = (("notes", Note, "created_at"), ("documents", ApplicationDocument, "created_at"),
               ("tasks", Task, "id"), ("interviews", Interview, "scheduled_at"))
    for key, model, order in related:
        rows = session.scalars(select(model).where(model.application_id == application.id).order_by(getattr(model, order), model.id)).all()
        if key == "notes":
            lines = [r.content for r in rows]
        elif key == "documents":
            lines = [f"{r.filename}: {r.external_reference or r.storage_path or ''}".rstrip(": ") for r in rows]
        elif key == "tasks":
            lines = [f"{r.title} ({r.status.value})" for r in rows]
        else:
            lines = [f"{r.type.value}: {r.scheduled_at.isoformat()} — {r.notes or ''}".rstrip(" —") for r in rows]
        values[key] = "\n".join(lines)
    previous = session.scalar(select(FollowUp).where(FollowUp.application_id == application.id, FollowUp.sent_at.is_not(None),
                                                    FollowUp.id != (item.id if item else "")).order_by(FollowUp.sent_at.desc()).limit(1))
    values.update(followup_number=str(item.sequence_number if item else 1),
                  followup_due_at=text_value(item.due_at if item else None), previous_sent_at=text_value(previous.sent_at if previous else None))
    return values


def render(template: str, values: dict) -> dict:
    missing, unknown = set(), set()

    def replace(match):
        key = ALIASES.get(match[1].strip(), match[1].strip())
        if key not in values:
            unknown.add(key)
        elif values[key] == "":
            missing.add(key)
        else:
            return str(values[key])
        return "{" + key + "}"

    return {"text": TAG.sub(replace, template), "missing": sorted(missing), "unknown": sorted(unknown)}


def prepare(session: Session, application: Application, item: FollowUp, settings: Settings, *, refresh=False):
    general = current_settings(session, settings)
    values = context_values(session, application, item, general)
    snapshot = item.template_snapshot if refresh and item.template_snapshot else general
    item.template_snapshot = {name: snapshot[name] for name in ("subject_template", "body_template", "revision", "language", "tone", "signature", "instructions")}
    item.variable_snapshot = values
    item.subject = render(snapshot["subject_template"], values)["text"]
    item.body = render(snapshot["body_template"], values)["text"]
    from app.models import FollowUpStatus, utc_now
    item.prepared_at = utc_now()
    item.status = FollowUpStatus.PREPARED
    item.approved_revision = None


def calendar_due(application: Application, general: dict, delay: int, after: datetime | None = None) -> datetime:
    zone = ZoneInfo(general["timezone"])
    start_date = after.replace(tzinfo=timezone.utc).astimezone(zone).date() if after else application.date_applied
    local = datetime.combine(start_date + timedelta(days=delay), time.fromisoformat(general["reminder_time"]), tzinfo=zone)
    return local.astimezone(timezone.utc).replace(tzinfo=None)
