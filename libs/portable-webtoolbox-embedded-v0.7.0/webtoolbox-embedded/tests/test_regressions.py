"""Offline regressions for the supplied contact-discovery failure catalogue."""

import asyncio
from pathlib import Path
from urllib.parse import urlsplit
import httpx
import pytest
from webtoolbox import Settings, WebToolbox
from webtoolbox.cache import SQLiteCache
from webtoolbox.contacts import extract_contacts, assess_employer
from webtoolbox.core import _fit_response, rendering_signals
from webtoolbox.extract import compact_text
from webtoolbox.search_results import normalize_hits
import webtoolbox.core as core

FIX = Path(__file__).parent / "fixtures"


def test_ads_never_consume_usable_budget_and_tracking_collapses():
    raw = [
        {"url": "https://www.bing.com/aclick?foo=1", "title": "Promoted"},
        {"url": "https://company.example/careers?utm_source=ads&job=42", "title": "Careers"},
        {"url": "https://company.example/careers?job=42&utm_campaign=paid", "title": "Careers duplicated"},
        {"url": "https://company.example/careers?job=99", "title": "Separate posting", "sponsored": False},
    ]
    hits, removed = normalize_hits(raw, "ddgs", official_domain="company.example")
    assert [h["url"] for h in hits] == ["https://company.example/careers?job=42", "https://company.example/careers?job=99"]
    assert removed["sponsored"] == 1 and removed["duplicates"] == 1
    assert hits[0]["rank"] == 2 and len(hits[0]["provenance"]) == 2
    assert hits[0]["sponsorship"] == "unknown" and hits[0]["employer_identity"] == "unknown"
    assert hits[1]["sponsorship"] == "organic"


def test_truncation_never_splits_emails_urls_or_records():
    address = "very.long-address.including-extra-information@careers.example"
    url = "https://recruitment.example/something?job=" + "a" * 450
    records = [{"url": url, "email": address, "excerpt": "x" * 120} for _ in range(10)]
    output = _fit_response({"results": records, "text": "one complete line\n" * 100}, 390)
    assert output["truncation"]["omitted_records"] > 0
    assert len(output["results"]) + output["truncation"]["omitted_records"] == 10
    assert all(rec["email"] == address and rec["url"] == url for rec in output["results"])
    text = "heading\n" + f"Address: {address}\n" + "other\n"
    clipped = compact_text(text, max_chars=30)
    assert address not in clipped and "@careers" not in clipped
    assert "metadata_exceeds_budget" not in output["truncation"]["reasons"]


def test_published_links_and_text_are_all_preserved_with_exclusions():
    contacts = extract_contacts((FIX / "published-emails.html").read_text(), "https://finaxys.example/team")
    by_email = {c["email"]: c for c in contacts}
    assert set(by_email) == {"recrutement@finaxys.example", "jobs@fortil.example", "presse@finaxys.example",
                             "sales@finaxys.example", "support@finaxys.example", "privacy@finaxys.example"}
    assert by_email["recrutement@finaxys.example"]["purpose"] == "recruitment"
    assert by_email["jobs@fortil.example"]["emails"][0]["label"] == "Postulez ici"
    assert by_email["jobs@fortil.example"]["emails"][0]["evidence"][0]["method"] == "mailto_link"
    for excluded in ("presse", "sales", "support", "privacy"):
        email = next(k for k in by_email if k.startswith(excluded))
        assert by_email[email]["exclusion_reason"] is not None
    # Bare navigation links remain separate; a Careers label is not attached to an email.
    assert all(e["label"] != "Careers" for c in contacts for e in c["emails"])


