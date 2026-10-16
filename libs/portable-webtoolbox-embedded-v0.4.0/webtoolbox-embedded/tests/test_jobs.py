"""Background job scheduling, deduplication, bounded concurrency and shutdown."""

import asyncio
from pathlib import Path
import pytest
from webtoolbox import Settings, WebToolbox


@pytest.mark.asyncio
async def test_submit_crawl_returns_immediately_and_deduplicates(tmp_path: Path, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def fake_crawl(self, url, **kwargs):
        calls.append(url)
        started.set()
        await release.wait()
        return {"fields": {"emails": ["jobs@example.org"]}, "url": url}

    monkeypatch.setattr(WebToolbox, "crawl", fake_crawl)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        job = web.submit_crawl("https://example.org", max_tokens=300)
        same = web.submit_crawl("https://example.org", max_tokens=300)
        assert same is job and job.status in {"queued", "running"}
        await started.wait()
        assert job.status == "running" and not job.done
        release.set()
        result = await job.result()
        assert result["fields"]["emails"] == ["jobs@example.org"]
        assert job.status == "completed"
        await asyncio.sleep(0)
        assert web.job(job.id) is job
    assert calls == ["https://example.org"]


@pytest.mark.asyncio
async def test_background_limit_and_graceful_close(tmp_path: Path, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    parallel = 0
    max_parallel = 0

    async def fake_crawl(self, url, **kwargs):
        nonlocal parallel, max_parallel
        parallel += 1
        max_parallel = max(max_parallel, parallel)
        started.set()
        await release.wait()
        parallel -= 1
        return {"url": url}

    monkeypatch.setattr(WebToolbox, "crawl", fake_crawl)
    web = WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3", background_concurrency=1, max_pending_jobs=2))
    first = web.submit_crawl("https://example.org/1")
    second = web.submit_crawl("https://example.org/2")
    with pytest.raises(RuntimeError, match="Too many"):
        web.submit_crawl("https://example.org/3")
    await started.wait()
    closer = asyncio.create_task(web.close())
    await asyncio.sleep(0)
    assert not closer.done()
    release.set()
    await closer
    assert (await first.result())["url"].endswith("/1")
    assert (await second.result())["url"].endswith("/2")
    assert max_parallel == 1
    with pytest.raises(RuntimeError, match="closed"):
        web.submit_crawl("https://example.org/4")


@pytest.mark.asyncio
async def test_failed_and_cancelled_jobs(tmp_path: Path, monkeypatch):
    async def fake_crawl(self, url, **kwargs):
        if url.endswith("/fail"):
            raise ValueError("broken selector")
        await asyncio.Event().wait()
        return {}

    monkeypatch.setattr(WebToolbox, "crawl", fake_crawl)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        failure = web.submit_crawl("https://example.org/fail")
        with pytest.raises(ValueError, match="broken selector"):
            await failure.result()
        assert failure.status == "failed" and failure.error == "broken selector"
        stalled = web.submit_crawl("https://example.org/stall")
        await asyncio.sleep(0)
        assert stalled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await stalled.result()
        assert stalled.status == "cancelled"


@pytest.mark.asyncio
async def test_recipe_returns_only_fields_by_default(tmp_path: Path, monkeypatch):
    from webtoolbox import core
    monkeypatch.setattr(core, "validate_url", lambda x, **_: x)

    async def fake_fetch(self, url):
        return '<html><title>Jobs</title><main><p>Very long article</p><a href="mailto:hr@example.org">Email</a></main></html>', url

    monkeypatch.setattr(WebToolbox, "_static_fetch", fake_fetch)
    recipe = {"fields": {"emails": {"selector": "a[href^='mailto:']", "attribute": "href", "all": True}}}
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        result = await web.crawl("https://example.org", recipe=recipe)
        verbose = await web.crawl("https://example.org", recipe=recipe, include_text=True)
    assert "text" not in result
    assert result["fields"]["emails"] == ["mailto:hr@example.org"]
    assert "Very long article" in verbose["text"]


@pytest.mark.asyncio
async def test_parallel_recipes_share_uncached_page(tmp_path: Path, monkeypatch):
    from webtoolbox import core
    monkeypatch.setattr(core, "validate_url", lambda x, **_: x)
    calls = 0

    async def fake_fetch(self, url):
        nonlocal calls
        calls += 1
        # Give the second job time to ask for the same uncached page.
        await asyncio.sleep(0)
        return '<html><body><main><a href="mailto:hr@example.org">Email</a></main></body></html>', url

    monkeypatch.setattr(WebToolbox, "_static_fetch", fake_fetch)
    recipe_a = {"fields": {"emails": {"selector": "a[href^='mailto:']", "attribute": "href"}}}
    recipe_b = {"fields": {"label": {"selector": "a[href^='mailto:']"}}}
    async with WebToolbox(Settings(cache_path=tmp_path / "shared.sqlite3")) as web:
        job_a = web.submit_crawl("https://example.org", recipe=recipe_a)
        job_b = web.submit_crawl("https://example.org", recipe=recipe_b)
        a, b = await asyncio.gather(job_a.result(), job_b.result())
        assert a["fields"]["emails"] == "mailto:hr@example.org"
        assert b["fields"]["label"] == "Email"
        assert calls == 1


@pytest.mark.asyncio
async def test_on_result_is_awaited_before_completion(tmp_path: Path, monkeypatch):
    saved = []

    async def fake_crawl(self, url, **kwargs):
        return {"url": url, "fields": {"email": "hr@example.org"}}

    async def save_result(result):
        # The host application can persist accepted evidence without polling.
        await asyncio.sleep(0)
        saved.append(result["fields"]["email"])

    monkeypatch.setattr(WebToolbox, "crawl", fake_crawl)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        job = web.submit_crawl("https://example.org", on_result=save_result)
        await job.result()
        assert job.status == "completed"
    assert saved == ["hr@example.org"]
