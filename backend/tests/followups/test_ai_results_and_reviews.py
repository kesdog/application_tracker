import asyncio
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GeneralSettings, TimelineEvent
from app.config import Settings
from app.mcp_server import create_mcp_server
from tests.support import activate_agent as activate, prepare_followup as prepare, save_settings as settings


def request(client, url):
    response = client.get(url + '/ai-request')
    assert response.status_code == 200, response.text
    return response.json()


def result(req, **changes):
    return {'operation_id': req['operation_id'], 'expected_revision': req['expected_revision'],
            'status': 'revised_message', 'body': 'Hello {company_name}', 'agent_name': 'Claude', **changes}


def test_shared_request_includes_preferences_registry_notes_and_mailbox(client):
    settings(client, signature='Alex', instructions='Global guidance')
    app, item, url = prepare(client)
    client.patch(f"/api/applications/{app['id']}", json={'followup_instructions': 'Job guidance', 'followup_customization': {'tone': 'Friendly'}})
    client.patch(url, json={'instructions': 'One-off guidance', 'customization': {'language': 'French'}})
    client.post(f"/api/applications/{app['id']}/notes", json={'content': 'Evidence', 'type': 'GENERAL'})
    req = request(client, url)
    assert req['version'] == 2 and req['mailbox_reference'] == 'message-123'
    assert req['preferences'] == {'language': 'French', 'tone': 'Friendly', 'signature': 'Alex', 'instructions': ['Global guidance', 'Job guidance', 'One-off guidance']}
    assert req['notes'][0]['content'] == 'Evidence' and req['template_revision']
    assert any(v['key'] == 'requirements' for v in req['variable_registry'])
    assert 'Never send email' in req['instructions'] and 'token' not in req


def test_manual_revision_preserves_approval_boundary_audit_and_replays(client):
    app, item, url = prepare(client)
    req = request(client, url)
    payload = result(req)
    accepted = client.post(url + '/ai-results', json=payload)
    assert accepted.status_code == 200, accepted.text
    assert client.post(url + '/ai-results', json=payload).json() == accepted.json()
    updated = client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]
    assert updated['body'] == 'Hello Example' and updated['status'] == 'PREPARED' and updated['approved_revision'] is None
    assert len(client.get(url + '/ai-results').json()) == 1
    assert client.post(url + '/ai-results', json=result(req, body='Different')).status_code == 409
    timeline = client.get(f"/api/applications/{app['id']}/timeline").json()
    assert any(e['actor_type'] == 'AGENT' and e['event_type'] == 'FOLLOWUP_DRAFTED' for e in timeline['events'])
    assert client.post(f"/api/applications/{app['id']}/undo").status_code == 200
    assert client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]['body'] == item['body']


@pytest.mark.parametrize('change', ['message', 'approval', 'application', 'settings', 'note', 'closed', 'archive'])
def test_stale_context_cannot_overwrite_human_work(client, change):
    settings(client, signature='Alex')
    app, item, url = prepare(client)
    req = request(client, url)
    if change == 'message': client.patch(url, json={'body': 'Human message'})
    elif change == 'approval': client.patch(url, json={'status': 'READY'})
    elif change == 'application': client.patch(f"/api/applications/{app['id']}", json={'contact_email': 'new@example.com'})
    elif change == 'settings': settings(client, instructions='New global instructions')
    elif change == 'note': client.post(f"/api/applications/{app['id']}/notes", json={'content': 'New evidence'})
    elif change == 'closed': client.patch(f"/api/applications/{app['id']}", json={'status': 'CLOSED', 'outcome': 'UNSUCCESSFUL'})
    else: client.patch(url, json={'archived': True})
    assert client.post(url + '/ai-results', json=result(req)).status_code == 409
    assert client.get(url + '/ai-results').json() == []