def test_scoped_cards_never_exchange_ownership_or_guess_absent_emails():
    contacts = extract_contacts((FIX / "people-cards.html").read_text(), "https://company.example/team")
    people = {c["name"]: c for c in contacts if c["name"]}
    assert people["Alice Martin"]["email"] == "alice@company.example"
    assert people["Bob Noel"]["email"] == "bob@company.example"
    assert people["Claire Laurent"]["email"] is None
    assert people["Pierre Pierre"]["email"] is None
    assert people["Claire Laurent"]["vacancy_responsibility"] == "unknown"
    assert people["Alice Martin"]["field_evidence"]["email"][0]["method"] == "mailto_link"
    assert people["Alice Martin"]["association"]["confidence"] == "scoped_record"
    unverified = assess_employer(people["Alice Martin"], "FAO Consulting", known_domains=("company.example",))
    assert unverified["employer_match"]["state"] == "provisional"
    assert unverified["personal_ownership"] == "unknown" and unverified["deliverability"] == "not_checked"
    assert assess_employer(people["Alice Martin"], "FAO Consulting", conflicting_names=("FAO Consulting",))["employer_match"]["state"] == "conflicting"


def test_js_shell_requires_two_signals_and_empty_static_page_does_not():
    assert "application_mount_node" in rendering_signals((FIX / "js-shell.html").read_text())
    assert rendering_signals((FIX / "empty-page.html").read_text()) == []


@pytest.mark.asyncio
async def test_search_records_fallback_provider_attempts_and_raw_vs_usable(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kw: url)
    calls = []

    async def fake_ddgs(query, limit):
        calls.append(query)
        if "recrutement contact" in query:
            return [{"url": "https://bing.com/aclick?q=ad", "title": "Ad"}]
        return [{"url": "https://company.example/jobs?id=42", "title": "Company careers"}]

    monkeypatch.setattr(core, "ddgs_search", fake_ddgs)
    async with WebToolbox(Settings(cache_path=tmp_path / "c.sqlite3")) as web:
        response = await web.search_with_fallback("Company", max_tokens=5000)
    assert response["completion"] == "complete"
    assert len(response["attempts"]) == 2
    assert response["attempts"][0]["outcome"] == "results"
    assert response["attempts"][0]["raw_count"] == 1 and response["attempts"][0]["usable_count"] == 0
    assert response["attempts"][1]["usable_count"] == 1
    assert response["results"][0]["url"].endswith("id=42")


@pytest.mark.asyncio
async def test_rate_limits_not_mislabeled_empty_and_stale_results_coexist(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kw: url)

    async def found(query, limit):
        return [{"url": "https://company.example/jobs", "title": "Jobs"}]

    monkeypatch.setattr(core, "ddgs_search", found)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3", provider_cooldown_seconds=0)) as web:
        await web.search("Company careers hiring contacts")
        with web.cache._connect() as con:
            con.execute("UPDATE cache SET expires_at=0")

        async def throttled(query, limit):
            raise RuntimeError("HTTP 429 rate limit")

        monkeypatch.setattr(core, "ddgs_search", throttled)
        stale = await web.search("Company careers hiring contacts")
        fallback = await web.search_with_fallback("Company")
    assert stale["outcome"] == "rate_limited"
    assert stale["cached"] and stale["stale"] and stale["results"]
    assert any(a["outcome"] == "rate_limited" for a in fallback["attempts"])
    assert fallback["completion"] in {"unresolved", "partial"}  # A rate limit never means empty.


@pytest.mark.asyncio
async def test_failed_provider_has_attempt_budget_and_unresolved_completion(tmp_path, monkeypatch):
    n = 0
    async def failed(query, limit):
        nonlocal n
        n += 1
        raise RuntimeError("upstream down")
    monkeypatch.setattr(core, "ddgs_search", failed)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        r = await web.search_with_fallback("Company", max_attempts=2)
    assert r["completion"] == "unresolved"
    assert r["stop_reason"] == "attempt_budget"
    assert n == 2 and len(r["attempts"]) == 2
    assert all(x["outcome"] == "upstream_error" for x in r["attempts"])


