"""SQLite-backed idempotency for replayable agent create operations."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import AgentIdempotencyRecord, utc_now


RETENTION_DAYS = 30


class IdempotencyConflict(ValueError):
    pass


def reserve(session: Session, token_hash: str, operation: str, key: str, request_hash: str | None = None) -> tuple[AgentIdempotencyRecord, dict | None]:
    existing = session.scalar(select(AgentIdempotencyRecord).where(
        AgentIdempotencyRecord.token_hash == token_hash,
        AgentIdempotencyRecord.operation == operation,
        AgentIdempotencyRecord.idempotency_key == key,
    ))
    if existing and existing.expires_at <= utc_now():
        session.delete(existing)
        session.commit()
        existing = None
    if existing:
        if existing.request_hash and existing.request_hash != request_hash:
            raise IdempotencyConflict('This idempotency key was used for different arguments. Review the original request before retrying.')
        if existing.result is None:
            raise IdempotencyConflict("A request with this idempotency key is still in progress")
        return existing, existing.result
    record = AgentIdempotencyRecord(
        token_hash=token_hash,
        operation=operation,
        idempotency_key=key,
        request_hash=request_hash,
        expires_at=utc_now() + timedelta(days=RETENTION_DAYS),
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise IdempotencyConflict('This request was already reserved. Retry with the same key and arguments.') from None
    return record, None


def complete(session: Session, record: AgentIdempotencyRecord, result: dict) -> None:
    record.result = result
    session.commit()


def abandon(session: Session, record: AgentIdempotencyRecord) -> None:
    session.rollback()
    current = session.get(AgentIdempotencyRecord, record.id)
    if current is not None and current.result is None:
        session.delete(current)
        session.commit()
