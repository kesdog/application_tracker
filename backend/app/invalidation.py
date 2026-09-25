import asyncio
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InvalidationEvent


def publish(session: Session, topic: str, application_id: str | None) -> None:
    session.add(InvalidationEvent(topic=topic, application_id=application_id))
    session.commit()


async def stream(engine, cursor: int | None = None):
    if cursor is None:
        with Session(engine) as session:
            cursor = session.scalar(select(func.max(InvalidationEvent.id))) or 0
    yield ": connected\n\n"
    while True:
        with Session(engine) as session:
            events = list(session.scalars(select(InvalidationEvent).where(InvalidationEvent.id > cursor).order_by(InvalidationEvent.id).limit(100)))
            for event in events:
                cursor = event.id
                payload = json.dumps({"application_id": event.application_id})
                yield f"id: {event.id}\nevent: {event.topic}\ndata: {payload}\n\n"
        if not events:
            yield ": keepalive\n\n"
        await asyncio.sleep(1)
