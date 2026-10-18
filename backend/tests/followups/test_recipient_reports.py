import asyncio
from datetime import timedelta
import json
import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RecipientPageReport, utc_now
from app.recipient_reports import PageReports, SearchOnlyCache, list_reports, page_key
from app.recipient_research import PublicRecipientResearch
from webtoolbox.cache import SQLiteCache

CONTEXT = {'company': 'Example', 'job_title': 'Engineer', 'job_url': None, 'location': 'France'}
URL = 'https://example.com/contact'


def new_application(client):
    return client.post('/api/applications', json={**{k: CONTEXT[k] for k in ('company', 'job_title')},
        'date_applied': '2026-10-01', 'email_reference': 'test-message'}).json()['id']


def source(url=URL, **extra):
    return {'url': url, 'title': 'Example recruitment', 'text': 'Example contact findings. '+('x'*2000),
        'html': '<secret>Never saved</secret>', 'outcome': 'results', 'candidates': [
            {'email': 'jobs@employer.test', 'source_url': url, 'purpose': 'recruitment',
             'html': '<secret>Never saved</secret>', 'field_evidence': {'email': [{'excerpt': 'Recruitment: jobs@employer.test'}]}}], **extra}


async def test_reuse_across_restart_applications_and_redirect_aliases_without_raw_page_storage(client):
    app, other = new_application(client), new_application(client)
    engine = client.app.state.engine
    calls = []
    async def fetch():
        calls.append(True)
        return source('https://example.com/careers')
    first, fetched = await PageReports(engine).page(app, URL+'?utm_source=mail#x', CONTEXT, fetch)
    assert fetched and len(first['summary']) == 1000
    for app_id, url in [(app, URL), (other, 'https://EXAMPLE.com:443/careers')]:
        reused, fetched = await PageReports(engine).page(app_id, url, CONTEXT, fetch, allow_fetch=False)
        assert not fetched and reused['candidates'][0]['email'] == 'jobs@employer.test'
    assert calls == [True]
    listing = client.get('/api/recipients/pages').json()
    assert listing['total'] == 1
    report_id = listing['items'][0]['id']
    data = client.get(f'/api/recipients/pages/{report_id}', params={'application_id': other}).json()
    assert '<secret>' not in json.dumps(data) and 'html' not in data['report'] and 'text' not in data['report']
    assert client.get('/api/recipients/pages', params={'application_id': other}).json()['total'] == 1
    unrelated = new_application(client)
    assert client.get(f'/api/recipients/pages/{report_id}', params={'application_id': unrelated}).status_code == 404
    assert client.get('/api/recipients/pages', params={'page_size': 101}).status_code == 422


async def test_concurrent_jobs_fetch_a_url_once_and_explicit_refresh_is_retry_safe(client):
    app, other = new_application(client), new_application(client)
    store = PageReports(client.app.state.engine)
    calls = 0
    async def fetch():
        nonlocal calls
        calls += 1
        await asyncio.sleep(.05)
        return source()
    values = await asyncio.gather(store.page(app, URL, CONTEXT, fetch), store.page(other, URL, CONTEXT, fetch))
    assert calls == 1 and sorted(fetched for _, fetched in values) == [False, True]
    refresh_after = utc_now()
    assert (await store.page(app, URL, CONTEXT, fetch, refresh_after=refresh_after))[1]
    assert not (await store.page(app, URL, CONTEXT, fetch, refresh_after=refresh_after))[1]
    assert calls == 2


async def test_cancellation_releases_page_lease_and_retains_earlier_report(client):
    app = new_application(client)
    store = PageReports(client.app.state.engine)
    async def completed(): return source()
    await store.page(app, URL, CONTEXT, completed)
    started = asyncio.Event()
    async def blocked():
        started.set()
        await asyncio.Event().wait()
    task = asyncio.create_task(store.page(app, URL+'/team', CONTEXT, blocked))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    with Session(client.app.state.engine) as session:
        rows = session.scalars(select(RecipientPageReport)).all()
        assert len(rows) == 2 and all(r.lease_id is None for r in rows)
        assert list_reports(session, app)['total'] == 1
    assert (await store.page(app, URL+'/team', CONTEXT, completed))[1]


async def test_failed_reports_are_saved_and_only_explicit_refresh_refetches_them(client):
    app = new_application(client)
    store = PageReports(client.app.state.engine)
    calls = []
    async def fetch(): calls.append(True); return {'url': URL, 'outcome': 'blocked', 'error': 'Forbidden'}
    await store.page(app, URL, CONTEXT, fetch)
    value, fetched = await store.page(app, URL, CONTEXT, fetch)
    assert not fetched and value['outcome'] == 'blocked' and calls == [True]
    with Session(client.app.state.engine) as session:
        row = session.scalar(select(RecipientPageReport))
        row.fetched_at = utc_now()-timedelta(days=8)
        row.lease_id, row.lease_until = 'expired', utc_now()-timedelta(seconds=1)
        session.commit()
    value, fetched = await store.page(app, URL, CONTEXT, fetch)
    assert value['stale'] and not fetched
    assert (await store.page(app, URL, CONTEXT, fetch, refresh_after=utc_now()))[1]


