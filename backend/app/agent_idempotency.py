"""SQLite-backed idempotency for replayable agent create operations."""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentIdempotencyRecord, utc_now


RETENTION_DAYS = 30


class IdempotencyConflict(ValueError):
    pass


def reserve(session: Session, token_hash: str, operation: str, key: str) -> tuple[AgentIdempotencyRecord, dict | None]:
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
        if existing.result is None:
            raise IdempotencyConflict("A request with this idempotency key is still in progress")
        return existing, existing.result
    record = AgentIdempotencyRecord(
        token_hash=token_hash,
        operation=operation,
        idempotency_key=key,
        expires_at=utc_now() + timedelta(days=RETENTION_DAYS),
    )
    session.add(record)
    session.commit()
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
