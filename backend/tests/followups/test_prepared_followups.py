from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.followup_reminders import synchronize
from app.main import create_app
from app.models import FollowUpNotice


def settings(client, **changes):
    values = client.get('/api/settings/general').json()
    revision = values.pop('revision')
    result = client.put('/api/settings/general', json={**values, **changes, 'expected_revision': revision})
    assert result.status_code == 200, result.text
    return result.json()


def application(client, **changes):
    response = client.post('/api/applications', json={'company': 'Example', 'job_title': 'Engineer',
                          'date_applied': '2026-10-01', 'email_reference': 'Message 123', **changes})
    assert response.status_code == 201, response.text
    return response.json()


def initial(client, app):
    return client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]


def url(app, item):
    return f"/api/applications/{app['id']}/followups/{item['id']}"


def test_settings_are_persistent_and_revision_protected(tmp_path):
    config = Settings(app_data_dir=tmp_path, _env_file=None)
    with TestClient(create_app(config)) as client:
        saved = settings(client, signature='Alex', followup_delay_days=3, tone='Friendly')
        assert client.put('/api/settings/general', json={**{k: v for k, v in saved.items() if k != 'revision'}, 'expected_revision': 1}).status_code == 409
    with TestClient(create_app(config.model_copy(update={'followup_delay_days': 99}))) as client:
        assert client.get('/api/settings/general').json() == saved
        item = initial(client, application(client))
        assert item['due_at'] == '2026-10-04T07:00:00Z'
        assert item['body'].endswith('Alex')


def test_variable_registry_and_aliases_are_shared(client):
    keys = {v['key'] for v in client.get('/api/followups/variables').json()}
    assert {'company_name', 'position_name', 'contact_email', 'phone_number', 'deadline', 'requirements', 'posting_status',
            'notes', 'documents', 'tasks', 'interviews', 'signature', 'followup_number'} <= keys
    saved = settings(client, subject_template='About {company name}', body_template='Role: {job_title}', signature='Alex')
    assert saved['subject_template'] == 'About {company_name}'
    assert saved['body_template'] == 'Role: {position_name}'
    item = initial(client, application(client))
    assert item['subject'] == 'About Example' and item['body'] == 'Role: Engineer'
    result = client.post('/api/followups/preview', json={'subject': '{unknown}', 'body': '{contact_name}'})
    assert result.json()['subject']['unknown'] == ['unknown']
    assert result.json()['body']['missing'] == ['contact_name']


def test_prepare_immediately_and_calendar_days_across_dst(client):
    settings(client, signature='Alex')
    app = application(client, date_applied='2026-10-20')
    item = initial(client, app)
    assert item['status'] == 'PREPARED' and item['approved_revision'] is None
    assert item['subject'] and item['body'] and item['prepared_at']
    assert item['due_at'] == '2026-10-27T08:00:00Z'  # Paris switches from UTC+2 to UTC+1.
    assert client.get('/api/followups').json()['total'] == 1
    assert client.get(url(app, item) + '/ai-request').json()['preferences']['signature'] == 'Alex'


def test_missing_variables_block_readiness_then_save_resolves_inserted_tags(client):
    app = application(client)
    item = initial(client, app)
    assert '{signature}' in item['body']
    assert client.patch(url(app, item), json={'status': 'READY', 'expected_revision': item['revision']}).status_code == 422
    edited = client.patch(url(app, item), json={'body': 'Checking in about {company name}.\nAlex', 'expected_revision': item['revision']}).json()
    assert edited['body'] == 'Checking in about Example.\nAlex'
    ready = client.patch(url(app, item), json={'status': 'READY', 'expected_revision': edited['revision']}).json()
    assert ready['status'] == 'READY' and ready['approved_revision'] == ready['revision']
    stale = client.patch(url(app, item), json={'body': 'Stale content', 'expected_revision': edited['revision']})
    assert stale.status_code == 409
    saved = client.patch(url(app, item), json={'instructions': 'Mention the interview', 'expected_revision': ready['revision']}).json()
    assert saved['status'] == 'PREPARED' and saved['approved_revision'] is None


