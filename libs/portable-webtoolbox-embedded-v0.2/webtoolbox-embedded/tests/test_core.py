"""Cache isolation, rendering defaults and compact response checks."""

import asyncio
from dataclasses import replace
from pathlib import Path

from webtoolbox import WebToolbox, Settings
from webtoolbox.cache import SQLiteCache
from webtoolbox.extract import approx_tokens
import webtoolbox.core as core


HTML = "<html><head><title>Open positions</title></head><body><nav>menu</nav><main><h1>Open roles</h1>" + "<p>Python engineer experience required</p>" * 100 + "<a href='mailto:jobs@example.org'>apply</a></main></body></html>"


def test_disk_cache_stale(tmp_path: Path):
    cache = SQLiteCache(tmp_path / "c.sqlite3")
    cache.set("x", {"data": 42}, ttl=0)
    assert cache.get("x") is None
    assert cache.get("x", allow_stale=True)["stale"] is True
    assert cache.prune() == 1


def test_crawl_reuses_page_across_recipes(monkeypatch, tmp_path: Path):
    # A second recipe should not cause a second outbound network fetch.
    monkeypatch.setattr(core, "validate_url", lambda x, **_: x)
    calls = []

    async def fake_fetch(self, url):
        calls.append(url)
        return HTML, url

    monkeypatch.setattr(WebToolbox, "_static_fetch", fake_fetch)
    settings = Settings(cache_path=tmp_path / "cache.sqlite3")

    async def run():
        async with WebToolbox(settings) as toolbox:
            first = await toolbox.crawl("https://example.org/jobs", max_tokens=300)
            second = await toolbox.crawl("https://example.org/jobs", recipe={"fields": {
                "email": {"selector": "a[href^='mailto:']", "attribute": "href"}}}, max_tokens=300)
            third = await toolbox.crawl("https://example.org/jobs", refresh=True, max_tokens=300)
        return first, second, third

    first, second, third = asyncio.run(run())
    assert len(calls) == 2
    assert first["cached"] is False and second["cached"] is True and third["cached"] is False
    assert second["fields"]["email"] == "mailto:jobs@example.org"
    assert "menu" not in first["text"]
    assert first["approx_output_tokens"] <= 320


def test_keyless_search_and_research(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(core, "validate_url", lambda x, **_: x)
    searched = []

    async def fake_search(query, limit):
        searched.append(query)
        return [{"url": "https://example.org/jobs", "title": "Python", "snippet": "hiring"}]

    async def fake_fetch(self, url):
        return HTML, url

    monkeypatch.setattr(core, "ddgs_search", fake_search)
    monkeypatch.setattr(WebToolbox, "_static_fetch", fake_fetch)

    async def run():
        async with WebToolbox(Settings(cache_path=tmp_path / "search.sqlite3")) as toolbox:
            first = await toolbox.research("python company jobs", pages=1, max_tokens=450)
            second = await toolbox.search("python company jobs")
        return first, second

    first, second = asyncio.run(run())
    assert len(searched) == 1
    assert first["results"][0]["url"] == "https://example.org/jobs"
    assert second["cached"] is True
    assert first["approx_output_tokens"] <= 470


def test_stale_search_is_labeled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(core, "validate_url", lambda x, **_: x)

    async def provider(query, limit):
        return [{"url": "https://example.org/jobs", "title": "Jobs", "snippet": "Hiring"}]

    monkeypatch.setattr(core, "ddgs_search", provider)

    async def run():
        async with WebToolbox(Settings(cache_path=tmp_path / "stale.sqlite3")) as toolbox:
            fresh = await toolbox.search("employer", limit=2)
            # Force a stale entry without depending on sleep or wall-clock timing.
            with toolbox.cache._connect() as con:
                con.execute("UPDATE cache SET expires_at=0")

            async def failed(*args):
                raise RuntimeError("provider unavailable")

            monkeypatch.setattr(core, "ddgs_search", failed)
            stale = await toolbox.search("employer", limit=3)
        return fresh, stale

    fresh, stale = asyncio.run(run())
    assert fresh["cached"] is False
    assert stale["cached"] and stale["stale"]
    assert "provider unavailable" in stale["warning"]