def test_draft_requires_explicit_request_reports_reference_and_completes_only_task(client):
    settings(client, signature='Alex')
    app, item, url = prepare(client)
    token = activate(client)
    unauthorized = result(request(client, url), status='mailbox_draft_created', body=None, draft_reference='draft-1')
    assert client.post(url + '/ai-results', json=unauthorized).status_code == 422
    response = client.post(url + '/draft-task', json={'expected_revision': item['revision']})
    assert response.status_code == 200, response.text
    queued = response.json()
    req = request(client, url)
    assert req['allowed_action'] == 'write_mailbox_draft'
    assert json.loads(queued['description'][queued['description'].index('{'):])['operation_id'] == req['operation_id']
    payload = result(req, status='mailbox_draft_created', body=None, draft_reference='gmail:draft-1', details='Saved, not sent')
    route = '/api/agent/tools/report_followup_result'
    args = {'application_id': app['id'], 'followup_id': item['id'], 'result': payload}
    headers = {'Authorization': f'Bearer {token}'}
    accepted = client.post(route, headers=headers, json=args)
    assert accepted.status_code == 200, accepted.text
    assert client.post(route, headers=headers, json=args).json() == accepted.json()
    work = client.get(f"/api/applications/{app['id']}/work").json()
    assert work['tasks'][0]['status'] == 'COMPLETED'
    assert work['followups'][0]['status'] == 'PREPARED' and work['followups'][0]['sent_at'] is None
    client.put('/api/settings/agent/permissions', json={'read': True, 'draft': False})
    assert client.post(route, headers=headers, json=args).status_code == 403


def test_non_content_results_are_durable_and_allow_a_fresh_attempt(client):
    for status in ['skipped', 'needs_clarification', 'failure']:
        app, item, url = prepare(client)
        req = request(client, url)
        payload = result(req, status=status, body=None, details='Mailbox tools unavailable')
        assert client.post(url + '/ai-results', json=payload).status_code == 200, status
        assert client.get(url + '/ai-results').json()[0]['status'] == status
        assert request(client, url)['operation_id'] != req['operation_id']
        work = client.get(f"/api/applications/{app['id']}/work").json()
        assert work['followups'][0]['body'] == item['body'] and work['followups'][0]['status'] == 'PREPARED'


def test_concurrent_identical_results_are_recorded_once(client):
    app, item, url = prepare(client)
    payload = result(request(client, url))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(url + '/ai-results', json=payload), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert len(client.get(url + '/ai-results').json()) == 1


def sends(client, app, url, count):
    client.patch(url, json={'status': 'SENT'})
    for _ in range(count - 1):
        followup = client.post(f"/api/applications/{app['id']}/followups", json={}).json()
        assert client.patch(f"/api/applications/{app['id']}/followups/{followup['id']}", json={'status': 'SENT'}).status_code == 200


def test_review_default_settings_reply_and_undo_keep_application_open(client):
    assert client.get('/api/settings/general').json()['unsuccessful_review_after'] == 3
    app, item, url = prepare(client)
    sends(client, app, url, 3)
    review = client.get(f"/api/applications/{app['id']}/work").json()['outcome_review']
    assert review['needs_review'] and review['unanswered_sent_count'] == 3
    assert client.get('/api/followups/reviews').json()['total'] == 1
    saved = client.get(f"/api/applications/{app['id']}").json()
    assert saved['status'] == 'SUBMITTED' and saved['outcome'] is None
    settings(client, unsuccessful_review_after=4)
    assert client.get('/api/followups/reviews').json()['total'] == 0
    settings(client, unsuccessful_review_after=0)
    assert client.get('/api/followups/reviews').json()['total'] == 0
    settings(client, unsuccessful_review_after=3)
    client.post(f"/api/applications/{app['id']}/notes", json={'content': 'Generic note'})
    assert client.get('/api/followups/reviews').json()['total'] == 1
    client.post(f"/api/applications/{app['id']}/notes", json={'content': 'Employer acknowledged application', 'employer_reply': True})
    assert client.get('/api/followups/reviews').json()['total'] == 0
    assert client.get(f"/api/applications/{app['id']}/work").json()['outcome_review']['unanswered_sent_count'] == 0


