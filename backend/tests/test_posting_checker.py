import asyncio
from datetime import timedelta

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.models import PostingStatus, utc_now
from app.posting_checker import PostingChecker, inspect_html
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
    metadata_closed = inspect_html(
        '<script>window.__STATE__ = {"notice": "The job you are looking for is no longer available"}</script>',
        'https://fr.indeed.com/viewjob?jk=529293da834e1ec8', now,
    )
    assert metadata_closed.status == PostingStatus.CLOSED
    french_closed = inspect_html("<p>Cette offre d'emploi n'est plus disponible.</p>", 'https://example.test/job', now)
    assert french_closed.status == PostingStatus.CLOSED


def test_linkedin_guest_job_is_live_when_it_has_a_matched_apply_control():
    result = inspect_html(
        '''<html><head><meta name="pageKey" content="d_jobs_guest_details" />
        <link rel="canonical" href="https://fr.linkedin.com/jobs/view/full-stack-engineer-4463232717" /></head>
        <body><a id="topbar-apply" class="apply-button" data-tracking-control-name="public_jobs_apply-link-onsite">Apply</a></body></html>''',
        "https://www.linkedin.com/jobs/view/4463232717/",
    )
    assert result.status == PostingStatus.LIVE
    assert result.method == "LINKEDIN_HTML"
    assert "4463232717" in result.reason


def test_linkedin_apply_control_without_a_matched_job_page_is_inconclusive():
    result = inspect_html(
        '<button class="apply-button">Apply</button>',
        "https://www.linkedin.com/jobs/view/4463232717/",
    )
    assert result.status == PostingStatus.UNKNOWN


def test_indeed_job_is_live_when_it_has_a_matched_apply_control():
    result = inspect_html(
        '''<html><head><meta name="pageKey" content="jobsearch-JobInfoHeader" /></head>
        <body data-jk="529293da834e1ec8"><button data-testid="indeedApplyButton">Apply now</button></body></html>''',
        "https://fr.indeed.com/viewjob?jk=529293da834e1ec8",
    )
    assert result.status == PostingStatus.LIVE
    assert result.method == "INDEED_HTML"
    assert "529293da834e1ec8" in result.reason


def test_indeed_apply_control_without_a_matched_job_page_is_inconclusive():
    result = inspect_html(
        '<button data-testid="indeedApplyButton">Start</button>',
        "https://fr.indeed.com/viewjob?jk=529293da834e1ec8",
    )
    assert result.status == PostingStatus.UNKNOWN


def test_browser_fallback_handles_an_http_403_with_a_verified_page():
    async def browser(_url: str) -> tuple[str, str]:
        return (
            '''<meta name="pageKey" content="d_jobs_guest_details" />
            <body data-job-id="4463232717"><button class="apply-button">Apply</button></body>''',
            "https://www.linkedin.com/jobs/view/4463232717/",
        )

    result = asyncio.run(
        PostingChecker(browser_fallback=browser)._browser_result(
            "https://www.linkedin.com/jobs/view/4463232717/", utc_now(), 403,
            "https://www.linkedin.com/jobs/view/4463232717/",
        )
    )
    assert result.status == PostingStatus.LIVE
    assert result.http_status == 403
    assert result.method == "PLAYWRIGHT"


def test_browser_fallback_reports_a_blocked_403_clearly():
    async def browser(_url: str) -> tuple[str, str]:
        return "<title>Blocked</title><p>Access denied</p>", "https://fr.indeed.com/viewjob?jk=529293da834e1ec8"

    result = asyncio.run(
        PostingChecker(browser_fallback=browser)._browser_result(
            "https://fr.indeed.com/viewjob?jk=529293da834e1ec8", utc_now(), 403,
            "https://fr.indeed.com/viewjob?jk=529293da834e1ec8",
        )
    )
    assert result.status == PostingStatus.UNKNOWN
    assert result.method == "PLAYWRIGHT"
    assert "blocked the direct request" in result.reason


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
