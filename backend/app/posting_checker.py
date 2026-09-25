"""Conservative, deterministic job-posting inspection with no LLM dependency."""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html import unescape
import re
from typing import Awaitable, Callable

import extruct
import httpx
from bs4 import BeautifulSoup

from app import __version__
from app.models import PostingStatus, utc_now


STRONG_CLOSED_PHRASES = (
    "this job is no longer available", "this position has been filled", "applications are closed",
    "this job has expired", "we are no longer accepting applications", "job not found",
    "position is no longer available",
)
LIVE_SIGNALS = ("apply now", "apply for this job", "submit application", "job description")


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
    phrase = next((item for item in STRONG_CLOSED_PHRASES if item in text), None)
    if phrase:
        return PostingCheckResult(PostingStatus.CLOSED, checked_at, 200, final_url, "HTML", f"Page contains closed-posting phrase: {phrase}")
    signal = next((item for item in LIVE_SIGNALS if item in text), None)
    if signal:
        return PostingCheckResult(PostingStatus.LIVE, checked_at, 200, final_url, "HTML", f"Page contains live-posting signal: {signal}")
    return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, 200, final_url, "HTTP", "No conclusive structured metadata or posting text signal found")


class PostingChecker:
    def __init__(self, timeout_seconds: float = 12, browser_fallback: Callable[[str], Awaitable[tuple[str, str]]] | None = None):
        self.timeout_seconds = timeout_seconds
        self.browser_fallback = browser_fallback

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
        if status in (401, 403, 429) or status >= 500:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, status, final_url, "HTTP", f"HTTP {status} prevented a reliable posting check")
        if not 200 <= status < 300:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, status, final_url, "HTTP", f"HTTP {status} is inconclusive")
        result = inspect_html(response.text, final_url, checked_at)
        if result.status != PostingStatus.UNKNOWN or self.browser_fallback is None or len(normalized_text(response.text)) > 300:
            return result
        try:
            rendered_html, rendered_url = await self.browser_fallback(final_url)
        except (ImportError, ModuleNotFoundError):
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, status, final_url, "ERROR", "Playwright fallback unavailable")
        except Exception as exc:
            return PostingCheckResult(PostingStatus.UNKNOWN, checked_at, status, final_url, "ERROR", f"Playwright fallback failed: {exc.__class__.__name__}")
        rendered = inspect_html(rendered_html, rendered_url, checked_at)
        return PostingCheckResult(rendered.status, checked_at, status, rendered_url, "PLAYWRIGHT", rendered.reason)


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
