"""Opt-in Web Push and a durable, leased outbox. Never send mail."""
import asyncio
import base64
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from app import followup_reminders
from app.followup_templates import current_settings
from app.models import PushDelivery, PushDevice, utc_now
from app.push_keys import public_key


def ready(settings):
    return bool(settings.app_push_vapid_key_file and settings.app_push_contact)


def fingerprint(settings):
    return hashlib.sha256(public_key(settings.app_push_vapid_key_file).encode()).hexdigest()


def validate_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    # Browser-owned providers only: arbitrary user URLs must never become server requests.
    provider = host in {"fcm.googleapis.com", "updates.push.services.mozilla.com"} or host.endswith((".push.apple.com", ".notify.windows.com"))
    if not provider or parsed.scheme != "https" or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.fragment or not parsed.path or any(c.isspace() for c in value):
        raise ValueError("Use an HTTPS subscription from a supported browser push provider")
    return value


def decode_key(value: str, length: int):
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("Invalid push subscription key")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        if len(raw) != length:
            raise ValueError()
        return raw
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid push subscription key") from exc


class SubscriptionKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p256dh: str = Field(max_length=100)
    auth: str = Field(max_length=32)

    @field_validator("p256dh")
    @classmethod
    def validate_public(cls, value):
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decode_key(value, 65))
        return value

    @field_validator("auth")
    @classmethod
    def validate_auth(cls, value):
        decode_key(value, 16)
        return value


class SubscriptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: SubscriptionKeys
    label: str = Field(default="This device", min_length=1, max_length=80)
    expirationTime: float | None = None

    @field_validator("endpoint")
    @classmethod
    def endpoint_valid(cls, value):
        return validate_endpoint(value)

    @field_validator("label")
    @classmethod
    def label_valid(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Choose a device name without control characters")
        return value.strip()


def require_ready(settings):
    if not ready(settings):
        raise HTTPException(503, "Phone notifications are not configured on this server")


def device_view(session, item):
    latest = session.scalar(select(PushDelivery).where(PushDelivery.device_id == item.id).order_by(PushDelivery.created_at.desc()).limit(1))
    return {"id": item.id, "label": item.label, "active": item.active, "reason": item.reason,
            "created_at": item.created_at.replace(tzinfo=timezone.utc),
            "latest": None if not latest else {"state": latest.state, "attempts": latest.attempts,
                "error": latest.last_error, "accepted_at": latest.accepted_at.replace(tzinfo=timezone.utc) if latest.accepted_at else None}}


def status(session, settings):
    devices = session.scalars(select(PushDevice).order_by(PushDevice.created_at)).all()
    if ready(settings):
        for item in devices:
            if item.key_fingerprint != fingerprint(settings):
                item.active = False
                item.reason = "Server key changed; enable this device again"
        session.commit()
    return {"configured": ready(settings), "public_key": public_key(settings.app_push_vapid_key_file) if ready(settings) else None,
            "devices": [device_view(session, item) for item in devices]}


def subscribe(session, settings, data: SubscriptionInput):
    require_ready(settings)
    session.execute(text("BEGIN IMMEDIATE"))
    hashed = hashlib.sha256(data.endpoint.encode()).hexdigest()
    item = session.scalar(select(PushDevice).where(PushDevice.endpoint_hash == hashed))
    if item is None:
        if session.scalar(select(func.count()).select_from(PushDevice)) >= 20:
            raise HTTPException(409, "Remove an old device before adding another (maximum 20)")
        item = PushDevice(endpoint_hash=hashed, endpoint=data.endpoint)
        session.add(item)
    item.keys = data.keys.model_dump()
    item.label = data.label
    item.key_fingerprint = fingerprint(settings)
    item.active = True
    item.reason = None
    session.commit()
    return device_view(session, item)


def remove(session, device_id):
    session.execute(delete(PushDelivery).where(PushDelivery.device_id == device_id))
    session.execute(delete(PushDevice).where(PushDevice.id == device_id))
    session.commit()


def test_notification(session, settings, device_id, now=None):
    require_ready(settings)
    now = now or utc_now()
    session.execute(text("BEGIN IMMEDIATE"))
    device = session.get(PushDevice, device_id)
    if not device or not device.active or device.key_fingerprint != fingerprint(settings):
        raise HTTPException(409, "Enable notifications on this device first")
    recent = session.scalar(select(PushDelivery).where(PushDelivery.device_id == device_id, PushDelivery.kind == "TEST", PushDelivery.created_at > now - timedelta(minutes=1)))
    if recent:
        raise HTTPException(429, "Wait one minute before sending another test", headers={"Retry-After": "60"})
    item = PushDelivery(device_id=device_id, batch_key="test:" + str(uuid4()), kind="TEST", notice_ids=[], next_attempt_at=now, created_at=now)
    session.add(item)
    session.commit()
    return {"id": item.id, "state": "PENDING", "message": "Test queued. Push-service acceptance does not confirm it appeared on the phone."}


def enqueue(engine, settings, now):
    if not ready(settings):
        return
    with Session(engine) as session:
        followup_reminders.synchronize(session, now)
        session.execute(text("BEGIN IMMEDIATE"))
        values = current_settings(session)
        local = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(values["timezone"]))
        if not values["notifications_enabled"] or followup_reminders.in_quiet_hours(now, values) or (values["daily_digest"] and local.strftime("%H:%M") < values["reminder_time"]):
            return
        available = followup_reminders.notices(session)
        for device in session.scalars(select(PushDevice).where(PushDevice.active.is_(True))):
            if device.key_fingerprint != fingerprint(settings):
                device.active = False
                device.reason = "Server key changed; enable this device again"
                continue
            history = session.scalars(select(PushDelivery).where(PushDelivery.device_id == device.id, PushDelivery.state != "CANCELLED")).all()
            used = {notice for delivery in history for notice in delivery.notice_ids}
            pending = [row["id"] for row in available if row["id"] not in used]
            if not pending:
                continue
            key = "digest:" + local.date().isoformat() if values["daily_digest"] else "batch:" + str(uuid4())
            previous = session.scalar(select(PushDelivery).where(PushDelivery.device_id == device.id, PushDelivery.batch_key == key))
            if previous:
                if previous.state == "CANCELLED":
                    previous.notice_ids, previous.state, previous.next_attempt_at = pending, "PENDING", now
                    previous.attempts, previous.last_error = 0, None
                continue
            session.add(PushDelivery(device_id=device.id, batch_key=key, notice_ids=pending, next_attempt_at=now, created_at=now))
        session.commit()


