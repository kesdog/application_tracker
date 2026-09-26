"""Conservative, deterministic job-posting inspection with no LLM dependency."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import unescape
import re
from typing import Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import extruct
import httpx
from bs4 import BeautifulSoup

from app import __version__
from app.models import PostingStatus, utc_now


STRONG_CLOSED_PHRASES = (
    "this job is no longer available", "the job you are looking for is no longer available",
    "job posting is no longer available", "this position has been filled", "applications are closed",
    "this job has expired", "job posting has expired", "we are no longer accepting applications",
    "no longer accepting applications", "job not found", "job has been removed",
    "this job has been removed", "position is no longer available", "position has been removed",
    "cette offre d'emploi n'est plus disponible", "cette offre n'est plus disponible",
    "les candidatures ne sont plus acceptées", "les candidatures sont closes", "poste pourvu",
    "l'offre d'emploi a expiré",
)
LIVE_SIGNALS = ("apply now", "apply for this job", "submit application", "job description")
LINKEDIN_GUEST_PAGE_MARKERS = ("d_jobs_guest_details", "jobs-guest-frontend")
INDEED_JOB_PAGE_MARKERS = ("jobsearch-jobinfoheader", "jobsearch-jobcomponent", "indeedapply")


@dataclass(frozen=True)
class PostingCheckResult:
    status: PostingStatus
    checked_at: datetime
    http_status: int | None
    final_url: str | None
    method: str
    reason: str


def normalized_text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(BeautifulSoup(html, "html.parser").get_text(" "))).casefold()


def _linkedin_job_id(url: str) -> str | None:
    """Return the job id from both direct and slugged LinkedIn guest URLs."""
    parsed = urlparse(url)
    if not (parsed.hostname or "").casefold().endswith("linkedin.com"):
        return None
    match = re.search(r"/jobs/view/(?:[^/?#]*-)?(\d+)(?:[/?#]|$)", parsed.path, re.IGNORECASE)
    return match.group(1) if match else None


def _linkedin_live_signal(html: str, final_url: str) -> str | None:
    """Check LinkedIn's guest-job DOM without treating a generic Apply word as proof."""
    job_id = _linkedin_job_id(final_url)
    source = html.casefold()
    if not job_id or job_id not in source or not any(marker in source for marker in LINKEDIN_GUEST_PAGE_MARKERS):
        return None

    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(("a", "button")):
        attributes = " ".join(
            " ".join(value) if isinstance(value, list) else str(value)
            for value in element.attrs.values()
        ).casefold()
        if "apply-button" in attributes or "public_jobs_apply" in attributes:
            return f"LinkedIn guest job page matched job ID {job_id} and exposes an Apply control"
    return None