def test_latest_template_requires_explicit_replacement(client):
    settings(client, signature='Alex')
    app = application(client)
    before = initial(client, app)
    settings(client, body_template='New message for {company_name}.\n{signature}')
    assert initial(client, app)['body'] == before['body']
    proposed = client.get(url(app, before) + '/proposal').json()
    assert proposed['body']['text'] == 'New message for Example.\nAlex'
    applied = client.post(url(app, before) + '/apply-template', json={'expected_revision': before['revision']}).json()
    assert applied['body'] == proposed['body']['text']
    assert applied['template_snapshot']['revision'] == client.get('/api/settings/general').json()['revision']
    assert client.post(url(app, before) + '/apply-template', json={'expected_revision': before['revision']}).status_code == 409


def test_job_and_message_customization_reaches_ai_and_invalidates_ready(client):
    settings(client, signature='Alex', instructions='Keep it brief')
    app = application(client, followup_instructions='Mention Python', followup_customization={'language': 'French'})
    item = initial(client, app)
    edited = client.patch(url(app, item), json={'instructions': 'Ask about next steps', 'customization': {'tone': 'Warm'}, 'expected_revision': 1}).json()
    ready = client.patch(url(app, item), json={'status': 'READY', 'expected_revision': edited['revision']}).json()
    request = client.get(url(app, item) + '/ai-request').json()
    assert request['preferences']['language'] == 'French'
    assert request['preferences']['tone'] == 'Warm'
    assert request['preferences']['instructions'] == ['Keep it brief', 'Mention Python', 'Ask about next steps']
    assert client.patch(f"/api/applications/{app['id']}", json={'followup_instructions': 'Wait for Friday'}).status_code == 200
    current = initial(client, app)
    assert current['status'] == 'PREPARED' and current['revision'] > ready['revision']


def test_send_correction_and_undo_keep_successor_coherent(client):
    settings(client, signature='Alex')
    app = application(client)
    item = initial(client, app)
    sent = client.patch(url(app, item), json={'status': 'SENT', 'sent_at': '2026-10-09T10:00:00+02:00', 'expected_revision': 1})
    assert sent.status_code == 200, sent.text
    rows = client.get(f"/api/applications/{app['id']}/work").json()['followups']
    assert len(rows) == 2 and rows[1]['due_at'] == '2026-10-16T07:00:00Z'
    assert client.post(f"/api/applications/{app['id']}/undo").status_code == 200
    rows = client.get(f"/api/applications/{app['id']}/work").json()['followups']
    assert len(rows) == 1 and rows[0]['sent_at'] is None and rows[0]['revision'] > sent.json()['revision']
    sent = client.patch(url(app, item), json={'status': 'SENT', 'sent_at': '2026-10-10T10:00:00Z'}).json()
    correction = client.patch(url(app, item), json={'sent_at': '2026-10-11T10:00:00Z', 'expected_revision': sent['revision']})
    assert correction.status_code == 200
    rows = client.get(f"/api/applications/{app['id']}/work").json()['followups']
    assert rows[1]['due_at'] == '2026-10-18T07:00:00Z'
    assert client.post(f"/api/applications/{app['id']}/undo").status_code == 200
    rows = client.get(f"/api/applications/{app['id']}/work").json()['followups']
    assert rows[0]['sent_at'] == '2026-10-10T10:00:00Z'
    assert rows[1]['due_at'] == '2026-10-17T07:00:00Z'


def test_archiving_pausing_and_snoozing_preserve_content(client):
    settings(client, signature='Alex')
    app = application(client, date_applied='2026-01-01')
    item = initial(client, app)
    assert client.get('/api/dashboard').json()['counts']['followups_overdue'] == 1
    assert client.patch(url(app, item), json={'snoozed_until': '2099-01-01T00:00:00Z'}).status_code == 200
    assert client.get('/api/dashboard').json()['counts']['followups_overdue'] == 0
    assert client.patch(url(app, item), json={'archived': True}).status_code == 200
    assert client.get('/api/followups').json()['total'] == 0
    archived = client.get('/api/followups?archived=true').json()['items'][0]
    assert archived['body'] == item['body'] and archived['status'] == 'PREPARED'
    client.patch(url(app, item), json={'archived': False, 'snoozed_until': None})
    client.patch(f"/api/applications/{app['id']}", json={'followup_paused': True})
    assert client.get('/api/dashboard').json()['counts']['followups_overdue'] == 0
    assert client.get('/api/followups?paused=true').json()['total'] == 1


