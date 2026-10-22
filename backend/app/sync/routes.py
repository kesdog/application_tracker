"""Thin human-only endpoints; agents keep their existing six permissions."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from app.sync.engine import SyncError
from app.sync.schemas import WireModel


class Initialize(WireModel):
    label: str = Field(min_length=1, max_length=100)
    recovery_export: str | None = Field(default=None, max_length=150)
    confirm_encrypted_google_storage: bool


class Resolve(WireModel):
    state: dict
    expected_heads: list[str] = Field(min_length=1, max_length=1000)


def sync_router():
    router = APIRouter(prefix='/api/sync')

    def human(request: Request):
        if request.headers.get('authorization'):
            raise HTTPException(403, 'Use the human workspace session for sync management')
        owner = request.app.state.human_access.connection_owner(request)
        if owner is None:
            raise HTTPException(401, 'Sign in to manage sync')
        return request.app.state.sync

    @router.get('/status')
    def status(engine=Depends(human)):
        return engine.status()

    @router.post('/initialize')
    def initialize(data: Initialize, engine=Depends(human)):
        if not data.confirm_encrypted_google_storage:
            raise HTTPException(422, 'Confirm storage of compact encrypted files in your Google account')
        try:
            return engine.initialize(data.label, data.recovery_export)
        except (SyncError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None

    @router.post('/run')
    def run(engine=Depends(human)):
        return engine.run(manual=True)

    @router.get('/conflicts')
    def conflicts(engine=Depends(human)):
        return engine.conflicts()

    @router.post('/conflicts/{conflict_id}/resolve')
    def resolve(conflict_id: str, data: Resolve, engine=Depends(human)):
        try:
            return engine.resolve(conflict_id, data.state, data.expected_heads)
        except ValueError:
            raise HTTPException(409, 'Resolution is invalid or the conflict changed. Refresh and review every current branch.') from None

    return router
