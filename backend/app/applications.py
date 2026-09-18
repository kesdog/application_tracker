from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application
from app.schemas import ApplicationCreate


def create_application(session: Session, data: ApplicationCreate) -> Application:
    application = Application(**data.model_dump())
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def list_applications(session: Session) -> list[Application]:
    return list(session.scalars(select(Application).order_by(Application.date_applied.desc(), Application.id)))