def test_notices_are_durable_and_superseded_without_duplicate_scans(client):
    settings(client, quiet_start='00:00', quiet_end='00:00')
    app = application(client, date_applied='2026-01-01')
    item = initial(client, app)
    first = client.get('/api/followups/notices').json()
    assert len(first) == 1
    assert client.get('/api/followups/notices').json() == first
    client.post(f"/api/followups/notices/{first[0]['id']}/read")
    assert client.get('/api/followups/notices').json() == []
    client.patch(url(app, item), json={'snoozed_until': '2099-01-01T00:00:00Z'})
    client.get('/api/followups/notices')
    with Session(client.app.state.engine) as session:
        old = session.get(FollowUpNotice, first[0]['id'])
        assert old.state == 'SUPERSEDED'
        assert session.scalar(select(FollowUpNotice).where(FollowUpNotice.state == 'PENDING')).due_at.year == 2099


def test_agent_import_and_revision_use_shared_preferences_and_permissions(client):
    settings(client, signature='Alex', instructions='Use the default structure')
    token = client.post('/api/settings/agent/token').json()['token']
    permissions = {'read': True, 'create': True, 'edit': True, 'draft': True, 'tasks': False, 'interviews': False}
    client.put('/api/settings/agent/permissions', json=permissions)
    headers = {'Authorization': f'Bearer {token}'}
    payload = {'application': {'company': 'Agent Example', 'job_title': 'Engineer', 'date_applied': '2026-10-01', 'email_reference': 'Mail 1'}, 'idempotency_key': 'import-1'}
    created = client.post('/api/agent/tools/create_application', headers=headers, json=payload).json()
    assert client.post('/api/agent/tools/create_application', headers=headers, json=payload).json() == created
    item = initial(client, created)
    assert len(client.get(f"/api/applications/{created['id']}/work").json()['followups']) == 1
    request = client.post('/api/agent/tools/get_followup_request', headers=headers, json={'application_id': created['id'], 'followup_id': item['id']}).json()
    assert request['preferences']['instructions'] == ['Use the default structure']
    args = {'application_id': created['id'], 'followup_id': item['id'], 'changes': {'body': 'Updated by agent', 'expected_revision': 1}}
    revised = client.post('/api/agent/tools/revise_followup', headers=headers, json=args)
    assert revised.status_code == 200 and revised.json()['status'] == 'PREPARED'
    assert client.post('/api/agent/tools/revise_followup', headers=headers, json=args).status_code == 409
    args['changes'] = {'status': 'READY', 'expected_revision': revised.json()['revision']}
    assert client.post('/api/agent/tools/revise_followup', headers=headers, json=args).status_code == 422
    args['changes'] = {'body': 'Closed job update', 'expected_revision': revised.json()['revision']}
    client.patch(f"/api/applications/{created['id']}", json={'status': 'CLOSED'})
    assert client.post('/api/agent/tools/revise_followup', headers=headers, json=args).status_code == 422


def test_simultaneous_edits_cannot_overwrite_the_same_revision(client):
    app = application(client)
    item = initial(client, app)
    def edit(body):
        return client.patch(url(app, item), json={'body': body, 'expected_revision': 1})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(edit, ['First message', 'Second message']))
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert initial(client, app)['body'] == next(r.json()['body'] for r in responses if r.status_code == 200)


def test_application_date_correction_reschedules_without_rewriting_ready_content(client):
    settings(client, signature='Alex')
    app = application(client)
    item = initial(client, app)
    client.patch(url(app, item), json={'status': 'READY', 'expected_revision': item['revision']})
    client.patch(f"/api/applications/{app['id']}", json={'date_applied': '2026-10-02'})
    current = initial(client, app)
    assert current['due_at'] == '2026-10-09T07:00:00Z'
    assert current['body'] == item['body'] and current['status'] == 'READY'
    assert current['approved_revision'] == current['revision']
    client.post(f"/api/applications/{app['id']}/undo")
    assert initial(client, app)['due_at'] == item['due_at']


def test_quiet_hours_and_concurrent_scans_keep_one_durable_notice(client):
    app = application(client, date_applied='2026-01-01')
    item = initial(client, app)
    def scan(now):
        with Session(client.app.state.engine) as session:
            synchronize(session, now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(scan, [datetime(2026, 1, 8, 21)] * 2))
    with Session(client.app.state.engine) as session:
        rows = session.scalars(select(FollowUpNotice).where(FollowUpNotice.followup_id == item['id'])).all()
        assert len(rows) == 1 and rows[0].state == 'PENDING'
        notice_id = rows[0].id
    scan(datetime(2026, 1, 9, 8))
    with Session(client.app.state.engine) as session:
        notice = session.get(FollowUpNotice, notice_id)
        assert notice.state == 'AVAILABLE'
