from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.config import Settings
from app.work import create_followup
from app.work_schemas import FollowUpCreate


def create_application(client, **extra):
    response = client.post('/api/applications', json={
        'job_title': 'Engineer', 'company': 'Example', 'date_applied': '2026-09-24',
        'email_reference': 'Message 123', **extra,
    })
    assert response.status_code == 201
    return f"/api/applications/{response.json()['id']}"


@pytest.fixture
def path(client):
    return create_application(client)


def test_followup_defaults_sequences_and_unlimited_manual_creation(client, path):
    before = datetime.now(timezone.utc)
    automatic = client.get(path + '/work').json()['followups']
    assert len(automatic) == 1 and automatic[0]['is_automatic'] is True
    assert automatic[0]['due_at'] == '2026-10-01T07:00:00Z'  # 09:00 Europe/Paris
    records = [client.post(path + '/followups', json={}).json() for _ in range(4)]
    assert [item['sequence_number'] for item in records] == [2, 3, 4, 5]
    assert all(item['status'] == 'PREPARED' and item['sent_at'] is None for item in records)
    assert all(item['channel'] == 'EMAIL' for item in records)
    due = datetime.fromisoformat(records[0]['due_at'])
    assert before + timedelta(days=7) <= due <= datetime.now(timezone.utc) + timedelta(days=7)
    other = create_application(client)
    assert client.post(other + '/followups', json={}).json()['sequence_number'] == 2
    assert client.get(path + '/work').json()['followups'] == automatic + records


def test_phone_and_both_followups_require_application_phone(client, path):
    assert client.post(path + '/followups', json={'channel': 'PHONE'}).status_code == 422
    assert client.patch(path, json={'phone_number': '+33 6 12 34 56 78'}).status_code == 200
    phone = client.post(path + '/followups', json={'channel': 'PHONE'})
    both = client.post(path + '/followups', json={'channel': 'BOTH'})
    assert phone.status_code == both.status_code == 201
    assert phone.json()['channel'] == 'PHONE'
    assert both.json()['channel'] == 'BOTH'


def test_followup_drafted_sent_cancelled_and_timestamp(client, path):
    response = client.post(path + '/followups', json={'due_at': '2026-09-28T12:00:00Z', 'template_reference': 'First reminder'})
    assert response.status_code == 201
    item = response.json()
    url = path + '/followups/' + item['id']
    drafted = client.patch(url, json={'status': 'DRAFTED'}).json()
    assert drafted['status'] == 'PREPARED'
    assert drafted['sent_at'] is None
    sent = client.patch(url, json={'status': 'SENT'}).json()
    assert sent['sent_at'].endswith('Z')
    assert client.patch(url, json={'status': 'SENT'}).json()['sent_at'] == sent['sent_at']
    cancelled = client.patch(url, json={'status': 'CANCELLED'}).json()
    assert cancelled['status'] == 'PREPARED' and cancelled['archived_at'] is not None and cancelled['sent_at'] is None
    assert client.patch(url, json={'template_reference': None}).json()['template_reference'] is None
    assert client.get(path).json()['status'] == 'SUBMITTED'


def test_overrides_and_global_settings(client, path, monkeypatch):
    defaults = client.get(path + '/work').json()
    assert defaults['followup_delay_days'] == 7 and defaults['max_followup_suggestions'] == 2
    assert client.patch(path, json={'followup_delay_days': 0, 'max_followup_suggestions': 0}).status_code == 200
    overridden = client.get(path + '/work').json()
    assert overridden['followup_delay_days'] == 0 and overridden['max_followup_suggestions'] == 0
    before = datetime.now(timezone.utc)
    followup = client.post(path + '/followups', json={})
    assert followup.status_code == 201
    assert before <= datetime.fromisoformat(followup.json()['due_at']) <= datetime.now(timezone.utc)
    assert client.patch(path, json={'followup_delay_days': None, 'max_followup_suggestions': None}).status_code == 200
    assert client.get(path + '/work').json()['followup_delay_days'] == 7
    assert client.patch(path, json={'followup_delay_days': -1}).status_code == 422
    monkeypatch.setenv('FOLLOWUP_DELAY_DAYS', '3')
    monkeypatch.setenv('MAX_FOLLOWUP_SUGGESTIONS', '0')
    config = Settings(_env_file=None)
    assert config.followup_delay_days == 3 and config.max_followup_suggestions == 0


def test_automatic_followups_reschedule_and_repeat_until_the_limit(client, path):
    initial = client.get(path + '/work').json()['followups'][0]
    assert initial['is_automatic'] is True and initial['sequence_number'] == 1
    assert client.patch(path, json={'followup_delay_days': 3}).status_code == 200
    rescheduled = client.get(path + '/work').json()['followups'][0]
    assert rescheduled['due_at'] == '2026-09-27T07:00:00Z'
    sent = client.patch(path + '/followups/' + initial['id'], json={'status': 'SENT'}).json()
    assert sent['status'] == 'SENT'
    automatic = [item for item in client.get(path + '/work').json()['followups'] if item['is_automatic']]
    assert [item['sequence_number'] for item in automatic] == [1, 2]
    assert automatic[1]['status'] == 'PREPARED'


def test_simultaneous_followups_get_unique_sequences(client, path):
    def create_one(_):
        with Session(client.app.state.engine) as session:
            return create_followup(session, path.rsplit('/', 1)[1], FollowUpCreate(), client.app.state.settings).sequence_number
    with ThreadPoolExecutor(max_workers=4) as executor:
        sequences = list(executor.map(create_one, range(6)))
    assert sorted(sequences) == [2, 3, 4, 5, 6, 7]
