"""Embed WebToolbox in a pre-existing FastAPI application (not another server)."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from webtoolbox import Settings, WebToolbox


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One crawler and cache per host application lifespan; reuse from its services.
    async with WebToolbox(Settings(cache_path=Path("./data/web-cache.sqlite3"))) as web:
        app.state.webtoolbox = web
        yield


# In the host application's existing FastAPI setup, pass lifespan=lifespan.
# No webtoolbox routes or background HTTP service need to be created.