@pytest.mark.asyncio
async def test_no_implicit_browser_and_block_status_and_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kw: url)
    html = (FIX / "js-shell.html").read_text()
    browser_calls = 0

    async def static(self, url):
        return html, url

    async def browser(self, url):
        nonlocal browser_calls
        browser_calls += 1
        return "<html><main>Rendered</main></html>", url

    monkeypatch.setattr(WebToolbox, "_static_fetch", static)
    monkeypatch.setattr(WebToolbox, "_browser_fetch", browser)
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3")) as web:
        static_result = await web.crawl("https://company.example", mode="auto", structured=True)
        assert static_result["outcome"] == "rendering_needed"
        assert browser_calls == 0
        browser_result = await web.crawl("https://company.example", mode="browser", structured=True)
        assert browser_result["title"] == ""
        assert browser_calls == 1
        with web.cache._connect() as con:
            con.execute("UPDATE cache SET expires_at=0 WHERE cache_key LIKE 'page:%'")
        async def blocked(self, url):
            raise core.FetchBlocked(403, url)
        monkeypatch.setattr(WebToolbox, "_static_fetch", blocked)
        cached = await web.crawl("https://company.example", mode="auto", structured=True)
        assert cached["cached"] and cached["stale"] and cached["upstream_outcome"] == "blocked"
    async with WebToolbox(Settings(cache_path=tmp_path / "new.sqlite3")) as web:
        denied = await web.crawl("https://company.example", mode="auto", structured=True)
        assert denied["outcome"] == "blocked"


@pytest.mark.asyncio
async def test_concurrent_host_limits_and_unrelated_hosts_do_not_block(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kw: url)
    running = 0
    max_running = 0
    other_host_started = asyncio.Event()
    release = asyncio.Event()
    requests = []

    async def fake_stream(self, method, url, **kwargs):
        pass

    # This fake has stream's async-context-manager interface.
    class Response:
        status_code = 200
        encoding = "utf-8"
        headers = {"content-type": "text/html"}
        def raise_for_status(self): pass
        async def aiter_bytes(self): yield b"<html><body>Hello</body></html>"

    class Stream:
        def __init__(self, url): self.url = url
        async def __aenter__(self):
            nonlocal running, max_running
            running += 1
            max_running = max(max_running, running)
            requests.append(self.url)
            if urlsplit(self.url).hostname == "other.example":
                other_host_started.set()
            else:
                await release.wait()
            return Response()
        async def __aexit__(self, *args):
            nonlocal running
            running -= 1

    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3", concurrent_fetches=5,
                                per_host_concurrency=1, domain_delay_seconds=0)) as web:
        monkeypatch.setattr(web.client, "stream", lambda method, url, **kwargs: Stream(url))
        tasks = [asyncio.create_task(web.crawl(f"https://same.example/{i}", refresh=True)) for i in range(4)]
        tasks += [asyncio.create_task(web.crawl("https://other.example/a", refresh=True))]
        await asyncio.wait_for(other_host_started.wait(), 2)
        assert max_running <= 2  # One slow host and one unrelated host can run concurrently.
        release.set()
        await asyncio.gather(*tasks)
    assert max_running <= 2
    assert len(requests) == 5


@pytest.mark.asyncio
async def test_background_cancellation_has_completed_partial_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kw: url)

    async def fake_search(query, limit):
        return [{"url": "https://one.example", "title": "Jobs"}, {"url": "https://two.example", "title": "Jobs"}]
    monkeypatch.setattr(core, "ddgs_search", fake_search)
    second_started = asyncio.Event()
    async def fake_crawl(self, url, **kwargs):
        if url == "https://two.example/":
            second_started.set()
            await asyncio.Event().wait()
        return {"url": url, "title": "", "text": "yes", "fields": {}, "cached": False, "stale": False}
    monkeypatch.setattr(WebToolbox, "crawl", fake_crawl)
    reports = []
    async with WebToolbox(Settings(cache_path=tmp_path / "cache.sqlite3", max_crawl_pages=3)) as web:
        job = web.submit_research("Company careers", pages=2, on_progress=lambda p: reports.append(p))
        await asyncio.wait_for(second_started.wait(), 2)
        assert job.partial and len(job.partial["results"]) == 1
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job.result()
        assert job.partial["results"][0]["url"].startswith("https://one.example")
        assert any(p.get("event") == "page_complete" for p in reports)


