from sqlalchemy.orm import Session

from app.models import FollowUp, FollowUpStatus
from tests.support import save_settings


def create_application(client, **changes):
    response = client.post('/api/applications', json={
        'company': 'Example', 'job_title': 'Engineer', 'date_applied': '2026-10-01',
        'email_reference': 'Mail 123', **changes,
    })
    assert response.status_code == 201, response.text
    app = response.json()
    item = client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]
    return app, item


def change_language(client, language='fr', rewrite=False, revision=None):
    if revision is None:
        revision = client.get('/api/settings/general').json()['revision']
    return client.post('/api/settings/general/language', json={
        'language': language, 'rewrite_existing': rewrite, 'expected_revision': revision,
    })


def test_language_changes_defaults_without_replacing_existing_edits(client):
    save_settings(client, signature='Alex', instructions='Keep it brief')
    app, item = create_application(client)
    path = f"/api/applications/{app['id']}/followups/{item['id']}"
    client.patch(path, json={'body': 'My custom message'})
    response = change_language(client)
    assert response.status_code == 200, response.text
    assert response.json()['rewritten'] == 0
    assert response.json()['settings']['instructions'] == 'Keep it brief'
    assert client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]['body'] == 'My custom message'
    _, french = create_application(client, company='Second')
    assert french['subject'] == 'Suivi de ma candidature — Engineer'
    assert french['body'].startswith('Bonjour,') and french['body'].endswith('Alex')
    assert french['status'] == 'PREPARED' and french['approved_revision'] is None
    assert change_language(client, 'en').status_code == 200
    _, english = create_application(client, company='Third')
    assert english['body'].startswith('Hello,')


def test_rewrite_invalidates_approval_preserves_context_and_is_reversible(client):
    save_settings(client, signature='Alex')
    app, item = create_application(client, contact_email='hiring@example.com')
    path = f"/api/applications/{app['id']}/followups/{item['id']}"
    ready = client.patch(path, json={'body': 'Custom edit', 'status': 'READY', 'customization': {'signature': 'Sam'}}).json()
    response = change_language(client, rewrite=True)
    assert response.status_code == 200, response.text
    assert response.json()['rewritten'] == 1
    rewritten = client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]
    assert rewritten['body'].startswith('Bonjour,') and rewritten['body'].endswith('Sam')
    assert rewritten['message_language'] == 'fr'
    assert rewritten['customization'].get('language') is None
    assert rewritten['recipient_email'] == 'hiring@example.com'
    assert rewritten['due_at'] == item['due_at']
    assert rewritten['revision'] > ready['revision']
    assert rewritten['status'] == 'PREPARED' and rewritten['approved_revision'] is None
    assert rewritten['sent_at'] is None
    stale = client.patch(path, json={'expected_revision': ready['revision'], 'status': 'READY'})
    assert stale.status_code == 409
    assert client.post(f"/api/applications/{app['id']}/undo").status_code == 200
    undone = client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]
    assert undone['body'] == 'Custom edit'


def test_rewrite_skips_history_closed_phone_and_remote_content(client):
    from app.sync.models import SyncRecord
    apps = [create_application(client, company=name) for name in ('sent', 'archived', 'closed', 'phone', 'remote')]
    with Session(client.app.state.engine) as session:
        for (app, item), kind in zip(apps, ('sent', 'archived', 'closed', 'phone', 'remote')):
            row = session.get(FollowUp, item['id'])
            if kind == 'sent':
                from app.models import utc_now
                row.status = FollowUpStatus.SENT
                row.sent_at = utc_now()
            elif kind == 'archived':
                from app.models import utc_now
                row.archived_at = utc_now()
            elif kind == 'closed':
                from app.models import Application, ApplicationStatus
                session.get(Application, app['id']).status = ApplicationStatus.CLOSED
            elif kind == 'phone':
                from app.models import FollowUpChannel
                row.channel = FollowUpChannel.PHONE
            else:
                session.add(SyncRecord(key='followup:' + row.id, imported=True))
        session.commit()
    response = change_language(client, rewrite=True)
    assert response.status_code == 200, response.text
    assert response.json()['rewritten'] == 0
    with Session(client.app.state.engine) as session:
        assert all(session.get(FollowUp, item['id']).body == item['body'] for _, item in apps)


def test_language_action_rejects_stale_settings_and_unsupported_language(client):
    previous = client.get('/api/settings/general').json()
    assert change_language(client).status_code == 200
    assert change_language(client, 'en', True, previous['revision']).status_code == 409
    current = client.get('/api/settings/general').json()
    assert current['language'] == 'French'
    assert change_language(client, 'de').status_code == 422
    assert client.get('/api/settings/general').json() == current


def test_per_job_language_uses_localized_builtin_but_keeps_custom_templates(client):
    save_settings(client, signature='Alex')
    _, item = create_application(client, followup_customization={'language': 'French'})
    assert item['body'].startswith('Bonjour,')
    save_settings(client, subject_template='Custom {position_name}', body_template='Custom {signature}')
    _, custom = create_application(client, company='Custom', followup_customization={'language': 'French'})
    assert custom['subject'] == 'Custom Engineer' and custom['body'] == 'Custom Alex'


def test_switching_languages_keeps_edits_and_restores_the_saved_text_exactly(client):
    save_settings(client, signature='Alex')
    app, item = create_application(client)
    path = f"/api/applications/{app['id']}/followups/{item['id']}"
    english = client.patch(path, json={'subject': 'My English subject', 'body': 'My edited English message', 'expected_revision': item['revision']}).json()
    french = client.post(path + '/language', json={'language': 'fr', 'expected_revision': english['revision']})
    assert french.status_code == 200, french.text
    assert french.json()['message_language'] == 'fr' and french.json()['body'].startswith('Bonjour,')
    french = client.patch(path, json={'subject': 'Mon objet', 'body': 'Mon texte français', 'expected_revision': french.json()['revision']}).json()
    restored = client.post(path + '/language', json={'language': 'en', 'expected_revision': french['revision']})
    assert restored.status_code == 200, restored.text
    assert restored.json()['subject'] == 'My English subject' and restored.json()['body'] == 'My edited English message'
    versions = client.get(path + '/versions').json()
    assert versions['current_language'] == 'en'
    assert any(version['body'] == 'Mon texte français' for version in versions['versions'])
    # Changes to job data must not silently regenerate a previously saved language version.
    client.patch(f"/api/applications/{app['id']}", json={'company': 'Changed company'})
    again = client.post(path + '/language', json={'language': 'fr', 'expected_revision': restored.json()['revision']})
    assert again.status_code == 200, again.text
    assert again.json()['subject'] == 'Mon objet' and again.json()['body'] == 'Mon texte français'
    assert again.json()['status'] == 'PREPARED' and again.json()['approved_revision'] is None


def test_bulk_default_changes_skip_application_and_message_overrides(client):
    save_settings(client, signature='Alex')
    inherited_app, inherited = create_application(client, company='Inherited')
    explicit_app, explicit = create_application(client, company='Canada', followup_customization={'language': 'English'})
    message_app, message = create_application(client, company='France')
    message_path = f"/api/applications/{message_app['id']}/followups/{message['id']}"
    explicit_message = client.post(message_path + '/language', json={'language': 'en', 'expected_revision': message['revision']}).json()
    response = change_language(client, rewrite=True)
    assert response.status_code == 200, response.text
    assert response.json()['rewritten'] == 1
    assert client.get(f"/api/applications/{explicit_app['id']}/work").json()['followups'][0]['body'] == explicit['body']
    assert client.get(message_path + '/versions').json()['current_language'] == 'en'
    assert client.get(f"/api/applications/{message_app['id']}/work").json()['followups'][0]['revision'] == explicit_message['revision']
    inherited_path = f"/api/applications/{inherited_app['id']}/followups/{inherited['id']}"
    assert any(v['body'] == inherited['body'] for v in client.get(inherited_path + '/versions').json()['versions'])
    assert change_language(client, 'en', True).status_code == 200
    assert client.get(f"/api/applications/{inherited_app['id']}/work").json()['followups'][0]['body'] == inherited['body']


def test_history_restoration_is_scoped_revision_checked_and_keeps_all_versions(client):
    save_settings(client, signature='Alex')
    app, item = create_application(client)
    path = f"/api/applications/{app['id']}/followups/{item['id']}"
    original = client.get(path + '/versions').json()['versions'][0]
    edited = client.patch(path, json={'body': 'Later English edit'}).json()
    restored = client.post(path + f"/versions/{original['id']}/restore", json={'expected_revision': edited['revision']})
    assert restored.status_code == 200, restored.text
    assert restored.json()['body'] == original['body']
    versions = client.get(path + '/versions').json()['versions']
    assert any(version['body'] == 'Later English edit' for version in versions)
    assert sum(version['active'] for version in versions) == 1
    assert client.post(path + '/language', json={'language': 'fr', 'expected_revision': item['revision']}).status_code == 409
    other_app, other = create_application(client, company='Another')
    other_path = f"/api/applications/{other_app['id']}/followups/{other['id']}"
    assert client.post(other_path + f"/versions/{original['id']}/restore", json={'expected_revision': other['revision']}).status_code == 404
    assert client.get(f"/api/applications/{other_app['id']}/followups/{item['id']}/versions").status_code == 404
    current = restored.json()
    client.patch(path, json={'status': 'SENT', 'expected_revision': current['revision']})
    sent = client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]
    assert client.post(path + '/language', json={'language': 'fr', 'expected_revision': sent['revision']}).status_code == 422
    assert client.get(path + '/versions').status_code == 200


def test_agent_context_uses_email_language_and_agent_edits_are_versioned(client):
    save_settings(client, signature='Alex', language='English')
    app, item = create_application(client, followup_customization={'language': 'French'})
    path = f"/api/applications/{app['id']}/followups/{item['id']}"
    assert item['message_language'] == 'fr'
    request = client.get(path + '/ai-request').json()
    assert request['preferences']['language'] == 'French'
    response = client.post(path + '/ai-results', json={'operation_id': request['operation_id'],
        'expected_revision': request['expected_revision'], 'status': 'revised_message',
        'body': 'Texte révisé par mon agent', 'agent_name': 'Test agent'})
    assert response.status_code == 200, response.text
    versions = client.get(path + '/versions').json()['versions']
    assert any(v['body'] == item['body'] and v['language'] == 'fr' for v in versions)
    assert any(v['body'] == 'Texte révisé par mon agent' and v['language'] == 'fr' for v in versions)


def test_remote_only_followup_cannot_restore_local_versions(client):
    from app.sync.models import SyncRecord
    app, item = create_application(client)
    with Session(client.app.state.engine) as session:
        session.add(SyncRecord(key='followup:' + item['id'], imported=True)); session.commit()
    path = f"/api/applications/{app['id']}/followups/{item['id']}"
    assert client.get(path + '/versions').status_code == 422
    assert client.post(path + '/language', json={'language': 'fr', 'expected_revision': item['revision']}).status_code == 422


def test_language_versions_survive_portable_backup_restore_and_restart(tmp_path):
    from fastapi.testclient import TestClient
    from app.backup import backup_workspace, restore_workspace
    from app.config import Settings
    from app.main import create_app
    workspace, backup, restored = (tmp_path / folder for folder in ('workspace', 'backup', 'restored'))
    with TestClient(create_app(Settings(app_data_dir=workspace, _env_file=None))) as client:
        app, item = create_application(client)
        path = f"/api/applications/{app['id']}/followups/{item['id']}"
        assert client.post(path + '/language', json={'language': 'fr', 'expected_revision': item['revision']}).status_code == 200
        versions = client.get(path + '/versions').json()['versions']
    backup_workspace(workspace, backup)
    restore_workspace(backup, restored)
    with TestClient(create_app(Settings(app_data_dir=restored, _env_file=None))) as client:
        saved = client.get(path + '/versions').json()
        assert saved['current_language'] == 'fr'
        assert {(v['id'], v['language'], v['subject'], v['body']) for v in saved['versions']} == {
            (v['id'], v['language'], v['subject'], v['body']) for v in versions}
