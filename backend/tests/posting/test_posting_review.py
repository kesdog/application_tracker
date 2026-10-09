import asyncio
from urllib.parse import parse_qs, urlsplit

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.posting_checker import PostingChecker


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(app_data_dir=tmp_path, posting_playwright_fallback=True, _env_file=None))) as client:
        yield client


def application(client):
    return client.post('/api/applications', json={'job_title': 'C# Engineer', 'company': 'Acme', 'intermediary': 'ISCOD', 'location': 'Paris', 'date_applied': '2026-09-24', 'email_reference': 'Email 123', 'source': 'INDEED'}).json()


def review(**changes):
    return {'status': 'LIVE', 'evidence_url': 'https://employer.test/jobs/123', 'notes': 'Matched Acme, C# Engineer and Paris; this vacancy accepts applications.', 'same_position': True, 'replace_job_url': True, 'checked_at': '2026-09-25T13:30:00+02:00', **changes}


def test_search_handoff_available_without_url_and_manual_review_preserves_lifecycle(client):
    app = application(client)
    plan = client.get(f"/api/applications/{app['id']}/posting-review").json()
    query = parse_qs(urlsplit(plan['searches'][0]['url']).query)['q'][0]
    assert query == 'C# Engineer + Acme'
    assert len(plan['searches']) == 1 and plan['searches'][0]['label'] == 'Search manually'
    assert plan['search_query'] == query
    prompt = plan['agent_search_prompt']
    assert app['id'] in prompt and '2026-09-24' in prompt and 'Email 123' in prompt
    assert 'get_application_context' in prompt and 'get_application_timeline' in prompt
    assert 'signed-in mailbox' in prompt and 'record_posting_review' in prompt
    assert 'Preserve application status, outcome and original application date' in prompt
    result = client.post(f"/api/applications/{app['id']}/posting-review", json=review())
    assert result.status_code == 200 and result.json()['method'] == 'MANUAL_BROWSER'
    current = client.get(f"/api/applications/{app['id']}").json()
    assert current['job_url'] == 'https://employer.test/jobs/123' and current['source'] == 'OTHER'
    assert current['status'] == 'SUBMITTED' and current['outcome'] is None
    assert current['date_applied'] == '2026-09-24' and current['posting_last_checked_at'] == '2026-09-25T11:30:00Z'
    events = client.get(f"/api/applications/{app['id']}/timeline").json()['events']
    event = next(e for e in events if e['event_type'] == 'POSTING_REVIEWED')
    assert event['created_at'] == '2026-09-25T11:30:00Z'
    assert event['metadata']['replaced_job_url'] is True and event['metadata']['previous_job_url'] is None
    unknown = client.post(f"/api/applications/{app['id']}/posting-review", json=review(status='UNKNOWN', replace_job_url=False, same_position=False, notes='No verifiable matching position in the search results.'))
    assert unknown.status_code == 200 and unknown.json()['status'] == 'UNKNOWN'


@pytest.mark.parametrize('changes', [{'same_position': False}, {'status': 'CLOSED'}, {'status': 'UNKNOWN', 'replace_job_url': True}, {'evidence_url': 'javascript:alert(1)'}, {'checked_at': '2999-01-01T00:00:00Z'}])
def test_rejects_unverified_conclusions_replacements_and_invalid_dates(client, changes):
    app = application(client)
    assert client.post(f"/api/applications/{app['id']}/posting-review", json=review(**changes)).status_code == 422
    assert client.get(f"/api/applications/{app['id']}").json()['job_url'] is None


def test_agent_routes_share_extraction_browser_configuration_permissions_and_review(client, monkeypatch):
    token = client.post('/api/settings/agent/token').json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    def call(op, args):
        return client.post(f'/api/agent/tools/{op}', json=args, headers=headers)
    client.put('/api/settings/agent/permissions', json={'read': True, 'create': True, 'edit': False, 'draft': False, 'tasks': False, 'interviews': False})
    email = 'Candidature envoyée Engineer ISCOD - Paris Les éléments suivants ont été envoyés à ISCOD. Bonne chance !'
    extracted = call('extract_confirmation_details', {'confirmation_email': email})
    assert extracted.status_code == 200 and extracted.json()['intermediary'] == 'ISCOD'
    created = call('create_application', {'application': {'company': 'ISCOD', 'job_title': 'Engineer', 'date_applied': '2026-09-24', 'email_reference': 'Email', 'source': 'INDEED'}, 'confirmation_email': email})
    assert created.status_code == 200
    app = created.json()
    assert app['company'] == 'Employer not disclosed' and app['intermediary'] == 'ISCOD'
    agent_plan = call('get_posting_review', {'application_id': app['id']})
    assert agent_plan.status_code == 200
    assert agent_plan.json() == client.get(f"/api/applications/{app['id']}/posting-review").json()
    assert len(agent_plan.json()['searches']) == 1
    assert 'Employer: Employer not disclosed' in agent_plan.json()['agent_search_prompt']
    assert 'ISCOD' in agent_plan.json()['search_query']
    assert call('record_posting_review', {'application_id': app['id'], 'review': review()}).status_code == 403
    client.put('/api/settings/agent/permissions', json={'read': True, 'create': True, 'edit': True, 'draft': False, 'tasks': False, 'interviews': False})
    assert call('record_posting_review', {'application_id': app['id'], 'review': review()}).status_code == 200
    events = call('get_application_timeline', {'application_id': app['id']}).json()['events']
    assert next(e for e in events if e['event_type'] == 'POSTING_REVIEWED')['actor_type'] == 'AGENT'
    def fake_check(session, application_id, checker, **kwargs):
        assert checker.browser_fallback is not None and kwargs['actor_type'].value == 'AGENT'
        from app.schemas import PostingCheckRead
        return PostingCheckRead(status='UNKNOWN', checked_at='2026-09-25T11:30:00Z', http_status=403, final_url=None, method='PLAYWRIGHT', reason='Blocked', failures=1)
    monkeypatch.setattr('app.agent_ops.posting_service.check_application_posting', fake_check)
    assert call('check_posting_status', {'application_id': app['id']}).status_code == 200


def test_timeout_uses_rendered_browser_fallback(monkeypatch):
    async def get(*args, **kwargs):
        raise httpx.ReadTimeout('timed out')
    async def browser(url):
        return '<button>Apply now</button>', url
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    result = asyncio.run(PostingChecker(browser_fallback=browser).check('https://example.test/jobs/123'))
    assert result.status.value == 'LIVE' and result.method == 'PLAYWRIGHT'


def test_redirected_board_pages_and_description_alone_are_inconclusive(monkeypatch):
    from app.models import utc_now
    from app.posting_checker import inspect_html
    assert inspect_html('<h1>Job description</h1>', 'https://example.test/jobs/123').status.value == 'UNKNOWN'
    async def get(*args, **kwargs):
        return httpx.Response(200, text='<button>Apply now</button>', request=httpx.Request('GET', 'https://www.linkedin.com/jobs/'))
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    result = asyncio.run(PostingChecker().check('https://www.linkedin.com/jobs/view/123/'))
    assert result.status.value == 'UNKNOWN' and 'original job ID' in result.reason
    async def browser(url):
        return '<button>Apply now</button>', 'https://www.linkedin.com/jobs/view/456/'
    rendered = asyncio.run(PostingChecker(browser_fallback=browser)._browser_result('https://www.linkedin.com/jobs/view/123/', utc_now(), 403, 'https://www.linkedin.com/jobs/view/123/'))
    assert rendered.status.value == 'UNKNOWN' and 'original job ID' in rendered.reason
