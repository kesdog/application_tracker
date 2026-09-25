from datetime import timedelta

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.models import PostingStatus, utc_now
from app.posting_checker import inspect_html
from app.posting_service import apply_result


def test_deterministic_html_hierarchy():
    now = utc_now()
    expired = inspect_html('<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","validThrough":"2020-01-01"}</script>', 'https://example.test/job', now)
    assert expired.status == PostingStatus.CLOSED and expired.method == "JSON_LD"
    live = inspect_html('<script type="application/ld+json">{"@context":"https://schema.org","@type":"JobPosting","validThrough":"2999-01-01"}</script>', 'https://example.test/job', now)
    assert live.status == PostingStatus.LIVE
    closed = inspect_html('<p>THIS position has been filled</p>', 'https://example.test/job', now)
    assert closed.status == PostingStatus.CLOSED and closed.method == "HTML"
    assert inspect_html('<p>The role was filled with useful experience.</p>', 'https://example.test/job', now).status == PostingStatus.UNKNOWN
    assert inspect_html('<button>Apply now</button>', 'https://example.test/job', now).status == PostingStatus.LIVE
    linkedin = inspect_html('<p>This role is no longer accepting applications.</p>', 'https://www.linkedin.com/jobs/view/4390679517/', now)
    assert linkedin.status == PostingStatus.CLOSED and linkedin.method == "HTML"


def test_unknown_check_preserves_live_status_and_tracks_failures(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, _env_file=None))) as client:
        application = client.post('/api/applications', json={"job_title": "Engineer", "company": "Example", "date_applied": "2026-09-25", "job_url": "https://example.test/job"}).json()
        with client.app.state.engine.begin() as connection:
            pass
        from sqlalchemy.orm import Session
        from app.applications import get_application
        from app.posting_checker import PostingCheckResult
        with Session(client.app.state.engine) as session:
            record = get_application(session, application['id']); record.posting_status = PostingStatus.LIVE; session.commit()
            unknown = PostingCheckResult(PostingStatus.UNKNOWN, utc_now(), 429, 'https://example.test/job', 'HTTP', 'HTTP 429 prevented a reliable posting check')
            saved = apply_result(session, record, unknown)
            assert saved.status == PostingStatus.LIVE and saved.failures == 1
            closed = PostingCheckResult(PostingStatus.CLOSED, utc_now(), 404, 'https://example.test/job', 'HTTP', 'HTTP 404 confirms the posting is unavailable')
            saved = apply_result(session, record, closed)
            assert saved.status == PostingStatus.CLOSED and saved.failures == 0
        timeline = client.get(f"/api/applications/{application['id']}/timeline").json()
        assert sum(event['event_type'] == 'POSTING_STATUS_CHANGED' for event in timeline['events']) == 1