def _indeed_job_key(url: str) -> str | None:
    """Return the immutable ``jk`` key from an Indeed direct job URL."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    if not any(host == domain or host.endswith(f".{domain}") for domain in ("indeed.com", "indeed.fr", "indeed.co.uk", "indeed.de")):
        return None
    if not parsed.path.rstrip("/").endswith("/viewjob"):
        return None
    job_key = (parse_qs(parsed.query).get("jk") or [None])[0]
    return job_key.casefold() if isinstance(job_key, str) and re.fullmatch(r"[a-zA-Z0-9]+", job_key) else None


def _indeed_live_signal(html: str, final_url: str) -> str | None:
    """Verify an Indeed job page from its job key and native application control."""
    job_key = _indeed_job_key(final_url)
    source = html.casefold()
    if not job_key or job_key not in source or not any(marker in source for marker in INDEED_JOB_PAGE_MARKERS):
        return None

    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(("a", "button")):
        attributes = " ".join(
            " ".join(value) if isinstance(value, list) else str(value)
            for value in element.attrs.values()
        ).casefold()
        if "indeedapply" in attributes or "indeed-apply" in attributes:
            return f"Indeed job page matched job key {job_key} and exposes an Apply control"
    return None


def _date(value) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _job_postings(html: str, url: str) -> list[dict]:
    try:
        extracted = extruct.extract(html, base_url=url, syntaxes=["json-ld", "microdata"])
    except Exception:
        return []
    candidates: list[dict] = []
    for syntax in ("json-ld", "microdata"):
        for item in extracted.get(syntax, []):
            values = item if isinstance(item, list) else [item]
            for value in values:
                if not isinstance(value, dict):
                    continue
                kinds = value.get("@type") or value.get("type") or []
                if isinstance(kinds, str): kinds = [kinds]
                if any(str(kind).casefold() == "jobposting" for kind in kinds):
                    item_url = value.get("url")
                    # Metadata naming another posting is ignored to avoid unrelated vacancy widgets.
                    if not item_url or str(item_url).rstrip("/") == url.rstrip("/"):
                        candidates.append(value)
    return candidates


def inspect_html(html: str, final_url: str, checked_at: datetime | None = None) -> PostingCheckResult:
    checked_at = checked_at or utc_now()
    postings = _job_postings(html, final_url)
    if postings:
        expiry_values = [_date(item.get("validThrough")) for item in postings]
        if any(value is not None and value < checked_at.date() for value in expiry_values):
            return PostingCheckResult(PostingStatus.CLOSED, checked_at, 200, final_url, "JSON_LD", "Structured JobPosting metadata has an expired validThrough date")
        return PostingCheckResult(PostingStatus.LIVE, checked_at, 200, final_url, "JSON_LD", "Structured JobPosting metadata found without an expired validThrough date")
    text = normalized_text(html)
    # Some job boards place their standardized unavailable message in metadata or
    # a client-rendered template, so inspect the raw response too. The phrases
    # above are deliberately strong enough to avoid treating a generic mention
    # of a filled role as a closed posting.
    closure_text = f"{text} {html.casefold()}"
    phrase = next((item for item in STRONG_CLOSED_PHRASES if item in closure_text), None)
    if phrase:
        return PostingCheckResult(PostingStatus.CLOSED, checked_at, 200, final_url, "HTML", f"Page contains closed-posting phrase: {phrase}")
    linkedin_signal = _linkedin_live_signal(html, final_url)
    if linkedin_signal:
        return PostingCheckResult(PostingStatus.LIVE, checked_at, 200, final_url, "LINKEDIN_HTML", linkedin_signal)
    indeed_signal = _indeed_live_signal(html, final_url)
    if indeed_signal:
        return PostingCheckResult(PostingStatus.LIVE, checked_at, 200, final_url, "INDEED_HTML", indeed_signal)
    signal = next((item for item in LIVE_SIGNALS if item in text), None)
    if signal:
        return PostingCheckResult(PostingStatus.LIVE, checked_at, 200, final_url, "HTML", f"Page contains live-posting signal: {signal}")
    return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, 200, final_url, "HTTP", "No conclusive structured metadata or posting text signal found")


class PostingChecker:
    def __init__(self, timeout_seconds: float = 12, browser_fallback: Callable[[str], Awaitable[tuple[str, str]]] | None = None):
        self.timeout_seconds = timeout_seconds
        self.browser_fallback = browser_fallback

    async def _browser_result(self, url: str, checked_at: datetime, http_status: int, final_url: str) -> PostingCheckResult:
        """Use the ordinary browser fallback when direct HTTP was blocked or inconclusive."""
        try:
            rendered_html, rendered_url = await self.browser_fallback(url)  # type: ignore[misc]
        except (ImportError, ModuleNotFoundError):
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, http_status, final_url, "ERROR", "Playwright fallback unavailable")
        except Exception as exc:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, http_status, final_url, "ERROR", f"Playwright fallback failed: {exc.__class__.__name__}")
        rendered = inspect_html(rendered_html, rendered_url, checked_at)
        if rendered.status == PostingStatus.UNKNOWN and http_status in (401, 403):
            return PostingCheckResult(
                PostingStatus.UNKNOWN, checked_at, http_status, rendered_url, "PLAYWRIGHT",
                f"HTTP {http_status} blocked the direct request and the browser fallback did not receive a verifiable job page",
            )
        return PostingCheckResult(rendered.status, checked_at, http_status, rendered_url, "PLAYWRIGHT", rendered.reason)

    async def check(self, job_url: str) -> PostingCheckResult:
        checked_at = utc_now()
        headers = {"User-Agent": f"ApplicationTracker/{__version__} (+local job posting status checker)"}
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout_seconds, headers=headers) as client:
                response = await client.get(job_url)
        except httpx.TimeoutException:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, None, None, "ERROR", "Request timed out")
        except httpx.HTTPError as exc:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, None, None, "ERROR", f"Network request failed: {exc.__class__.__name__}")
        status = response.status_code
        final_url = str(response.url)
        if status in (404, 410):
            return PostingCheckResult(PostingStatus.CLOSED, checked_at, status, final_url, "HTTP", f"HTTP {status} confirms the posting is unavailable")
        if status in (401, 403):
            if self.browser_fallback is not None:
                return await self._browser_result(job_url, checked_at, status, final_url)
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, status, final_url, "HTTP", f"HTTP {status} prevented a reliable posting check")
        if status == 429 or status >= 500:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, status, final_url, "HTTP", f"HTTP {status} prevented a reliable posting check")
        if not 200 <= status < 300:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, status, final_url, "HTTP", f"HTTP {status} is inconclusive")
        result = inspect_html(response.text, final_url, checked_at)
        if result.status != PostingStatus.UNKNOWN or self.browser_fallback is None:
            return result
        return await self._browser_result(final_url, checked_at, status, final_url)


async def render_with_playwright(url: str) -> tuple[str, str]:
    """Optional fallback: no stealth settings, login, or anti-bot work is attempted."""
    from playwright.async_api import async_playwright
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            return await page.content(), page.url
        finally:
            await browser.close()