def test_link_label_is_kept_with_its_own_destination():
    from webtoolbox.contacts import extract_contact_links, extract_source_dates
    html = (FIX / "published-emails.html").read_text()
    links = extract_contact_links(html, "https://finaxys.example/team")
    assert {link["label"]: link["url"] for link in links}["Careers"] == "https://finaxys.example/careers"
    assert all(link["url"] != "mailto:jobs@fortil.example?subject=CV" for link in links)
    assert extract_source_dates('<meta property="article:modified_time" content="2026-10-01">') == {
        "last_updated": "2026-10-01", "source": 'meta[property="article:modified_time"]'}


@pytest.mark.asyncio
async def test_explicit_empty_provider_and_timeout_have_distinct_outcomes(tmp_path, monkeypatch):
    async def empty(query, limit):
        return []
    monkeypatch.setattr(core, "ddgs_search", empty)
    async with WebToolbox(Settings(cache_path=tmp_path / "empty.sqlite3")) as web:
        r = await web.search_with_fallback("Company")
    assert r["completion"] == "complete" and r["attempts"]
    assert all(a["outcome"] == "empty" for a in r["attempts"])

    async def timeout(query, limit):
        raise asyncio.TimeoutError()
    monkeypatch.setattr(core, "ddgs_search", timeout)
    async with WebToolbox(Settings(cache_path=tmp_path / "timeout.sqlite3")) as web:
        r = await web.search_with_fallback("Company")
    assert r["completion"] == "unresolved" and all(a["outcome"] == "timeout" for a in r["attempts"])


@pytest.mark.asyncio
async def test_structured_crawl_contains_source_freshness_and_link_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "validate_url", lambda url, **kw: url)
    html = (FIX / "published-emails.html").read_text()
    async def fake_fetch(self, url):
        return html, url
    monkeypatch.setattr(WebToolbox, "_static_fetch", fake_fetch)
    async with WebToolbox(Settings(cache_path=tmp_path / "dates.sqlite3")) as web:
        result = await web.crawl("https://finaxys.example/team", structured=True,
                                 contacts=True, max_tokens=7500)
    assert result["cache_state"]["fetched_at_epoch"] > 0
    assert result["contact_links"][0]["label"] == "Careers"
    assert result["contact_links"][0]["url"].endswith("/careers")
    assert result["source_dates"]["last_updated"] is None
    assert all(c["fetched_at"] for c in result["candidates"])


def test_french_recruitment_language_in_public_source_excerpts():
    # Small source-grounded excerpts reconstructed from public job announcements.
    from webtoolbox.contacts import extract_contacts
    samples = (
        ("<p>Ou encore par mail à : recrutement@a3com.fr</p>", "recrutement@a3com.fr"),
        ("<p>Pour candidater : Via l'offre ou par email à contact@livract.fr</p>", "contact@livract.fr"),
        ("<p>Postulez en envoyant votre CV à recrutement@weadminit.fr</p>", "recrutement@weadminit.fr"),
    )
    for html, address in samples:
        contacts = extract_contacts(html, "https://example.com/recrutement/")
        assert len(contacts) == 1
        assert contacts[0]["email"] == address
        assert contacts[0]["purpose"] == "recruitment"
        assert contacts[0]["exclusion_reason"] is None


def test_french_recruitment_terms_do_not_override_bad_mailbox_purpose():
    # A press/privacy/support address is still excluded on a careers page.
    from webtoolbox.contacts import extract_contacts
    html = "<div><p>Recrutement</p><p>presse@exemple.fr</p><p>support@exemple.fr</p></div>"
    contacts = extract_contacts(html, "https://exemple.fr/recrutement/")
    by_mail = {c["email"]: c for c in contacts}
    assert by_mail["presse@exemple.fr"]["exclusion_reason"] == "not_recruitment_media"
    assert by_mail["support@exemple.fr"]["exclusion_reason"] == "not_recruitment_support"
