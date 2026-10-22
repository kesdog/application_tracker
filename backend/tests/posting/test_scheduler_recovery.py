from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from app.models import Application, PostingStatus, utc_now
from app.posting_checker import PostingCheckResult
from app.scheduler import PostingCheckScheduler


@pytest.mark.asyncio
async def test_restart_catches_up_only_due_records_and_rejects_changed_url(client, monkeypatch):
    def create(company):
        return client.post('/api/applications', json={'company': company, 'job_title': 'Engineer',
            'date_applied': '2026-10-01', 'job_url': f'https://example.test/{company}'}).json()['id']
    due, fresh, changed = [create(name) for name in ('due', 'fresh', 'changed')]
    with Session(client.app.state.engine) as session:
        session.get(Application, fresh).posting_last_checked_at = utc_now()
        session.commit()
    calls = []
    async def check(_self, url):
        calls.append(url)
        if url.endswith('changed'):
            with Session(client.app.state.engine) as session:
                session.get(Application, changed).job_url = 'https://example.test/new'
                session.commit()
        return PostingCheckResult(PostingStatus.CLOSED, utc_now(), 404, url, 'HTTP', 'Unavailable')
    monkeypatch.setattr('app.scheduler.PostingChecker.check', check)
    settings = SimpleNamespace(posting_check_interval_hours=24, posting_check_concurrency=2, posting_playwright_fallback=False)
    result = await PostingCheckScheduler(client.app.state.engine, settings).refresh()
    assert result['checked'] == 1
    with Session(client.app.state.engine) as session:
        assert session.get(Application, due).posting_status == PostingStatus.CLOSED
        assert session.get(Application, changed).posting_last_checked_at is None
    await PostingCheckScheduler(client.app.state.engine, settings).refresh()
    assert sum(url.endswith('/due') for url in calls) == 1
    assert not any(url.endswith('/fresh') for url in calls)
