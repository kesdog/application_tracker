"""Draft receipts must preserve edits made while a mailbox write is in flight."""
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app import applications, work
from app.config import Settings
from app.main import create_app
from app.schemas import ApplicationUpdate
from app.work_schemas import FollowUpUpdate


@pytest.mark.parametrize('change', ['message', 'close_application'])
def test_mailbox_completion_preserves_newer_context_and_replays_receipt(tmp_path, change):
    class Provider:
        writes = 0
        def is_connected(self):
            return True
        def create_draft(self, application, followup, content):
            self.writes += 1
            with Session(app.state.engine) as session:
                if change == 'message':
                    work.update_followup(session, application.id, followup.id,
                        FollowUpUpdate(body='A newer human message', expected_revision=followup.revision), settings=settings)
                else:
                    applications.update_application(session, application.id,
                        ApplicationUpdate(status='CLOSED', expected_revision=application.revision), settings=settings)
            return 'https://mail.google.com/mail/u/0/#drafts/test'
    provider = Provider()
    settings = Settings(app_data_dir=tmp_path, _env_file=None)
    app = create_app(settings, mail_provider=provider)
    with TestClient(app) as client:
        application = client.post('/api/applications', json={'company': 'Example', 'job_title': 'Engineer', 'date_applied': '2026-10-18', 'email_reference': 'mail'}).json()
        path = f"/api/applications/{application['id']}"
        followup = client.get(path + '/work').json()['followups'][0]
        followup_path = path + '/followups/' + followup['id']
        saved = client.patch(followup_path, json={'subject': 'Follow up', 'body': 'Original message', 'recipient_email': 'recruiter@example.com', 'expected_revision': followup['revision']}).json()
        request = {'content': 'Original message', 'expected_revision': saved['revision'], 'operation_id': str(uuid4())}
        result = client.post(followup_path + '/draft', json=request)
        assert result.status_code == 200, result.text
        assert 'newer tracker message was preserved' in result.json()['message']
        assert client.post(followup_path + '/draft', json=request).json() == result.json()
        assert provider.writes == 1
        latest = client.get(path + '/work').json()['followups'][0]
        assert latest['body'] == ('A newer human message' if change == 'message' else 'Original message')
        assert latest['status'] == 'PREPARED'