def claim(engine, settings, now):
    with Session(engine) as session:
        followup_reminders.synchronize(session, now)
        session.execute(text("BEGIN IMMEDIATE"))
        item = session.scalar(select(PushDelivery).where(or_(
            PushDelivery.state.in_(("PENDING", "RETRY")) & (PushDelivery.next_attempt_at <= now),
            (PushDelivery.state == "INFLIGHT") & (PushDelivery.lease_until <= now),
        )).order_by(PushDelivery.next_attempt_at, PushDelivery.id).limit(1))
        if not item:
            return None
        device = session.get(PushDevice, item.device_id)
        if not device or not device.active or device.key_fingerprint != fingerprint(settings) or item.created_at < now - timedelta(days=7):
            item.state, item.last_error = "CANCELLED", "Device unavailable or reminder expired"
            session.commit()
            return {}
        if item.kind == "TEST":
            payload = {"title": "Application Tracker", "body": "Phone notification test. Open the tracker to review your follow-ups.", "url": "/#/followups"}
        else:
            values = current_settings(session)
            local = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(values["timezone"]))
            if not values["notifications_enabled"] or followup_reminders.in_quiet_hours(now, values) or (values["daily_digest"] and local.strftime("%H:%M") < values["reminder_time"]):
                item.state, item.next_attempt_at = "RETRY", now + timedelta(minutes=1)
                item.lease_token, item.lease_until = None, None
                session.commit()
                return {}
            ids = set(item.notice_ids)
            available = [row for row in followup_reminders.notices(session) if row["id"] in ids]
            if not available:
                item.state, item.last_error = "CANCELLED", "Follow-ups no longer need a reminder"
                session.commit()
                return {}
            item.notice_ids = [row["id"] for row in available]
            url = "/#/followups"
            if len(available) == 1:
                row = available[0]
                url += f"/{row['application']['id']}/{row['followup']['id']}"
            payload = {"title": "Application Tracker", "body": f"{len(available)} follow-up{'s' if len(available) != 1 else ''} need review. Open your queue to continue.", "url": url}
        token = str(uuid4())
        item.state, item.lease_token, item.lease_until = "INFLIGHT", token, now + timedelta(minutes=2)
        item.attempts += 1
        payload["tag"] = "tracker-" + item.id
        delivery = {"id": item.id, "lease": token, "subscription": {"endpoint": device.endpoint, "keys": device.keys}, "payload": payload}
        session.commit()
        return delivery


