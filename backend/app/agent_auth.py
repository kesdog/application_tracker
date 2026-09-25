import hashlib
import hmac
import secrets

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.models import AgentCredential, utc_now


PERMISSIONS = ("read", "create", "edit", "draft", "tasks", "interviews")
DEFAULT_PERMISSIONS = {name: name == "read" for name in PERMISSIONS}


class PermissionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read: bool = True
    create: bool = False
    edit: bool = False
    draft: bool = False
    tasks: bool = False
    interviews: bool = False


class AgentSettingsRead(BaseModel):
    configured: bool
    permissions: PermissionSettings


class AgentTokenCreated(AgentSettingsRead):
    token: str


class AgentConnectionInfo(BaseModel):
    local_mcp_command: str
    rest_endpoint: str
    mcp_transport: str
    remote_mcp_endpoint: str | None


def current_settings(session: Session) -> AgentSettingsRead:
    credential = session.get(AgentCredential, 1)
    return AgentSettingsRead(
        configured=credential is not None,
        permissions=PermissionSettings.model_validate(credential.permissions if credential else DEFAULT_PERMISSIONS),
    )


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_fingerprint(token: str) -> str:
    """Use the existing stored token hash as an idempotency namespace, never the plaintext token."""
    return _hash(token)


def regenerate(session: Session) -> AgentTokenCreated:
    token = secrets.token_urlsafe(48)
    credential = session.get(AgentCredential, 1)
    if credential is None:
        credential = AgentCredential(id=1, token_hash=_hash(token), permissions=DEFAULT_PERMISSIONS)
        session.add(credential)
    else:
        credential.token_hash = _hash(token)
        credential.updated_at = utc_now()
    session.commit()
    return AgentTokenCreated(configured=True, permissions=PermissionSettings.model_validate(credential.permissions), token=token)


def update_permissions(session: Session, permissions: PermissionSettings) -> AgentSettingsRead:
    credential = session.get(AgentCredential, 1)
    if credential is None:
        raise ValueError("Generate an agent token before configuring permissions")
    credential.permissions = permissions.model_dump()
    credential.updated_at = utc_now()
    session.commit()
    return current_settings(session)


def authorized(session: Session, token: str | None, permission: str) -> bool:
    credential = session.get(AgentCredential, 1)
    return bool(
        credential and token and hmac.compare_digest(_hash(token), credential.token_hash)
        and credential.permissions.get(permission, False)
    )


def token_valid(session: Session, token: str | None) -> bool:
    credential = session.get(AgentCredential, 1)
    return bool(credential and token and hmac.compare_digest(_hash(token), credential.token_hash))
