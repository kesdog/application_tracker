from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
import uvicorn

from app import __version__
from app.config import Settings
from app.database import create_database


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
            yield
        finally:
            engine.dispose()

    application = FastAPI(title="Application Tracker", version=__version__, lifespan=lifespan)
    application.state.settings = settings

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
