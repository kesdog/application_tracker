"""Offline contracts for job board link and lifecycle detection."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

import webtoolbox.core as core
from webtoolbox import WebToolbox, Settings
from webtoolbox.job_postings import (
    platform_of, is_specific_job_url, canonical_job_url,
    parse_job_page, assess_status, application_links, match_job,
)

LINKEDIN = "https://www.linkedin.com/jobs/view/alternance-developpeur-at-company-3663502899?trackingId=abc"
INDEED = "https://fr.indeed.com/viewjob?jk=27fc96cacd2d6fe2&utm_source=alerts&tk=abcd"
FREEWORK = "https://www.free-work.com/fr/tech-it/job-mission/developpeur-python/developpeur-python-cloud"
ATS = "https://job-boards.greenhouse.io/example/jobs/4829123"


def job_html(title="Développeur Python", company="Acme", location="Toulouse", *,
             apply_href="/careers/apply/4829123", extra="", schema=True):
    # The same fixtures exercise HTML and structured-data extraction.
    structured = {"@context": "https://schema.org", "@type": "JobPosting",
                  "title": title, "hiringOrganization": {"@type": "Organization", "name": company},
                  "jobLocation": {"address": {"addressLocality": location}},
                  "employmentType": "INTERN"}
    script = '<script type="application/ld+json">' + json.dumps(structured) + "</script>" if schema else ""
    return f'<html><head><title>{title}</title>{script}</head><body><main><h1>{title}</h1><p>{company} - {location}</p><a href="{apply_href}">Postuler</a>{extra}</main></body></html>'


def test_known_platform_urls_and_tracking_cleanup():
    assert platform_of(LINKEDIN) == "linkedin"
    assert platform_of(INDEED) == "indeed"
    assert platform_of(FREEWORK) == "freework"
    assert platform_of("https://jobs.lever.co/acme/abcdef") == "lever"
    assert platform_of("https://notlever.co/jobs/123") == "other"
    assert is_specific_job_url(LINKEDIN)
    assert is_specific_job_url(INDEED)
    assert is_specific_job_url(FREEWORK)
    assert is_specific_job_url(ATS)
    assert canonical_job_url(LINKEDIN) == "https://www.linkedin.com/jobs/view/3663502899/"
    assert canonical_job_url(INDEED) == "https://fr.indeed.com/viewjob?jk=27fc96cacd2d6fe2"
    assert not is_specific_job_url("https://www.linkedin.com/jobs/search/?keywords=python")
    assert not is_specific_job_url("https://www.free-work.com/fr/tech-it/jobs/developpeur-python")
    assert not is_specific_job_url("https://acme.com/jobs/search")


@pytest.mark.parametrize("url,notice", [
    (LINKEDIN, "No longer accepting applications"),
    (INDEED, "This job has expired"),
    (FREEWORK, "L’offre recherchée est expirée"),
    (ATS, "This position has been filled"),
])
def test_explicit_closed_notices(url, notice):
    html = job_html(extra=f"<p>{notice}</p>")
    status, reason, confidence, evidence = assess_status(parse_job_page(html, url), url)
    assert (status, reason, confidence) == ("CLOSED", "explicit_closed_notice", "high")
    assert evidence


@pytest.mark.parametrize("url", [LINKEDIN, INDEED, FREEWORK, ATS])
def test_public_apply_link_indicates_live_listing(url):
    page = parse_job_page(job_html(), url)
    assert page["application_links"][0]["url"] == "https://" + url.split("/")[2] + "/careers/apply/4829123"
    assert assess_status(page, url)[:2] == ("LIVE", "application_link_visible")


def test_js_apply_button_without_destination_is_not_fabricated():
    url = INDEED
    html = job_html(apply_href="#", extra='<button id="indeedApplyButton">Apply now</button>')
    page = parse_job_page(html, url)
    assert page["application_links"] == []
    assert page["visible_apply_controls"]
    assert assess_status(page, url)[:2] == ("LIVE", "apply_control_visible")


def test_disabled_apply_button_cannot_confirm_live():
    html = job_html(apply_href="#", extra='<button disabled>Apply now</button>')
    assert assess_status(parse_job_page(html, INDEED), INDEED)[0] == "UNKNOWN"


def test_access_block_outranks_available_apply_button():
    html = job_html(extra="<p>Verify you are human CAPTCHA</p>")
    assert assess_status(parse_job_page(html, LINKEDIN), LINKEDIN)[:2] == ("UNKNOWN", "access_blocked")


def test_past_validthrough_alone_not_definitive_closure():
    html = job_html().replace('"employmentType": "INTERN"', '"employmentType": "INTERN", "validThrough": "2020-01-01"')
    assert assess_status(parse_job_page(html, FREEWORK), FREEWORK)[:2] == ("UNKNOWN", "expired_schema_date")


def test_structured_ats_apply_url_and_no_cross_card_corruption():
    target = ATS
    html = job_html(apply_href="#").replace('"employmentType": "INTERN"',
                 '"employmentType": "INTERN", "applyUrl": "https://boards.greenhouse.io/example/apply/4829123"')
    links = application_links(html, target, parse_job_page(html, target) and {
        "applyUrl": "https://boards.greenhouse.io/example/apply/4829123"})
    assert links[0]["url"] == "https://boards.greenhouse.io/example/apply/4829123"


def test_ranking_not_exact_from_role_alone():
    page = parse_job_page(job_html(company="Unknown Corp", location="Lyon", schema=False), FREEWORK)
    match = match_job(page, company="Acme", title="Développeur Python", location="Toulouse")
    assert match["status"] != "likely_match"


@pytest.fixture
def fake_web(monkeypatch, tmp_path):
    # DNS resolution and remote fetches are replaced with deterministic sources.
    monkeypatch.setattr(core, "validate_url", lambda x, **kwargs: x)
    return Settings(cache_path=tmp_path / "job.sqlite3", domain_delay_seconds=0)


@pytest.mark.parametrize("url", [LINKEDIN, INDEED, FREEWORK])
async def test_live_status_then_cached_status(url, fake_web, monkeypatch):
    calls = []

    async def fetch(self, requested):
        calls.append(requested)
        return job_html(), requested

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        first = await web.check_job_status(url)
        cached = await web.check_job_status(url)
    assert first["status"] == "LIVE" and first["cached"] is False
    assert cached["cached"] is True
    assert len(calls) == 1


@pytest.mark.parametrize("code", [401, 403, 405, 429])
async def test_blocked_and_rate_limited_are_unknown(code, fake_web, monkeypatch):
    async def fetch(self, requested):
        if code in {403, 405}:
            raise core.FetchBlocked(code, requested)
        request = httpx.Request("GET", requested)
        response = httpx.Response(code, request=request)
        raise httpx.HTTPStatusError("blocked", request=request, response=response)

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        result = await web.check_job_status(INDEED)
    assert result["status"] == "UNKNOWN"
    assert result["reason"] == "access_blocked"


@pytest.mark.parametrize("code", [404, 410])
async def test_gone_posting_is_closed_not_proof_hiring_ended(code, fake_web, monkeypatch):
    async def fetch(self, requested):
        request = httpx.Request("GET", requested)
        response = httpx.Response(code, request=request)
        raise httpx.HTTPStatusError("gone", request=request, response=response)

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        result = await web.check_job_status(FREEWORK)
    assert result["status"] == "CLOSED"
    assert result["reason"] == "posting_unavailable"
    assert result["confidence"] == "medium"


async def test_old_cached_html_does_not_override_fresh_404(fake_web, monkeypatch):
    calls = 0

    async def fetch(self, requested):
        nonlocal calls
        calls += 1
        if calls == 1:
            return job_html(), requested
        request = httpx.Request("GET", requested)
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("removed", request=request, response=response)

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        assert (await web.check_job_status(INDEED))["status"] == "LIVE"
        assert (await web.check_job_status(INDEED, refresh=True))["status"] == "CLOSED"


async def test_redirect_to_login_is_unknown(fake_web, monkeypatch):
    async def fetch(self, requested):
        return job_html(), "https://fr.indeed.com/account/login"

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        result = await web.check_job_status(INDEED)
    assert (result["status"], result["reason"]) == ("UNKNOWN", "redirected_from_posting")


async def test_discover_job_deduplicates_tracking_links_and_ranks_correct_role(fake_web, monkeypatch):
    async def search(query, limit):
        return [
            {"title": "Développeur Python", "url": FREEWORK+"?utm_source=mail", "snippet": "Acme Toulouse"},
            {"title": "Développeur Python", "url": FREEWORK+"?utm_source=alert", "snippet": "Acme Toulouse"},
            {"title": "Développeur Python", "url": LINKEDIN, "snippet": "Acme Toulouse"},
            {"title": "Other position", "url": "https://www.linkedin.com/jobs/search/?q=python", "snippet": "Search"},
        ]

    async def fetch(self, url):
        return job_html(), url

    monkeypatch.setattr(core, "ddgs_search", search)
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        result = await web.discover_job("Acme", "Développeur Python", location="Toulouse", pages=4)
    assert len(result["matches"]) == 2
    assert result["matches"][0]["match"]["status"] == "likely_match"
    assert all(x["posting_status"] == "LIVE" for x in result["matches"])
    assert result["matches"][0]["application_url"]


async def test_job_discovery_remains_usable_without_search_provider(fake_web, monkeypatch):
    async def fetch(self, url):
        return job_html(), url

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        result = await web.discover_job("Acme", "Développeur Python", seed_urls=(ATS,), pages=1)
    assert result["matches"] and result["matches"][0]["source"] == "seed"


async def test_status_unknown_when_dynamic_shell(fake_web, monkeypatch):
    async def fetch(self, url):
        return '<html><head><script src="/bundle.js"></script></head><body><div id="root"></div></body></html>', url

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        result = await web.check_job_status(LINKEDIN)
    assert (result["status"], result["reason"]) == ("UNKNOWN", "rendering_needed")


async def test_compact_results_omit_complete_job_records(fake_web, monkeypatch):
    async def search(query, limit):
        return [{"title": "Python", "url": LINKEDIN, "snippet": "Acme"},
                {"title": "Python", "url": FREEWORK, "snippet": "Acme"}]

    async def fetch(self, url):
        return job_html(), url

    monkeypatch.setattr(core, "ddgs_search", search)
    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        result = await web.discover_job("Acme", "Développeur Python", max_tokens=280, pages=2)
    assert result["truncation"]["omitted_records"] > 0
    assert result["truncation"]["reasons"]
    assert len(result["matches"]) < 2


async def test_background_status_job_handle(fake_web, monkeypatch):
    async def fetch(self, url):
        await asyncio.sleep(.01)
        return job_html(), url

    monkeypatch.setattr(WebToolbox, "_static_fetch", fetch)
    async with WebToolbox(fake_web) as web:
        handle = web.submit_check_job_status(FREEWORK)
        result = await handle.result()
        assert result["status"] == "LIVE"
        assert web.job(handle.id) is not None
