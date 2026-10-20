"""Two independent MCP clients share authority and reject stale mutations."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.main import create_app
from app.mcp_server import create_mcp_server
from app.models import AuditEntry, AgentCredential


def value(server, operation, args):
    return json.loads(asyncio.run(server.call_tool(operation, args))[0].text)


def test_two_clients_exchange_updates_conflict_and_share_live_permission_changes(tmp_path):
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    app = create_app(settings)
    with TestClient(app) as client:
        token = client.post('/api/settings/agent/token').json()['token']
        enabled = {key: True for key in ('read', 'create', 'edit', 'draft', 'tasks', 'interviews')}
        client.put('/api/settings/agent/permissions', json=enabled)
        alice, bob = create_mcp_server(settings, token), create_mcp_server(settings, token)
        from app.agent_ops import PERMISSION_FOR
        for tool in asyncio.run(alice.list_tools()):
            if PERMISSION_FOR[tool.name] != 'read':
                assert 'idempotency_key' in tool.inputSchema['properties'], tool.name
        created = value(alice, 'create_application', {'application': {'job_title': 'Engineer', 'company': 'One', 'date_applied': '2026-10-18', 'email_reference': 'mail'}})
        current = value(bob, 'get_application', {'application_id': created['id']})
        assert current['revision'] == created['revision'] == 1

        def edit(server, proposed):
            try:
                return value(server, 'update_application', {'application_id': created['id'], 'changes': {'company': proposed, 'expected_revision': current['revision']}})
            except ToolError as exc:
                return json.loads(str(exc)[str(exc).index('{'):])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda pair: edit(*pair), [(alice, 'Alice proposal'), (bob, 'Bob proposal')]))
        accepted = [result for result in results if 'error' not in result]
        conflicts = [result['error'] for result in results if 'error' in result]
        assert len(accepted) == len(conflicts) == 1
        assert conflicts[0]['code'] == 'REVISION_CONFLICT'
        assert conflicts[0]['details']['proposed']['company'] != accepted[0]['company']
        assert conflicts[0]['details']['current']['company'] == accepted[0]['company']
        latest = value(bob, 'get_application', {'application_id': created['id']})
        assert latest['revision'] == 2
        updated = value(bob, 'update_application', {'application_id': created['id'], 'changes': {'location': 'Paris', 'expected_revision': 2}, 'idempotency_key': 'bob-location'})
        assert value(alice, 'get_application', {'application_id': created['id']})['location'] == 'Paris'
        assert value(bob, 'update_application', {'application_id': created['id'], 'changes': {'location': 'Paris', 'expected_revision': 2}, 'idempotency_key': 'bob-location'}) == updated
        client.put('/api/settings/agent/permissions', json={**enabled, 'edit': False, 'read': False})
        for server in (alice, bob):
            for operation, args in [('list_applications', {}), ('update_application', {'application_id': created['id'], 'changes': {'company': 'Denied', 'expected_revision': 3}})]:
                with pytest.raises(ToolError, match='PERMISSION_DENIED'):
                    value(server, operation, args)
        client.put('/api/settings/agent/permissions', json=enabled)
        assert value(alice, 'list_applications', {})['items'][0]['revision'] == 3
        client.post('/api/settings/agent/token')
        for server in (alice, bob):
            with pytest.raises(ToolError, match='INVALID_TOKEN'):
                value(server, 'list_applications', {})
        assert client.get('/api/applications').json()[0]['company'] == accepted[0]['company']
        with Session(app.state.engine) as session:
            assert len(list(session.scalars(select(AgentCredential)))) == 1


def test_rest_preconditions_payload_bound_retry_and_unverified_audit_labels(client):
    token = client.post('/api/settings/agent/token').json()['token']
    client.put('/api/settings/agent/permissions', json={'read': True, 'create': True, 'edit': True})
    request_id = str(uuid4())
    headers = {'Authorization': 'Bearer ' + token, 'X-Tracker-Request-Id': request_id, 'X-Tracker-Client': 'claude'}
    payload = {'application': {'company': 'Example', 'job_title': 'Engineer', 'date_applied': '2026-10-18', 'email_reference': 'mail'}}
    created = client.post('/api/agent/tools/create_application', json=payload, headers=headers)
    assert created.status_code == 200
    assert created.headers['x-tracker-request-id'] == request_id
    assert client.post('/api/agent/tools/create_application', json=payload, headers=headers).json() == created.json()
    assert client.post('/api/agent/tools/create_application', json={'application': {**payload['application'], 'company': 'Changed'}}, headers=headers).status_code == 409
    body_id = str(uuid4())
    body_request = client.post('/api/agent/tools/create_application', json={'application': {**payload['application'], 'company': 'Body request'}, 'request_id': body_id}, headers={'Authorization': 'Bearer ' + token})
    assert body_request.status_code == 200 and body_request.headers['x-tracker-request-id'] == body_id
    timeline = client.get(f"/api/applications/{created.json()['id']}/timeline").json()['events']
    event = next(event for event in timeline if event['event_type'] == 'APPLICATION_CREATED')
    assert event['metadata']['agent_call'] == {'request_id': request_id, 'client_label': 'claude', 'client_label_verified': False}
    path = '/api/agent/tools/update_application'
    assert client.post(path, json={'application_id': created.json()['id'], 'changes': {'company': 'Missing precondition'}}, headers={'Authorization': 'Bearer ' + token}).status_code == 422
    human_path = '/api/applications/' + created.json()['id']
    assert client.patch(human_path, json={'company': 'Human', 'expected_revision': 1}).status_code == 200
    conflict = client.patch(human_path, json={'company': 'Stale', 'expected_revision': 1})
    assert conflict.status_code == 409 and conflict.json()['proposed']['company'] == 'Stale'
    assert conflict.json()['current']['company'] == 'Human'