async def test_new_fetch_budget_allows_free_saved_reports_and_continues_frontier_on_retry(client):
    app = new_application(client)
    store = PageReports(client.app.state.engine)
    class Web:
        def __init__(self): self.calls = []
        async def search_with_fallback(self, *a, **kw):
            return {'completion': 'complete', 'attempts': [], 'results': [{'url': URL, 'title': 'Example'}]}
        async def search(self, *a, **kw): return {'outcome': 'empty', 'results': []}
        async def crawl(self, url, **kw):
            self.calls.append(url)
            return source(url, fields={'contact_links': [URL+'/team', URL+'/team/people']})
    research = PublicRecipientResearch.__new__(PublicRecipientResearch)
    research.web, research.report_store = Web(), store
    context = {**CONTEXT, 'application_id': app, 'page_limit': 1}
    first = await research.discover(context)
    assert first['diagnostics']['fetched_pages'] == 1
    second = await research.discover(context)
    assert second['diagnostics']['fetched_pages'] == 1 and second['diagnostics']['reused_pages'] == 1
    third = await research.discover(context)
    assert third['diagnostics']['fetched_pages'] == 1 and third['diagnostics']['reused_pages'] == 2
    fourth = await research.discover(context)
    assert fourth['diagnostics']['fetched_pages'] == 0 and fourth['diagnostics']['reused_pages'] == 3
    assert len(research.web.calls) == len(set(research.web.calls)) == 3


async def test_reused_vacancy_claim_is_not_transferred_to_a_different_posting(client):
    app = new_application(client)
    class Web:
        async def search_with_fallback(self, *a, **kw):
            return {'completion':'complete','results':[{'url':URL,'title':'Example'}]}
        async def search(self, *a, **kw): return {'outcome':'empty','results':[]}
        async def crawl(self, url, **kw):
            value = source(url)
            if url == URL: value['candidates'][0]['vacancy_responsibility'] = 'published_for_vacancy'
            else: value['candidates'] = []
            return value
    research = PublicRecipientResearch.__new__(PublicRecipientResearch)
    research.web, research.report_store = Web(), PageReports(client.app.state.engine)
    context = {**CONTEXT,'application_id':app,'page_limit':3,'job_url':'https://example.com/jobs/one'}
    first = await research.discover(context)
    assert first['candidates'][0]['vacancy_match'] == 'published_for_vacancy'
    second = await research.discover({**context,'job_url':'https://example.com/jobs/two'})
    assert second['candidates'][0]['vacancy_match'] == 'unknown'


async def test_company_mention_after_summary_is_retained_without_storing_the_full_body(client):
    app = new_application(client)
    class Web:
        async def search_with_fallback(self, *a, **kw):
            return {'completion':'complete','results':[{'url':'https://vacancies.test/contact','title':'Example'}]}
        async def search(self, *a, **kw): return {'outcome':'empty','results':[]}
        async def crawl(self, url, **kw):
            return source(url, title='Hiring contact', text=('general information '*300)+' Example recruitment jobs@employer.test')
    research = PublicRecipientResearch.__new__(PublicRecipientResearch)
    research.web, research.report_store = Web(), PageReports(client.app.state.engine)
    context = {**CONTEXT,'application_id':app,'page_limit':1}
    assert (await research.discover(context))['candidates']
    reused = await research.discover(context)
    assert reused['candidates'] and reused['diagnostics']['fetched_pages'] == 0
    with Session(client.app.state.engine) as session:
        value = session.scalar(select(RecipientPageReport)).report
        assert len(value['summary']) == 1000 and 'example' in value['employer_excerpt']


def test_legacy_cache_is_converted_offline_once_and_search_cache_never_persists_html(client, tmp_path):
    legacy = tmp_path/'legacy.sqlite3'
    cache = SQLiteCache(legacy)
    cache.set('page:old', {'html': '<title>Example</title><p>Recruitment: jobs@employer.test</p>', 'final_url': URL}, 60)
    store = PageReports(client.app.state.engine)
    assert store.import_legacy(legacy) == 1 and store.import_legacy(legacy) == 0
    data = client.get('/api/recipients/pages').json()
    assert data['items'][0]['candidate_count'] == 1
    cache_path = tmp_path/'search-only.sqlite3'
    adapter = SearchOnlyCache(SQLiteCache(cache_path))
    adapter.set('page:raw', {'html': 'Private raw content'}, 60)
    adapter.set('search:query', {'results': [{'url': URL}]}, 60)
    assert adapter.get('page:raw')['html'] == 'Private raw content'
    with sqlite3.connect(cache_path) as db:
        rows = db.execute('SELECT cache_key,value FROM cache').fetchall()
    assert len(rows) == 1 and rows[0][0] == 'search:query' and 'Private raw content' not in rows[0][1]
    assert SearchOnlyCache(SQLiteCache(cache_path)).get('page:raw') is None
    assert page_key('https://EXAMPLE.com:443/contact?utm_source=x#y') == URL
