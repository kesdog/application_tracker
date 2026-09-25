import asyncio
import hashlib

from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.mcp_server import create_mcp_http_app, create_mcp_server
from app.models import AgentCredential, InvalidationEvent
from app import invalidation


@pytest.fixture
def setup(tmp_path):
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    app = create_app(settings)
    with TestClient(app) as client:
        yield client, app, settings


def agent_call(client, token, operation, payload=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post(f"/api/agent/tools/{operation}", json=payload or {}, headers=headers)


def draft(company="Agent Example"):
    return {"job_title": "Engineer", "company": company, "date_applied": "2026-09-25", "job_url": "https://example.com/job"}


def test_token_only_shown_once_and_rotation_revokes_old_token(setup):
    client, app, _ = setup
    assert agent_call(client, None, "list_applications").status_code == 401
    first = client.post("/api/settings/agent/token").json()["token"]
    assert client.get("/api/settings/agent").json()["configured"] is True
    assert "token" not in client.get("/api/settings/agent").json()
    with Session(app.state.engine) as session:
        credential = session.get(AgentCredential, 1)
        assert credential.token_hash == hashlib.sha256(first.encode()).hexdigest()
        assert first not in str(credential.__dict__)
    assert agent_call(client, first, "list_applications").status_code == 200
    second = client.post("/api/settings/agent/token").json()["token"]
    assert second != first
    assert agent_call(client, first, "list_applications").status_code == 401
    assert agent_call(client, second, "list_applications").status_code == 200


def test_permission_enforcement_and_delete_forbidden(setup):
    client, _, _ = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    permissions = {"read": True, "create": False, "edit": False, "draft": False, "tasks": False, "interviews": False}
    assert client.put("/api/settings/agent/permissions", json=permissions).status_code == 200
    assert agent_call(client, token, "list_applications").status_code == 200
    assert agent_call(client, token, "create_application", {"application": draft()}).status_code == 403
    assert agent_call(client, token, "delete_application", {"application_id": "x"}).status_code == 404
    assert client.delete("/api/agent/applications/x", headers={"Authorization": f"Bearer {token}"}).status_code in {404, 405}
    permissions["create"] = True
    client.put("/api/settings/agent/permissions", json=permissions)
    created = agent_call(client, token, "create_application", {"application": draft()})
    assert created.status_code == 200
    application_id = created.json()["id"]
    assert agent_call(client, token, "update_application", {"application_id": application_id, "changes": {"company": "Changed"}}).status_code == 403
    assert agent_call(client, token, "create_task", {"application_id": application_id, "task": {"title": "Call"}}).status_code == 403
    assert agent_call(client, token, "create_note", {"application_id": application_id, "note": {"content": "Draft"}}).status_code == 403


def test_mcp_and_rest_use_same_service_and_mcp_checks_revocation(setup):
    client, _, settings = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    permissions = {"read": True, "create": True, "edit": False, "draft": False, "tasks": False, "interviews": False}
    assert client.put("/api/settings/agent/permissions", json=permissions).status_code == 200
    rest = agent_call(client, token, "create_application", {"application": draft("REST Company")}).json()
    server = create_mcp_server(settings, token)

    async def call(name, payload):
        return await server.call_tool(name, payload)

    mcp_created = asyncio.run(call("create_application", {"application": draft("MCP Company")}))
    assert mcp_created
    all_records = agent_call(client, token, "list_applications").json()["items"]
    assert {item["company"] for item in all_records} == {"REST Company", "MCP Company"}
    assert rest["status"] == next(item["status"] for item in all_records if item["company"] == "MCP Company")
    client.post("/api/settings/agent/token")
    with pytest.raises(ToolError, match="INVALID_TOKEN"):
        asyncio.run(call("list_applications", {}))


def test_sse_event_after_agent_mutation_contains_only_refetch_id(setup):
    client, app, _ = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    permissions = {"read": True, "create": True, "edit": False, "draft": False, "tasks": False, "interviews": False}
    assert client.put("/api/settings/agent/permissions", json=permissions).status_code == 200
    created = agent_call(client, token, "create_application", {"application": draft()}).json()
    with Session(app.state.engine) as session:
        event = session.scalar(select(InvalidationEvent).order_by(InvalidationEvent.id.desc()))
        assert event.topic == "application.created"
        assert event.application_id == created["id"]

    async def read_event():
        stream = invalidation.stream(app.state.engine, cursor=0)
        await anext(stream)
        message = await anext(stream)
        await stream.aclose()
        return message

    message = asyncio.run(read_event())
    assert "event: application.created" in message
    assert created["id"] in message
    assert "Agent Example" not in message
    assert "job_title" not in message


def test_agent_phone_uses_same_validation_and_followup_channels(setup):
    client, _, _ = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    permissions = {"read": True, "create": True, "edit": True, "draft": True, "tasks": False, "interviews": False}
    assert client.put("/api/settings/agent/permissions", json=permissions).status_code == 200
    invalid = agent_call(client, token, "create_application", {"application": {**draft(), "phone_number": "12345"}})
    assert invalid.status_code == 422
    created = agent_call(client, token, "create_application", {"application": {**draft(), "phone_number": "06 12 34 56 78"}})
    assert created.status_code == 200
    assert created.json()["phone_number"] == "+33612345678"
    application_id = created.json()["id"]
    updated = agent_call(client, token, "update_application", {"application_id": application_id, "changes": {"phone_number": "+44 20 8366 1177"}})
    assert updated.status_code == 200
    assert updated.json()["phone_number"] == "+442083661177"
    followup = agent_call(client, token, "create_followup", {"application_id": application_id, "followup": {"channel": "BOTH"}})
    assert followup.status_code == 200
    assert followup.json()["channel"] == "BOTH"


def test_agent_compact_list_is_paginated_and_keeps_filters_stable(setup):
    client, _, _ = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    permissions = {"read": True, "create": True, "edit": False, "draft": False, "tasks": False, "interviews": False}
    client.put("/api/settings/agent/permissions", json=permissions)
    created = [agent_call(client, token, "create_application", {"application": draft(f"Page {number}")}).json() for number in range(3)]

    first = agent_call(client, token, "list_applications", {"limit": 2}).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"]
    assert "description" not in first["items"][0]
    second = agent_call(client, token, "list_applications", {"limit": 2, "cursor": first["next_cursor"]}).json()
    assert len(second["items"]) == 1
    assert {item["id"] for item in first["items"] + second["items"]} == {item["id"] for item in created}
    assert agent_call(client, token, "search_applications", {"filters": {"company": "Page 1"}, "limit": 1}).json()["items"][0]["company"] == "Page 1"
    assert agent_call(client, token, "search_applications", {"filters": {"company": "Missing"}}).json() == {"items": [], "next_cursor": None}


def test_agent_application_context_contains_related_records_and_requires_read_access(setup):
    client, _, _ = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    permissions = {"read": True, "create": True, "edit": False, "draft": True, "tasks": True, "interviews": True}
    client.put("/api/settings/agent/permissions", json=permissions)
    application = agent_call(client, token, "create_application", {"application": draft("Context")}).json()
    application_id = application["id"]
    empty = agent_call(client, token, "get_application_context", {"application_id": application_id})
    assert empty.status_code == 200
    assert empty.json()["notes"] == [] and empty.json()["tasks"] == [] and empty.json()["documents"] == []
    agent_call(client, token, "create_note", {"application_id": application_id, "note": {"content": "Context note"}})
    agent_call(client, token, "create_task", {"application_id": application_id, "task": {"title": "Context task"}})
    agent_call(client, token, "create_followup", {"application_id": application_id, "followup": {}})
    agent_call(client, token, "create_interview", {"application_id": application_id, "interview": {"type": "TECHNICAL", "scheduled_at": "2026-10-01T10:00:00Z"}})
    document = client.post(f"/api/applications/{application_id}/documents", data={"document_type": "CV", "filename": "cv.pdf", "external_reference": "file:///cv.pdf"})
    assert document.status_code == 201
    context = agent_call(client, token, "get_application_context", {"application_id": application_id})
    assert context.status_code == 200
    assert context.json()["application"]["id"] == application_id
    assert len(context.json()["notes"]) == len(context.json()["tasks"]) == len(context.json()["followups"]) == len(context.json()["interviews"]) == len(context.json()["documents"]) == 1
    assert context.json()["recent_timeline"]
    assert agent_call(client, token, "get_application_context", {"application_id": "missing"}).status_code == 404
    client.put("/api/settings/agent/permissions", json={**permissions, "read": False})
    assert agent_call(client, token, "get_application_context", {"application_id": application_id}).status_code == 403


def test_agent_create_idempotency_replays_persisted_result_and_scopes_keys(setup):
    client, app, settings = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    permissions = {"read": True, "create": True, "edit": False, "draft": True, "tasks": False, "interviews": False}
    client.put("/api/settings/agent/permissions", json=permissions)
    first = agent_call(client, token, "create_application", {"application": draft("Idempotent"), "idempotency_key": "application-1"})
    retry = agent_call(client, token, "create_application", {"application": draft("Changed payload"), "idempotency_key": "application-1"})
    assert first.status_code == retry.status_code == 200
    assert retry.json() == first.json()
    assert agent_call(client, token, "list_applications").json()["items"].__len__() == 1
    note = agent_call(client, token, "create_note", {"application_id": first.json()["id"], "note": {"content": "Same key, other operation"}, "idempotency_key": "application-1"})
    assert note.status_code == 200
    second = agent_call(client, token, "create_application", {"application": draft("Different key"), "idempotency_key": "application-2"})
    assert second.status_code == 200

    # A new application process uses the stored SQLite replay result.
    with TestClient(create_app(settings)) as restarted:
        replay = agent_call(restarted, token, "create_application", {"application": draft("After restart"), "idempotency_key": "application-1"})
        assert replay.status_code == 200
        assert replay.json()["id"] == first.json()["id"]


def test_agent_errors_have_stable_payloads(setup):
    client, _, _ = setup
    no_token = agent_call(client, None, "list_applications")
    assert no_token.status_code == 401
    assert no_token.json()["error"]["code"] == "INVALID_TOKEN"
    token = client.post("/api/settings/agent/token").json()["token"]
    denied = agent_call(client, token, "create_application", {"application": draft()})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "PERMISSION_DENIED"
    client.put("/api/settings/agent/permissions", json={"read": True, "create": True, "edit": False, "draft": False, "tasks": False, "interviews": False})
    invalid = agent_call(client, token, "create_application", {"application": {**draft(), "job_url": None, "email_reference": None}})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "SOURCE_REQUIRED"
    posting = agent_call(client, token, "create_application", {"application": {**draft(), "job_url": None, "email_reference": "Application confirmation", "source": "LINKEDIN"}})
    assert posting.status_code == 422
    assert posting.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "exact job URL" in posting.json()["error"]["message"]


def test_mcp_tracker_info_and_streamable_http_share_bearer_auth(setup):
    client, _, settings = setup
    token = client.post("/api/settings/agent/token").json()["token"]
    server = create_mcp_server(settings, token)

    async def call(name, payload):
        return await server.call_tool(name, payload)

    info = asyncio.run(call("get_tracker_info", {}))
    assert "application_version" in str(info)
    assert "mcp_transport" in str(info)
    with TestClient(create_mcp_http_app(settings), base_url="http://127.0.0.1") as http_client:
        assert http_client.post("/mcp").status_code == 401
        # A valid bearer passes the transport guard; the MCP protocol may then
        # reject this intentionally incomplete handshake request.
        assert http_client.post("/mcp", headers={"Authorization": f"Bearer {token}"}).status_code != 401
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json", "Host": "127.0.0.1:8001"}
        initialized = http_client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "test", "version": "1"}},
        })
        assert initialized.status_code == 200
        session_id = initialized.headers["mcp-session-id"]
        info = http_client.post("/mcp", headers={**headers, "mcp-session-id": session_id}, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_tracker_info", "arguments": {}},
        })
        assert info.status_code == 200
        assert "application_version" in info.text


def test_settings_expose_only_configured_agent_connection_details(setup):
    client, _, settings = setup
    local = client.get("/api/settings/agent/connection").json()
    assert local == {
        "local_mcp_command": "application-tracker-mcp",
        "rest_endpoint": "http://127.0.0.1:8000/api/agent/",
        "mcp_transport": "stdio",
        "remote_mcp_endpoint": None,
    }
    remote_settings = settings.model_copy(update={"mcp_transport": "streamable-http", "mcp_host": "127.0.0.1", "mcp_port": 8123})
    with TestClient(create_app(remote_settings)) as remote_client:
        assert remote_client.get("/api/settings/agent/connection").json()["remote_mcp_endpoint"] == "http://127.0.0.1:8123/mcp"