def retry_delay(value, now):
    try:
        seconds = int(value)
    except (ValueError, TypeError):
        try:
            seconds = int((parsedate_to_datetime(value).astimezone(timezone.utc) - now.replace(tzinfo=timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            seconds = 60
    return max(60, min(86400, seconds))


def finish(engine, delivery, code, retry_after, now):
    with Session(engine) as session:
        session.execute(text("BEGIN IMMEDIATE"))
        item = session.get(PushDelivery, delivery["id"])
        if not item or item.state != "INFLIGHT" or item.lease_token != delivery["lease"]:
            return
        item.lease_token, item.lease_until, item.last_status = None, None, code
        if code and 200 <= code < 300:
            item.state, item.accepted_at, item.last_error = "ACCEPTED", now, None
        elif code in (404, 410):
            item.state, item.last_error = "FAILED", "Push subscription expired; enable this device again"
            device = session.get(PushDevice, item.device_id)
            if device:
                device.active, device.reason = False, item.last_error
        elif code is None or code in (408, 425, 429) or code >= 500:
            item.state = "RETRY" if item.attempts < 6 else "FAILED"
            item.last_error = "Temporary push-service failure" if item.state == "RETRY" else "Retry limit reached; use the in-app queue"
            delay = max(retry_delay(retry_after, now), min(21600, 60 * 2 ** min(item.attempts - 1, 8)))
            item.next_attempt_at = now + timedelta(seconds=delay)
        else:
            item.state, item.last_error = "FAILED", "Push service rejected delivery; check server configuration"
        session.commit()


def send(settings, subscription, payload):
    import requests
    from pywebpush import webpush, WebPushException

    class ProviderSession(requests.Session):
        def request(self, method, url, **kwargs):
            validate_endpoint(url)
            kwargs["allow_redirects"] = False
            return super().request(method, url, **kwargs)

    with ProviderSession() as transport:
        transport.trust_env = False
        try:
            response = webpush(subscription_info=subscription, data=json.dumps(payload),
                vapid_private_key=str(settings.app_push_vapid_key_file), vapid_claims={"sub": settings.app_push_contact},
                ttl=3600, timeout=10, headers={"Topic": hashlib.sha256(payload["tag"].encode()).hexdigest()[:32]}, requests_session=transport)
            return response.status_code, response.headers.get("Retry-After")
        except WebPushException as exc:
            response = exc.response
            return (response.status_code, response.headers.get("Retry-After")) if response is not None else (None, None)
        except requests.RequestException:
            return None, None


class PushScheduler:
    def __init__(self, engine, settings, sender=None, interval_seconds=30):
        self.engine, self.settings, self.sender = engine, settings, sender or send
        self.interval_seconds = interval_seconds
        self.stop = asyncio.Event()

    def refresh(self, now=None):
        if not ready(self.settings):
            return
        now = now or utc_now()
        enqueue(self.engine, self.settings, now)
        for _ in range(10):
            delivery = claim(self.engine, self.settings, now)
            if delivery is None:
                break
            if not delivery:
                continue
            try:
                code, retry = self.sender(self.settings, delivery["subscription"], delivery["payload"])
            except Exception:
                # Provider exceptions can include endpoint credentials; never log their text.
                code, retry = None, None
            finish(self.engine, delivery, code, retry, now)

    async def run(self):
        while not self.stop.is_set():
            try:
                await asyncio.to_thread(self.refresh)
            except Exception:
                logging.getLogger(__name__).error("Phone notification worker failed; pending work is retained")
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass
