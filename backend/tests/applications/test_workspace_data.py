from io import BytesIO
import hashlib
import json
from types import SimpleNamespace
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportBatch, MailImportReceipt, TimelineEvent


@pytest.fixture(autouse=True)
def same_origin(client):
    client.base_url = 'http://127.0.0.1:8000'
    client.headers['Origin'] = 'http://127.0.0.1:8000'


def seed(client):
    return client.post('/api/applications', json={'company': 'Example', 'job_title': 'Engineer',
        'date_applied': '2026-10-01', 'email_reference': 'Original'}).json()


def upload(client, action, data, **options):
    return client.post('/api/workspace/imports/' + action, data=options, files={'file': ('apps.csv', data, 'text/csv')})


def test_import_preview_mapping_validation_duplicates_and_replay(client):
    data = b'Company,Role,Applied,Email\nExample,Engineer,2026-10-01,Original\nOther,Designer,2026-10-02,Confirmation\nBad,,2026-10-02,Confirmation\n'
    mapping = {'Company': 'company', 'Role': 'job_title', 'Applied': 'date_applied', 'Email': 'email_reference'}
    parent = seed(client)
    preview = upload(client, 'preview', data, mapping=json.dumps(mapping))
    assert preview.status_code == 200, preview.text
    rows = preview.json()['rows']
    assert rows[0]['duplicates'] and rows[2]['errors']
    assert len(client.get('/api/applications').json()) == 1
    options = {'mapping': json.dumps(mapping), 'selected': '[2,3]', 'duplicates': 'skip'}
    first = upload(client, 'apply', data, **options)
    assert first.status_code == 200, first.text
    assert first.json()['skipped'] == 1 and len(first.json()['created']) == 1
    assert upload(client, 'apply', data, **options).json() == first.json()
    assert len(client.get('/api/applications').json()) == 2
    assert upload(client, 'apply', data, **{**options, 'selected': '[3,4]'}).status_code == 422
    assert len(client.get('/api/applications').json()) == 2
    assert upload(client, 'preview', data, mapping='[]').status_code == 422
    assert upload(client, 'preview', data, mapping='{"Company": []}').status_code == 422
    assert upload(client, 'apply', data, **{**options, 'selected': '[2,"bad"]'}).status_code == 422


def test_xlsx_import_rejects_formulas_and_handles_dates(client):
    workbook = Workbook(); sheet = workbook.active
    sheet.append(['Company', 'Job Title', 'Date Applied', 'Email Reference'])
    sheet.append(['Example', 'Engineer', '2026-10-01', 'reference'])
    output = BytesIO(); workbook.save(output)
    assert client.post('/api/workspace/imports/preview', files={'file': ('apps.xlsx', output.getvalue())}).json()['rows'][0]['errors'] == []
    sheet['A2'] = '=1+1'; output = BytesIO(); workbook.save(output)
    assert client.post('/api/workspace/imports/preview', files={'file': ('apps.xlsx', output.getvalue())}).status_code == 422


def test_exported_phone_round_trips_and_preview_keeps_original_row_numbers(client):
    data = b"Company,Job Title,Date Applied,Email Reference,Phone Number\n\nExample,Engineer,2026-10-01,Reference,'+33612345678\n"
    response = upload(client, 'preview', data)
    assert response.status_code == 200, response.text
    row = response.json()['rows'][0]
    assert row['row'] == 3 and row['errors'] == []
    assert row['application']['phone_number'] == '+33612345678'


def test_duplicate_merge_preserves_original_history_documents_and_sent_state(client):
    source, target = seed(client), seed(client)
    client.patch('/api/applications/' + source['id'], json={'description': 'Original role requirements'})
    client.post('/api/applications/' + source['id'] + '/notes', json={'content': 'Keep this note'})
    client.post('/api/applications/' + source['id'] + '/documents', data={'document_type': 'CV'}, files={'file': ('cv.txt', b'CV')})
    plan = client.get('/api/workspace/merge/preview', params={'source_id': source['id'], 'target_id': target['id']}).json()
    data = {'source_id': source['id'], 'source_revision': plan['source']['revision'], 'target_revision': plan['target']['revision'],
        'take_source_fields': ['description'], 'confirmed': True}
    assert client.post('/api/workspace/merge/' + target['id'], json={**data, 'confirmed': False}).status_code == 422
    response = client.post('/api/workspace/merge/' + target['id'], json=data)
    assert response.status_code == 200, response.text
    assert client.get('/api/applications/' + source['id']).status_code == 404
    saved = client.get('/api/applications/' + target['id']).json()
    assert saved['description'] == 'Original role requirements' and saved['followup_paused']
    work = client.get('/api/applications/' + target['id'] + '/work').json()
    assert work['notes'][0]['content'] == 'Keep this note'
    assert any(item['archived_at'] for item in work['followups'])
    document = client.get('/api/applications/' + target['id'] + '/documents').json()[0]
    assert client.get('/api/applications/' + target['id'] + '/documents/' + document['id'] + '/content').content == b'CV'
    assert client.get('/api/workspace/trash').json()['total'] == 1


def test_merge_reference_limit_is_actionable_and_rolls_back_without_losing_records(client):
    source, target = seed(client), seed(client)
    for record, value in ((source, 'a' * 1500), (target, 'b' * 1500)):
        client.patch('/api/applications/' + record['id'], json={'email_reference': value})
    plan = client.get('/api/workspace/merge/preview', params={'source_id': source['id'], 'target_id': target['id']}).json()
    result = client.post('/api/workspace/merge/' + target['id'], json={'source_id': source['id'],
        'source_revision': plan['source']['revision'], 'target_revision': plan['target']['revision'], 'confirmed': True})
    assert result.status_code == 422 and '2,048' in result.json()['detail']
    assert len(client.get('/api/applications').json()) == 2
    assert client.get('/api/workspace/trash').json()['total'] == 0


def test_trash_restore_preserves_work_and_pauses_reminders(client):
    app = seed(client); root = '/api/applications/' + app['id']
    original = client.get(root + '/work').json()
    client.delete(root)
    item = client.get('/api/workspace/trash').json()['items'][0]
    assert client.post('/api/workspace/trash/' + app['id'] + '/restore', json={'expected_revision': item['revision'] - 1}).status_code == 409
    response = client.post('/api/workspace/trash/' + app['id'] + '/restore', json={'expected_revision': item['revision']})
    assert response.status_code == 200 and response.json()['followup_paused']
    assert client.get(root + '/work').json()['followups'][0]['id'] == original['followups'][0]['id']
    assert client.get('/api/workspace/trash').json()['total'] == 0
    assert client.get('/api/workspace/trash', headers={'Authorization': 'Bearer agent'}).status_code == 403


def test_review_survives_service_state_loss_is_account_scoped_and_records_reply_choice(client):
    app = seed(client)
    account = hashlib.sha256(b'person@example.com').hexdigest()
    service = client.app.state.application_sync
    service.google = client.app.state.google = SimpleNamespace(status=lambda: {'email': 'person@example.com'})
    with Session(client.app.state.engine) as session:
        session.add(MailImportReceipt(account=account, message_id='abc1', thread_id='a', state='REVIEW', subject='Reply', reason='Review', lifecycle_applied=False))
        session.commit()
    service.account = None
    assert client.get('/api/applications/sync/status').json()['review_count'] == 1
    assert client.get('/api/workspace/mail-reviews').json()['total'] == 1
    data = {'action': 'link', 'application_id': app['id'], 'expected_revision': app['revision'], 'employer_reply': True, 'followups': 'pause'}
    assert client.post('/api/workspace/mail-reviews/abc1', json=data).status_code == 200
    assert client.get('/api/applications/' + app['id']).json()['followup_paused']
    assert client.get('/api/workspace/mail-reviews').json()['total'] == 0
    assert client.post('/api/workspace/mail-reviews/abc1', json=data).status_code == 422
    with Session(client.app.state.engine) as session:
        assert len(list(session.scalars(select(TimelineEvent).where(TimelineEvent.event_type == 'EMPLOYER_REPLY_RECORDED')))) == 1
    client.app.state.google = SimpleNamespace(status=lambda: {'email': 'other@example.com'})
    assert client.post('/api/workspace/mail-reviews/abc1', json={'action': 'ignore'}).status_code == 404


def test_backup_download_validation_and_document_corruption_leave_live_workspace_unchanged(client):
    app = seed(client)
    root = '/api/applications/' + app['id']
    client.post(root + '/documents', data={'document_type': 'CV'}, files={'file': ('cv.txt', b'Original CV')})
    backup = client.post('/api/workspace/backup')
    assert backup.status_code == 200
    validate = lambda data: client.post('/api/workspace/recovery/validate', files={'file': ('backup.zip', data)})
    result = validate(backup.content)
    assert result.status_code == 200 and result.json()['applications'] == 1, result.text
    output = BytesIO()
    with ZipFile(BytesIO(backup.content)) as original, ZipFile(output, 'w', ZIP_DEFLATED) as damaged:
        for name in original.namelist():
            damaged.writestr(name, b'Altered' if name.endswith('cv.txt') else original.read(name))
    assert validate(output.getvalue()).status_code == 422
    assert client.get(root).json()['company'] == 'Example'
    output = BytesIO()
    with ZipFile(BytesIO(backup.content)) as original, ZipFile(output, 'w', ZIP_DEFLATED) as damaged:
        metadata = json.loads(original.read('backup.json'))
        metadata['database_sha256'] = hashlib.sha256(b'not sqlite').hexdigest()
        for name in original.namelist():
            damaged.writestr(name, b'not sqlite' if name == 'tracker.sqlite3' else json.dumps(metadata) if name == 'backup.json' else original.read(name))
    assert validate(output.getvalue()).status_code == 422
    output = BytesIO()
    with ZipFile(output, 'w') as unsafe: unsafe.writestr('../outside', 'unsafe')
    assert validate(output.getvalue()).status_code == 422