def test_reviews_skip_interview_and_closed_jobs_and_clear_when_send_is_reopened(client):
    app, item, url = prepare(client)
    sends(client, app, url, 3)
    client.patch(url, json={'status': 'PREPARED'})
    assert client.get('/api/followups/reviews').json()['total'] == 0
    client.patch(url, json={'status': 'SENT'})
    client.patch(f"/api/applications/{app['id']}", json={'status': 'INTERVIEW'})
    assert client.get('/api/followups/reviews').json()['total'] == 0
    client.patch(f"/api/applications/{app['id']}", json={'status': 'CLOSED', 'outcome': 'UNSUCCESSFUL'})
    assert client.get('/api/followups/reviews').json()['total'] == 0


def test_existing_settings_get_new_default_without_overwriting_template(client):
    settings(client, signature='Original', unsuccessful_review_after=8)
    with Session(client.app.state.engine) as session:
        saved = session.get(GeneralSettings, 1)
        values = dict(saved.values)
        values.pop('unsuccessful_review_after')
        saved.values = values
        session.commit()
    values = client.get('/api/settings/general').json()
    assert values['signature'] == 'Original' and values['unsuccessful_review_after'] == 3
    assert client.put('/api/settings/general', json={**{k:v for k,v in values.items() if k != 'revision'}, 'unsuccessful_review_after': -1}).status_code == 422


def test_mcp_uses_shared_request_and_result_contract(client, tmp_path, monkeypatch):
    app, item, url = prepare(client)
    token = activate(client)
    monkeypatch.setenv('APPLICATION_TRACKER_AGENT_TOKEN', token)
    server = create_mcp_server(Settings(app_data_dir=tmp_path, _env_file=None))
    tools = asyncio.run(server.list_tools())
    tool = next(t for t in tools if t.name == 'report_followup_result')
    assert 'result' in tool.inputSchema['properties']
    async def call(name, arguments):
        return await server.call_tool(name, arguments)
    args = {'application_id': app['id'], 'followup_id': item['id']}
    blocks = asyncio.run(call('get_followup_request', args))
    # FastMCP returns content blocks plus structured content on recent versions.
    text_blocks = blocks[0] if isinstance(blocks, tuple) else blocks
    req = json.loads(next(b.text for b in text_blocks if hasattr(b, 'text')))
    assert req['operation_id'] == request(client, url)['operation_id']
    asyncio.run(call('report_followup_result', {**args, 'result': result(req)}))
    saved = client.get(url + '/ai-results').json()
    assert saved[0]['reported_by'] == 'AGENT'


def test_report_cannot_claim_send_or_approval_and_rejects_foreign_child(client):
    app, item, url = prepare(client)
    req = request(client, url)
    assert client.post(url + '/ai-results', json=result(req, status='SENT')).status_code == 422
    assert client.post(url + '/ai-results', json={**result(req), 'approved_revision': 2}).status_code == 422
    other, _, _ = prepare(client)
    assert client.post(f"/api/applications/{other['id']}/followups/{item['id']}/ai-results", json=result(req)).status_code == 404


def test_failed_draft_stops_task_and_new_explicit_request_uses_new_operation(client):
    settings(client, signature='Alex')
    app, item, url = prepare(client)
    activate(client)
    first = client.post(url + '/draft-task', json={'expected_revision': item['revision']}).json()
    req = request(client, url)
    failed = client.post(url + '/ai-results', json=result(req, status='failure', body=None, details='Could not confirm an external draft. Reconcile before retrying.'))
    assert failed.status_code == 200
    assert client.get(f"/api/applications/{app['id']}/work").json()['tasks'][0]['status'] == 'CANCELLED'
    second = client.post(url + '/draft-task', json={'expected_revision': item['revision']}).json()
    assert second['id'] != first['id']
    assert request(client, url)['operation_id'] != req['operation_id']
