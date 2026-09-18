from contextlib import asynccontextmanager
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import uvicorn

from app import __version__
from app.config import Settings
from app.database import create_database, migrate_database
from app import applications
from app.schemas import ApplicationCreate, ApplicationRead, ApplicationUpdate


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine = create_database(settings.app_data_dir)
        application.state.engine = engine
        try:
            migrate_database(engine)
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Application Tracker", version=__version__, lifespan=lifespan)
    application.state.settings = settings

    @application.exception_handler(applications.ApplicationNotFound)
    async def not_found(_request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @application.exception_handler(applications.InvalidApplication)
    async def invalid_application(_request, exc):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    def get_session():
        with Session(application.state.engine) as session:
            yield session

    @application.post("/api/applications", response_model=ApplicationRead, status_code=201)
    def create_application(data: ApplicationCreate, session: Session = Depends(get_session)):
        return applications.create_application(session, data)

    @application.get("/api/applications", response_model=list[ApplicationRead])
    def list_applications(session: Session = Depends(get_session)):
        return applications.list_applications(session)

    @application.get("/api/applications/{application_id}", response_model=ApplicationRead)
    def get_application(application_id: str, session: Session = Depends(get_session)):
        return applications.get_application(session, application_id)

    @application.patch("/api/applications/{application_id}", response_model=ApplicationRead)
    def update_application(application_id: str, data: ApplicationUpdate, session: Session = Depends(get_session)):
        return applications.update_application(session, application_id, data)

    @application.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        try:
            with application.state.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
        except SQLAlchemyError as exc:
            logging.getLogger(__name__).exception("Database health check failed")
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return HealthResponse(status="ok", version=__version__, database="connected")

    return application


app = create_app()


def run() -> None:
    settings = Settings()
    uvicorn.run(app, host=settings.app_host, port=settings.app_port, log_level=settings.log_level)


if __name__ == "__main__":
    run()
