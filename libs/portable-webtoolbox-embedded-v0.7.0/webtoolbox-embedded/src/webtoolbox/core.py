"""Reusable async toolbox: search -> fetch -> extract -> short evidence-backed output."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
import logging
from weakref import WeakValueDictionary
from contextvars import ContextVar
from collections.abc import Awaitable, Callable
from collections import OrderedDict
from typing import Any
from urllib.parse import urljoin, urlsplit
import httpx
from bs4 import BeautifulSoup

from .cache import SQLiteCache
from .extract import approx_tokens, compact_text, extract_fields, read_recipe
from .providers import ddgs_search, searxng_search
from .security import UnsafeURLError, validate_url
from .settings import Settings
from .profiles import KeywordProfile, load_profile
from .identity import EmployerContext, domain, site_identity
from .jobs import JobHandle
from .search_results import normalize_hits
from .contacts import extract_contacts, assess_employer, extract_contact_links, extract_source_dates
from .ranking import merge_and_rank, shortlist_summary
from .frontier import contact_page_priority
from .job_postings import (platform_of, canonical_job_url, is_specific_job_url,
                           job_route, posting_identity, is_individual_job_page, parse_job_page, assess_status, match_job)

logger = logging.getLogger(__name__)
# Scoped to each asyncio task; simultaneous jobs cannot overwrite each other's evidence.
_active_handle: ContextVar[JobHandle | None] = ContextVar("webtoolbox_active_handle", default=None)
_progress_hook: ContextVar[Callable[[dict[str, Any]], Any] | None] = ContextVar("webtoolbox_progress_hook", default=None)


def _keyword_results(payload: dict[str, Any], profile: KeywordProfile, mode: str = "rank") -> dict[str, Any]:
    """Rank or optionally filter hits without changing cached raw provider results."""
    if mode not in {"rank", "filter"}:
        raise ValueError("keyword_mode must be rank or filter")
    items = []
    rejected = 0
    for hit in payload.get("results", []):
        flags = profile.score_text(" ".join(str(hit.get(k, "")) for k in ("title", "snippet", "url")))
        if mode == "filter" and not flags["eligible"]:
            rejected += 1
            continue
        items.append({**hit, "keyword_match": flags})
    items.sort(key=lambda entry: (-entry["keyword_match"]["score"], entry.get("rank", 999)))
    return {**payload, "results": items, "keyword_omitted": rejected,
            "keyword_mode": mode}


def _limited_keyword_results(payload: dict[str, Any], profile: KeywordProfile,
                             mode: str, limit: int) -> dict[str, Any]:
    # First rank the *entire* stored result set. Cutting it before ranking
    # can drop a relevant hit that appeared below several irrelevant results.
    scored = _keyword_results(payload, profile, mode)
    scored["results"] = scored["results"][:limit]
    return scored


def _key(prefix: str, *values: object) -> str:
    # Stable independent key space for search, raw pages and extraction views.
    raw = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str)
    return prefix + ":" + hashlib.sha256(raw.encode()).hexdigest()


def _fit_response(response: dict[str, Any], budget: int) -> dict[str, Any]:
    """Apply approximate budgets without shortening addresses, URLs or extracted fields."""
    out = dict(response)
    total_counts = {name: len(response[name]) for name in ("candidates", "matches", "results") if isinstance(response.get(name), list)}
    budget = max(120, min(8000, budget))
    # Preserve cache contents; never mutate nested fields through a result view.
    for name in ("results", "matches", "application_links", "application_destinations", "route_rejections", "candidates", "contact_links", "warnings", "attempts", "search_attempts", "crawl_attempts"):
        if isinstance(out.get(name), list):
            out[name] = list(out[name])
    if isinstance(out.get("fields"), dict):
        out["fields"] = dict(out["fields"])
    metadata = {"omitted_records": 0, "omitted_fields": 0, "omitted_text_chars": 0, "reasons": []}

    def size() -> int:
        # Approximate model tokens including the final diagnostic envelope.
        return approx_tokens(json.dumps({**out, "truncation": metadata}, ensure_ascii=False, default=str)) + 10

    for _ in range(1000):
        if size() <= budget:
            break
        if isinstance(out.get("text"), str) and out["text"]:
            # Text excerpts, not evidence values, may be shortened at line boundaries.
            text = out["text"]
            lines = text.splitlines(keepends=True)
            cut = lines[-1] if lines else text
            out["text"] = text[:-len(cut)] if cut else ""
            metadata["omitted_text_chars"] += len(cut)
            if "text_excerpt_shortened" not in metadata["reasons"]:
                metadata["reasons"].append("text_excerpt_shortened")
            continue
        # Entire records may be omitted; no partial names, emails, URLs or evidence paths.
        collection = next((n for n in ("application_links", "application_destinations", "contact_links", "results", "matches", "candidates", "route_rejections") if out.get(n)), None)
        if collection:
            out[collection].pop()
            metadata["omitted_records"] += 1
            if "record_exceeds_budget" not in metadata["reasons"]:
                metadata["reasons"].append("record_exceeds_budget")
            continue
        if out.get("fields"):
            out["fields"].pop(next(reversed(out["fields"])))
            metadata["omitted_fields"] += 1
            if "field_exceeds_budget" not in metadata["reasons"]:
                metadata["reasons"].append("field_exceeds_budget")
            continue
        attempt_collection = next((n for n in ("attempts", "search_attempts", "crawl_attempts") if out.get(n)), None)
        if attempt_collection:
            # Preserve summary counts and completion state when verbose diagnostics won't fit.
            out[attempt_collection].pop()
            metadata["omitted_records"] += 1
            if "attempt_diagnostics_omitted" not in metadata["reasons"]:
                metadata["reasons"].append("attempt_diagnostics_omitted")
            continue
        if out.get("warnings"):
            out["warnings"].pop()
            metadata["omitted_records"] += 1
            if "warnings_omitted" not in metadata["reasons"]:
                metadata["reasons"].append("warnings_omitted")
            continue
        # Metadata alone can exceed a very small requested budget: report it honestly.
        metadata["reasons"].append("metadata_exceeds_budget")
        break
    if metadata["omitted_records"] or metadata["omitted_fields"] or metadata["omitted_text_chars"]:
        out["result_counts_before_budget"] = total_counts
        # A partial return cannot legitimately advertise a complete evidence set.
        if response.get("completion") == "complete" and (metadata["omitted_records"] or metadata["omitted_fields"]):
            out["completion"] = "partial"
            out["response_partial_reason"] = "output_budget"
    out["truncation"] = metadata
    out["approx_output_tokens"] = approx_tokens(json.dumps(out, ensure_ascii=False, default=str))
    return out


def _failure_outcome(exc: Exception) -> str:
    # Preserve rate-limit and transport distinction instead of treating both as empty.
    message = str(exc).lower()
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if "429" in message or "rate limit" in message or "ratelimit" in message or "too many requests" in message:
        return "rate_limited"
    return "upstream_error"


class CachedPageFailure(RuntimeError):
    """Short-lived reused upstream failure with its original HTTP status."""
    def __init__(self, url: str, result: dict[str, Any]):
        super().__init__(f"Cached {result['outcome']} for {url}")
        self.status = result.get("http_status")
        self.outcome = result["outcome"]
        self.cached_failure = True


class FetchBlocked(RuntimeError):
    """Remote page returned an explicit forbidden/method-not-allowed response."""
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} blocked {url}")
        self.status = status
        self.url = url


def rendering_signals(html: str) -> list[str]:
    """Only identify strong JS-shell signals, never assume short pages need rendering."""
    soup = BeautifulSoup(html, "html.parser")
    visible = soup.get_text(" ", strip=True)
    if len(visible) >= 180:
        return []
    signals = []
    if soup.select_one("#__next, #root, #app, [data-reactroot], [data-v-app]"):
        signals.append("application_mount_node")
    if soup.select("script[src]") and len(visible) < 90:
        signals.append("script_bundle_with_little_visible_text")
    if any(t in html.lower() for t in ("enable javascript", "requires javascript", "please enable js")):
        signals.append("javascript_required_notice")
    return signals if len(signals) >= 2 or "javascript_required_notice" in signals else []


class WebToolbox:
    """Drop-in async API and background task scheduler for any Python application."""

    def __init__(self, settings: Settings | None = None, *, on_request: Callable[[dict[str, Any]], Any] | None = None):
        self.settings = settings or Settings()
        self.profile = load_profile(self.settings.keyword_profile)
        self.cache = SQLiteCache(self.settings.cache_path)
        # trust_env=False avoids an implicit machine-wide proxy for arbitrary user URLs.
        self.client = httpx.AsyncClient(timeout=self.settings.request_timeout, trust_env=False, follow_redirects=False,
                                        headers={"User-Agent": "PortableWebToolbox/0.1 (+local-research)"})
        self._semaphore = asyncio.Semaphore(self.settings.concurrent_fetches)
        self._host_semaphores: dict[str, asyncio.Semaphore] = {}
        self._blocked_urls: set[str] = set()
        self._provider_cooldowns: dict[str, float] = {}
        self.on_request = on_request
        self._last_request: dict[str, float] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._browser: Any = None
        self._background_semaphore = asyncio.Semaphore(max(1, self.settings.background_concurrency))
        self._active_jobs: dict[str, JobHandle] = {}
        self._inflight_jobs: dict[str, JobHandle] = {}
        self._completed_jobs: OrderedDict[str, JobHandle] = OrderedDict()
        self._closed = False
        self._browser_lock = asyncio.Lock()
        # Weak locks deduplicate simultaneous page fetches without leaking URL keys.
        self._page_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

    async def __aenter__(self) -> "WebToolbox":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def close(self, *, cancel_pending: bool = False) -> None:
        """Graceful shutdown waits for submitted work; optionally cancels pending tasks."""
        if self._closed:
            return
        self._closed = True
        tasks = [job._task for job in self._active_jobs.values() if job._task is not None]
        if cancel_pending:
            for task in tasks:
                task.cancel()
        if tasks:
            # Recover failures from completed jobs so close is safe during shutdown.
            await asyncio.gather(*tasks, return_exceptions=True)
        if self._browser is not None:
            await self._browser.__aexit__(None, None, None)
            self._browser = None
        await self.client.aclose()

    def job(self, job_id: str) -> JobHandle | None:
        """Retrieve a submitted job while it is running or in bounded memory history."""
        return self._active_jobs.get(job_id) or self._completed_jobs.get(job_id)

    def _submit(self, operation: str, *args: object, on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
                on_progress: Callable[[dict[str, Any]], Any] | None = None,
                deadline_seconds: float | None = None, **kwargs: Any) -> JobHandle:
        """Schedule work on the caller's running event loop, deduplicating identical jobs."""
        if self._closed:
            raise RuntimeError("WebToolbox has been closed")
        # asyncio.create_task explicitly requires a running loop; no hidden threads.
        asyncio.get_running_loop()
        # Distinct callbacks require distinct jobs; they may still share fetched HTML.
        request_key = _key("inflight", operation, args, kwargs, id(on_result) if on_result else None,
                           id(on_progress) if on_progress else None, deadline_seconds)
        existing = self._inflight_jobs.get(request_key)
        if existing is not None and not existing.done:
            return existing
        if len(self._active_jobs) >= self.settings.max_pending_jobs:
            raise RuntimeError("Too many pending WebToolbox jobs")
        handle = JobHandle(id=str(uuid.uuid4()), operation=operation)

        async def execute() -> dict[str, Any]:
            handle_token = _active_handle.set(handle)
            progress_token = _progress_hook.set(on_progress)
            try:
                async with self._background_semaphore:
                    handle._state = "running"
                    if on_progress is not None:
                        feedback = on_progress({"job_id": handle.id, "state": "running", "operation": operation})
                        if asyncio.iscoroutine(feedback):
                            await feedback
                    # Deadlines apply to all network/extraction work within one job.
                    async def call() -> dict[str, Any]:
                        return await getattr(self, operation)(*args, **kwargs)
                    result = await asyncio.wait_for(call(), timeout=deadline_seconds) if deadline_seconds else await call()
                    handle._partial = result
                    if on_progress is not None:
                        feedback = on_progress({"job_id": handle.id, "state": "result", "operation": operation})
                        if asyncio.iscoroutine(feedback):
                            await feedback
                    if on_result is not None:
                        # Run app-side persistence before marking a job complete.
                        await on_result(result)
                    return result
            except asyncio.CancelledError:
                handle._state = "cancelled"
                raise
            except BaseException:
                handle._state = "failed"
                raise
            finally:
                _active_handle.reset(handle_token)
                _progress_hook.reset(progress_token)
                if handle._state == "running":
                    handle._state = "completed"

        task: asyncio.Task[dict[str, Any]] = asyncio.create_task(execute(), name=f"webtoolbox:{operation}:{handle.id}")
        handle._task = task
        self._active_jobs[handle.id] = handle
        self._inflight_jobs[request_key] = handle

        def finalize(completed: asyncio.Task[dict[str, Any]]) -> None:
            # Consume exceptions for callers that intentionally fire-and-forget.
            if not completed.cancelled():
                err = completed.exception()
                if err is not None:
                    logger.warning("WebToolbox job %s failed: %s", handle.id, err)
            self._active_jobs.pop(handle.id, None)
            if self._inflight_jobs.get(request_key) is handle:
                self._inflight_jobs.pop(request_key, None)
            self._completed_jobs[handle.id] = handle
            while len(self._completed_jobs) > self.settings.completed_job_history:
                self._completed_jobs.popitem(last=False)

        task.add_done_callback(finalize)
        return handle

    def submit_crawl(self, url: str, *, on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None, **kwargs: Any) -> JobHandle:
        """Run a crawl in the background; optionally persist via an async callback."""
        return self._submit("crawl", url, on_result=on_result, **kwargs)

    def submit_search(self, query: str, *, on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None, **kwargs: Any) -> JobHandle:
        """Schedule search while the application continues handling other work."""
        return self._submit("search", query, on_result=on_result, **kwargs)

    def submit_research(self, query: str, *, on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None, **kwargs: Any) -> JobHandle:
        """Schedule search plus page extraction, with an optional completion callback."""
        return self._submit("research", query, on_result=on_result, **kwargs)

    def submit_research_contacts(self, company: str, *, on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
                                 **kwargs: Any) -> JobHandle:
        """Background evidence-first contact research without an extra service."""
        return self._submit("research_contacts", company, on_result=on_result, **kwargs)

    def submit_discover_job(self, company: str, title: str, *,
                            on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
                            **kwargs: Any) -> JobHandle:
        """Search job URLs in-process without tying results to a specific app DB."""
        return self._submit("discover_job", company, title, on_result=on_result, **kwargs)

    def submit_check_job_status(self, url: str, *,
                                on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
                                **kwargs: Any) -> JobHandle:
        """Queue a single lightweight URL probe; never submit an application."""
        return self._submit("check_job_status", url, on_result=on_result, **kwargs)

    async def _progress(self, event: str, partial: dict[str, Any] | None = None) -> None:
        """Expose partial evidence to a cancelled caller without waiting for job success."""
        handle = _active_handle.get()
        if handle is not None and partial is not None:
            handle._partial = partial
        hook = _progress_hook.get()
        if hook is not None:
            feedback = hook({"event": event, "job_id": handle.id if handle else None,
                             "partial_count": len(partial.get("candidates", [])) if partial else 0})
            if asyncio.iscoroutine(feedback):
                await feedback

    async def _validate(self, url: str) -> str:
        # DNS lookup can block; perform URL validation outside the event loop.
        return await asyncio.to_thread(
            validate_url, url,
            allow_private=self.settings.allow_private_urls,
            allowed_hosts=self.settings.allowed_hosts,
        )

    async def _throttle(self, url: str) -> None:
        domain = urlsplit(url).hostname or ""
        lock = self._domain_locks.setdefault(domain, asyncio.Lock())
        async with lock:
            interval = self.settings.domain_delay_seconds
            wait = interval - (time.monotonic() - self._last_request.get(domain, 0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request[domain] = time.monotonic()

    async def _static_fetch(self, url: str) -> tuple[str, str]:
        """Host-isolated scheduling, validated redirects, bounded HTML and clear blocks."""
        for _ in range(4):
            target = await self._validate(url)
            if target in self._blocked_urls:
                raise FetchBlocked(403, target)
            host = urlsplit(target).hostname or ""
            host_sem = self._host_semaphores.setdefault(host, asyncio.Semaphore(max(1, self.settings.per_host_concurrency)))
            # Acquire the host permit first so blocked hosts don't occupy global slots.
            async with host_sem:
                await self._throttle(target)
                async with self._semaphore:
                    if self.on_request:
                        feedback = self.on_request({"url": target, "mode": "static"})
                        if asyncio.iscoroutine(feedback):
                            await feedback
                    async with self.client.stream("GET", target, headers={"Accept": "text/html,application/xhtml+xml"}) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise RuntimeError("Redirect without a Location header")
                            url = urljoin(target, location)
                            continue
                        if response.status_code in {403, 405}:
                            self._blocked_urls.add(target)
                            raise FetchBlocked(response.status_code, target)
                        response.raise_for_status()
                        if "html" not in response.headers.get("content-type", "").lower():
                            raise RuntimeError("Only HTML pages are supported")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 1024 * 1024:
                                raise RuntimeError("Page exceeds 1 MiB HTML limit")
                        return body.decode(response.encoding or "utf-8", errors="replace"), target
        raise RuntimeError("Too many HTTP redirects")

    async def _browser_fetch(self, url: str) -> tuple[str, str]:
        """Dynamic rendering is opt-in: Chromium is more expensive than HTTPX."""
        await self._validate(url)
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
        except ImportError as exc:
            raise RuntimeError("Install the browser extra: pip install -e '.[browser]' and run crawl4ai-setup") from exc
        if self._browser is None:
            # Multiple submitted browser jobs may start at once; initialize only once.
            async with self._browser_lock:
                if self._browser is None:
                    browser = AsyncWebCrawler(config=BrowserConfig(headless=True, verbose=False))
                    await browser.__aenter__()
                    self._browser = browser
        host = urlsplit(url).hostname or ""
        host_sem = self._host_semaphores.setdefault(host, asyncio.Semaphore(max(1, self.settings.per_host_concurrency)))
        async with host_sem, self._semaphore:
            await self._throttle(url)
            if self.on_request:
                feedback = self.on_request({"url": url, "mode": "browser"})
                if asyncio.iscoroutine(feedback):
                    await feedback
            # A per-run robots check is deliberate; do not circumvent site restrictions.
            result = await self._browser.arun(url, config=CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS, check_robots_txt=True, page_timeout=30000))
            if not result.success:
                raise RuntimeError(f"Browser extraction failed: {result.error_message}")
            final_url = str(result.url or url)
            await self._validate(final_url)
            if len(result.html or "") > 1024 * 1024:
                raise RuntimeError("Rendered HTML exceeds 1 MiB limit")
            return result.html, final_url

    async def _page(self, url: str, mode: str, refresh: bool) -> tuple[str, str, bool, bool, str | None]:
        if mode not in {"static", "browser", "auto"}:
            raise ValueError("mode must be static, browser or auto")
        validated = await self._validate(url)
        cache_key = _key("page", validated, mode)
        failure_key = _key("page-failure-v1", validated, mode)
        if not refresh and (failed := self.cache.get(failure_key)):
            # A recent 429/404/403 is an observation. Reusing it across keyword
            # profiles avoids repeated blocked requests without claiming vacancy closure.
            old = self.cache.get(cache_key, allow_stale=True)
            if old:
                return old["html"], old["final_url"], True, True, failed["outcome"]
            raise CachedPageFailure(validated, failed)
        if not refresh and (record := self.cache.get(cache_key)):
            return record["html"], record["final_url"], True, False, None
        lock = self._page_locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            self._page_locks[cache_key] = lock
        async with lock:
            if not refresh and (failed := self.cache.get(failure_key)):
                old = self.cache.get(cache_key, allow_stale=True)
                if old:
                    return old["html"], old["final_url"], True, True, failed["outcome"]
                raise CachedPageFailure(validated, failed)
            if not refresh and (record := self.cache.get(cache_key)):
                return record["html"], record["final_url"], True, False, None
            old = self.cache.get(cache_key, allow_stale=True)
            try:
                # Auto mode is intentionally *static* now; browser must be requested.
                html, final = await (self._browser_fetch(validated) if mode == "browser" else self._static_fetch(validated))
                self.cache.set(cache_key, {"html": html, "final_url": final}, self.settings.crawl_ttl)
                self.cache.delete(failure_key)
                return html, final, False, False, None
            except (httpx.HTTPError, RuntimeError) as exc:
                code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else getattr(exc, "status", None)
                outcome = "rate_limited" if code == 429 else "access_blocked" if code in {401, 403, 405} else "posting_unavailable" if code in {404, 410} else _failure_outcome(exc)
                self.cache.set(failure_key, {"http_status": code, "outcome": outcome},
                               60 if code in {401, 403, 405, 429} else 600 if code in {404, 410} else 20)
                if old:
                    return old["html"], old["final_url"], True, True, "blocked" if isinstance(exc, FetchBlocked) else "not_found" if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {404, 410} else _failure_outcome(exc)
                raise RuntimeError(f"Could not retrieve {validated}: {exc}") from exc

    async def search(self, query: str, *, limit: int = 5, refresh: bool = False,
                     max_tokens: int | None = None, provider: str | None = None,
                     official_domain: str | None = None, keyword_profile: KeywordProfile | dict | str | None = None,
                     keyword_mode: str = "rank") -> dict[str, Any]:
        """Keyless search with organic filtering, provenance and provider diagnostics."""
        if not query.strip() or len(query) > 300:
            raise ValueError("query must be between 1 and 300 characters")
        limit = max(1, min(limit, self.settings.max_search_results))
        profile = load_profile(keyword_profile) if keyword_profile is not None else self.profile
        provider = (provider or self.settings.search_provider).lower()
        key = _key("search-v2", provider, self.settings.searxng_url if provider == "searxng" else "",
                   query.casefold().strip(), official_domain or "")
        cached = self.cache.get(key) if not refresh else None
        if cached:
            return _fit_response(_limited_keyword_results({**cached, "cache_state": {
                "cached": True, "stale": False, "age_seconds": cached.get("cache_age_seconds", 0)}}, profile, keyword_mode, limit), max_tokens or self.settings.max_tokens)
        old = self.cache.get(key, allow_stale=True)
        try:
            if provider == "ddgs":
                raw = await ddgs_search(query, max(self.settings.max_search_results * 3, 20))
            elif provider == "searxng":
                raw = await searxng_search(query, max(self.settings.max_search_results * 3, 20), self.settings.searxng_url, self.client)
            else:
                raise ValueError("WT_SEARCH_PROVIDER must be ddgs or searxng")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Some DDGS versions raise instead of returning [] for a genuine empty query.
            message = str(exc).lower().strip()
            no_results = provider == "ddgs" and (
                "no results found" in message or "no results were found" in message)
            if no_results:
                raw = []
            else:
                outcome = _failure_outcome(exc)
                self._provider_cooldowns[provider] = time.monotonic() + self.settings.provider_cooldown_seconds if outcome == "rate_limited" else self._provider_cooldowns.get(provider, 0)
                if old is not None:
                    return _fit_response(_limited_keyword_results({**old, "warning": str(exc)[:130],
                        "outcome": outcome, "cache_state": {"cached": True, "stale": old["stale"],
                        "age_seconds": old.get("cache_age_seconds", 0)}}, profile, keyword_mode, limit), max_tokens or self.settings.max_tokens)
                # Provider problems are normal research outcomes, not proof that
                # the job or company lacks results. Cancellation still propagates.
                return _fit_response({"query": query, "provider": provider,
                    "results": [], "cached": False, "stale": False,
                    "outcome": outcome, "raw_count": 0, "usable_count": 0,
                    "filtered": {}, "warning": str(exc)[:130],
                    "cache_state": {"cached": False, "stale": False, "age_seconds": 0}},
                    max_tokens or self.settings.max_tokens)
        hits, filtered = normalize_hits(raw, provider, official_domain=official_domain)
        usable: list[dict[str, Any]] = []
        for item in hits:
            try:
                await self._validate(item["url"])
            except UnsafeURLError:
                filtered["invalid_url"] += 1
                continue
            usable.append(item)
        result = {"query": query, "provider": provider, "results": usable, "cached": False, "stale": False,
                  "outcome": "results" if raw else "empty", "raw_count": len(raw),
                  "usable_count": len(usable), "filtered": filtered,
                  "cache_state": {"cached": False, "stale": False, "age_seconds": 0}}
        self.cache.set(key, result, self.settings.search_ttl)
        return _fit_response(_limited_keyword_results(result, profile, keyword_mode, limit), max_tokens or self.settings.max_tokens)

    async def search_with_fallback(self, company: str, *, role: str = "", official_domain: str | None = None,
                                   providers: tuple[str, ...] | None = None,
                                   max_attempts: int | None = None, deadline_seconds: float | None = None,
                                   limit: int = 5, max_tokens: int = 3000,
                                   continue_for_contacts: bool = False,
                                   keyword_profile: KeywordProfile | dict | str | None = None) -> dict[str, Any]:
        """Bounded recruitment->identity->official-site ladder with attempt diagnostics."""
        profile = load_profile(keyword_profile) if keyword_profile is not None else self.profile
        forms = profile.queries("contact_queries", company=company, role=role, domain=official_domain or "")
        provider_names = (providers or (self.settings.search_provider,))[:2]
        provider_names = tuple(dict.fromkeys(provider_names))
        attempt_budget = max(1, min(6, max_attempts or self.settings.max_search_attempts))
        deadline = time.monotonic() + (deadline_seconds or self.settings.search_deadline_seconds)
        attempts: list[dict[str, Any]] = []
        hits: list[dict[str, Any]] = []
        seen: set[str] = set()
        stop_reason = "queries_exhausted"
        for query in forms:
            for provider in provider_names:
                if len(attempts) >= attempt_budget:
                    stop_reason = "attempt_budget"
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stop_reason = "deadline"
                    break
                if time.monotonic() < self._provider_cooldowns.get(provider, 0):
                    attempts.append({"query": query, "provider": provider, "outcome": "rate_limited",
                                     "raw_count": 0, "usable_count": 0, "cached": False,
                                     "reason": "provider_cooldown"})
                    continue
                try:
                    # Small outputs are not allowed to silently discard usable search hits.
                    result = await asyncio.wait_for(self.search(query, limit=limit, provider=provider,
                        official_domain=official_domain, max_tokens=8000, keyword_profile=profile), timeout=remaining)
                    entry = {"query": query, "provider": provider, "outcome": result["outcome"],
                             "raw_count": result.get("raw_count", 0), "usable_count": result.get("usable_count", 0),
                             "cached": result["cached"], "stale": result["stale"],
                             "filtered": result.get("filtered", {})}
                    attempts.append(entry)
                    for hit in result["results"]:
                        if hit["url"] not in seen:
                            seen.add(hit["url"])
                            hits.append(hit)
                    if hits and not result["stale"] and not continue_for_contacts:
                        stop_reason = "usable_results"
                        break
                except asyncio.CancelledError:
                    attempts.append({"query": query, "provider": provider, "outcome": "cancelled"})
                    raise
                except Exception as exc:
                    attempts.append({"query": query, "provider": provider, "outcome": _failure_outcome(exc),
                                     "raw_count": 0, "usable_count": 0, "cached": False, "reason": str(exc)[:130]})
            if stop_reason in {"usable_results", "attempt_budget", "deadline"}:
                break
        if len(attempts) >= attempt_budget and stop_reason == "queries_exhausted":
            stop_reason = "attempt_budget"
        failed = any(a["outcome"] in {"rate_limited", "upstream_error", "timeout"} for a in attempts)
        completion = "partial" if hits and failed else "complete" if hits or not failed else "unresolved"
        if continue_for_contacts:
            # A vacancy mirror is not useful evidence of a recruitment recipient.
            hits.sort(key=lambda h: (-contact_page_priority(h["url"],
                " ".join((h.get("title", ""), h.get("snippet", ""))),
                official_domain=official_domain or "", keyword_profile=profile), h.get("rank", 99)))
        return _fit_response({"schema_version": "1.0", "company": company,
            "results": hits[:limit], "attempts": attempts, "completion": completion,
            "stop_reason": stop_reason, "attempt_count": len(attempts)}, max_tokens)

    async def crawl(self, url: str, *, recipe: str | dict[str, Any] | None = None,
                    mode: str = "static", query: str = "", refresh: bool = False,
                    max_tokens: int | None = None, include_text: bool | None = None,
                    contacts: bool = False, employer: str | None = None,
                    known_domains: tuple[str, ...] = (), structured: bool = False,
                    record_selector: str | None = None, vacancy_url: str | None = None,
                    vacancy_reference: str | None = None,
                    keyword_profile: KeywordProfile | dict | str | None = None,
                    employer_context: EmployerContext | dict | None = None) -> dict[str, Any]:
        """Return portable recipe fields, or opt-in source-backed contact candidates."""
        spec = read_recipe(recipe)
        profile = load_profile(keyword_profile) if keyword_profile is not None else self.profile
        context = EmployerContext.from_mapping(employer_context, company=employer or "") if employer_context else None
        budget = max_tokens or self.settings.max_tokens
        try:
            html, final_url, cached, stale, upstream_failure = await self._page(url, mode, refresh)
        except RuntimeError as exc:
            if not structured:
                raise
            cause = exc.__cause__
            status = "blocked" if isinstance(cause, FetchBlocked) else _failure_outcome(exc)
            return {"schema_version": "1.0", "url": url, "outcome": status,
                    "error": str(exc)[:180], "candidates": [], "fields": {}, "cached": False, "stale": False}
        # Fetch age is not source publication age; use original cache save time.
        page_key = _key("page", await self._validate(url), mode)
        snapshot = self.cache.get(page_key, allow_stale=True)
        fetched_at = snapshot.get("fetched_at") if snapshot else time.time()
        cache_age = int(snapshot.get("cache_age_seconds", 0)) if cached and snapshot else 0
        fields = extract_fields(html, spec, final_url) if spec else {}
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True)[:160] if soup.title else ""
        result: dict[str, Any] = {"url": final_url, "title": title, "fields": fields,
                                  "cached": cached, "stale": stale, "mode": mode}
        signals = rendering_signals(html) if mode != "browser" else []
        if upstream_failure:
            result["upstream_outcome"] = upstream_failure
        if signals:
            result["outcome"] = "rendering_needed"
            result["rendering_signals"] = signals
        elif structured:
            result["outcome"] = upstream_failure or "results"
        if contacts:
            result["site_identity"] = site_identity(html, final_url)
            options = {"record_selector": record_selector} if record_selector else {}
            options.update(vacancy_url=vacancy_url, vacancy_reference=vacancy_reference, keyword_profile=profile)
            from datetime import datetime, timezone
            stamp = datetime.fromtimestamp(fetched_at, tz=timezone.utc).isoformat()
            candidates = extract_contacts(html, final_url, fetched_at=stamp, **options)
            dates = extract_source_dates(html)
            result["candidates"] = merge_and_rank([
                {**assess_employer(c, employer, known_domains=known_domains, employer_context=context),
                 "source_last_updated": dates["last_updated"],
                 "cache_stale": stale} for c in candidates
            ], keyword_profile=profile)
            result["contact_categories"] = shortlist_summary(result["candidates"])
            result["contact_links"] = extract_contact_links(html, final_url, keyword_profile=profile)
            result["source_dates"] = dates
            result["recommended"] = [c["email"] for c in result["candidates"] if c["email"]
                and c["purpose"] == "recruitment" and not c["exclusion_reason"]]
        want_text = not bool(spec or contacts) if include_text is None else include_text
        if want_text:
            main = soup.select_one(spec.get("content_selector", "main, article, [role=main]")) if spec else soup.select_one("main, article, [role=main]")
            candidate = main or soup.body or soup
            for node in candidate.select("script, style, nav, footer, noscript, svg, form"):
                node.decompose()
            content = candidate.get_text("\n", strip=True)
            result["text"] = compact_text(content, query=query, max_chars=min(14000, budget*4))
            if len(result["text"]) < len(content):
                result["text_reduction"] = {"removed_characters": len(content) - len(result["text"]),
                                            "reason": "noise_filtering_or_line_budget"}
        if contacts and "recommended" in result:
            # A published address is only recommended when evidence remains in the response.
            result.pop("recommended")
        if structured:
            result["schema_version"] = "1.0"
            result["cache_state"] = {"cached": cached, "stale": stale,
                "age_seconds": cache_age, "fetched_at_epoch": fetched_at}
        output = _fit_response(result, budget)
        if contacts:
            output["recommended"] = [c["email"] for c in output.get("candidates", [])
                if c.get("email") and c.get("purpose") == "recruitment" and not c.get("exclusion_reason")
                and c.get("contact_priority", {}).get("outreach_eligible")
                and c.get("emails") and any(e.get("evidence") for e in c["emails"])]
            if approx_tokens(json.dumps(output, ensure_ascii=False, default=str)) > budget:
                # Candidate records themselves carry purpose; recommendations are derived.
                output.pop("recommended")
            output["approx_output_tokens"] = approx_tokens(json.dumps(output, ensure_ascii=False, default=str))
        return output

    async def research(self, query: str, *, pages: int = 2, recipe: str | dict[str, Any] | None = None,
                       mode: str = "static", refresh: bool = False, max_tokens: int | None = None) -> dict[str, Any]:
        """Legacy compact search plus crawl, now with distinct failure diagnostics."""
        budget = max_tokens or self.settings.max_tokens
        pages = max(1, min(pages, self.settings.max_crawl_pages))
        try:
            search_response = await self.search(query, limit=max(3, pages), refresh=refresh, max_tokens=3000)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return _fit_response({"query": query, "results": [], "warnings": [str(exc)[:130]],
                "search_attempts": [{"outcome": _failure_outcome(exc), "provider": self.settings.search_provider}],
                "completion": "unresolved"}, budget)
        if search_response.get("outcome") in {"rate_limited", "timeout", "upstream_error"} and not search_response.get("results"):
            return _fit_response({"query": query, "provider": search_response["provider"],
                "results": [], "warnings": [search_response.get("warning", "")],
                "search_attempts": [{"outcome": search_response["outcome"],
                                     "provider": search_response["provider"]}],
                "completion": "unresolved"}, budget)
        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        blocked: set[str] = set()
        for hit in search_response["results"][:pages]:
            if hit["url"] in blocked:
                continue
            try:
                page = await self.crawl(hit["url"], recipe=recipe, mode=mode, query=query,
                    refresh=refresh, max_tokens=max(180, budget // pages), include_text=True)
                results.append({"url": page["url"], "title": page["title"],
                    "snippet": page.get("text", ""), "fields": page["fields"],
                    "cached": page["cached"], "stale": page["stale"],
                    "outcome": page.get("outcome", "results")})
                await self._progress("page_complete", {"results": list(results)})
            except (ValueError, RuntimeError, httpx.HTTPError) as exc:
                if isinstance(exc.__cause__, FetchBlocked):
                    blocked.add(hit["url"])
                warnings.append(f"{hit['url']}: {str(exc)[:130]}")
        return _fit_response({"query": query, "provider": search_response["provider"],
            "results": results, "warnings": warnings}, budget)

    async def research_contacts(self, company: str, *, role: str = "", official_domain: str | None = None,
                                providers: tuple[str, ...] | None = None, pages: int = 3,
                                deadline_seconds: float | None = None, max_tokens: int = 6500,
                                vacancy_url: str | None = None,
                                vacancy_reference: str | None = None,
                                target_region: str | None = None,
                                target_sector: str | None = None,
                                employer_context: EmployerContext | dict | None = None,
                                keyword_profile: KeywordProfile | dict | str | None = None) -> dict[str, Any]:
        """Search, rank the crawl frontier and collect evidence before recommending.

        The query ladder continues after mirror hits, up to the configured search
        attempt budget. Relevant contact pages discovered inside fetched HTML may
        take a remaining crawl slot. The application owns durable job storage.
        """
        deadline = time.monotonic() + (deadline_seconds or self.settings.search_deadline_seconds)
        profile = load_profile(keyword_profile) if keyword_profile is not None else self.profile
        # Legacy official_domain is a supplied hint, not proof of identity.
        context = (EmployerContext.from_mapping(employer_context, company=company)
                   if employer_context else EmployerContext(company=company, domain=official_domain or "",
                                                           status="provisional" if official_domain else "unknown"))
        allowed_domain = context.domain or official_domain or ""
        page_limit = min(max(1, pages), self.settings.max_crawl_pages)
        searches = await self.search_with_fallback(
            company, role=role, official_domain=allowed_domain or None,
            providers=providers, continue_for_contacts=True, limit=max(page_limit * 4, 8),
            deadline_seconds=max(0.1, deadline - time.monotonic()), max_tokens=7500,
            keyword_profile=profile)
        candidates: list[dict[str, Any]] = []
        crawl_attempts: list[dict[str, Any]] = []
        # Only evidence-focused source pages are crawled; mirrors may be visited
        # when they are the only available source, but not ahead of official links.
        frontier: dict[str, dict[str, Any]] = {}
        excluded_domains: list[dict[str, str]] = []
        def enqueue(url: str, *, label: str = "", from_url: str = "", seed: bool = False) -> None:
            try:
                from .security import normalized_url
                canonical = normalized_url(url)
            except (ValueError, UnsafeURLError):
                return
            # A verified domain is a hard research boundary, not a ranking boost.
            # Unknown domains can be researched as leads only when no employer
            # domain is supplied; their contacts are never outreach-eligible.
            if allowed_domain and not context.allows_crawl(canonical):
                excluded_domains.append({"url": canonical, "reason": "outside_employer_context"})
                return
            priority = contact_page_priority(canonical, label, official_domain=allowed_domain,
                                             keyword_profile=profile)
            # Neutral seed pages are valid starting points for internal links.
            if priority <= -20 or (priority < 0 and not seed):
                return
            if seed:
                priority = max(priority, 1)
            if allowed_domain and context.allows_crawl(canonical):
                priority += 20
            if any(x in urlsplit(canonical).path.casefold() for x in
                   ("contact", "equipe", "team", "people", "recrut", "career")):
                priority += 20
            if vacancy_url and canonical == vacancy_url:
                priority += 10
            if not seed and priority < 1:
                return
            # Strictly same-origin expansion unless the host app explicitly
            # supplied a known company domain. External social/vendor links are skipped.
            if from_url:
                src = (urlsplit(from_url).hostname or "").lower()
                dst = (urlsplit(canonical).hostname or "").lower()
                sanctioned = allowed_domain and context.allows_crawl(canonical)
                if dst != src and not sanctioned:
                    return
            if canonical not in frontier or priority > frontier[canonical]["priority"]:
                frontier[canonical] = {"url": canonical, "priority": priority,
                                       "label": label, "discovered_from": from_url or None}
        for hit in searches["results"]:
            enqueue(hit["url"], label=" ".join((hit.get("title", ""), hit.get("snippet", ""))), seed=True)
        # Seed the supplied employer homepage even if the search provider cached
        # an empty result. Do not invent likely contact-page URLs.
        if allowed_domain:
            enqueue(f"https://{allowed_domain}/", label="employer homepage", seed=True)
        attempted: set[str] = set()
        while frontier and len(crawl_attempts) < page_limit and time.monotonic() < deadline:
            entry = max(frontier.values(), key=lambda x: (x["priority"], x["url"]))
            frontier.pop(entry["url"])
            url = entry["url"]
            if url in attempted:
                continue
            attempted.add(url)
            try:
                page = await asyncio.wait_for(self.crawl(
                    url, structured=True, contacts=True, employer=company,
                    known_domains=(allowed_domain,) if allowed_domain else (),
                    vacancy_url=vacancy_url, vacancy_reference=vacancy_reference,
                    keyword_profile=profile, employer_context=context,
                    max_tokens=14000), timeout=max(0.1, deadline - time.monotonic()))
                crawl_attempts.append({"url": url, "outcome": page.get("outcome", "results"),
                    "candidate_count": len(page.get("candidates", [])),
                    "cached": page.get("cached", False), "stale": page.get("stale", False),
                    "cache_age_seconds": page.get("cache_state", {}).get("age_seconds", 0),
                    "frontier_priority": entry["priority"]})
                for candidate in page.get("candidates", []):
                    # Each source stays fresh/stale independently even after dedupe.
                    source_context = {"description": " ".join((candidate.get("role") or "", page.get("title") or "")),
                                      "region": candidate.get("source_region") or "",
                                      "sector": candidate.get("source_sector") or ""}
                    candidates.append(assess_employer(candidate, company,
                        known_domains=(allowed_domain,) if allowed_domain else (),
                        target_region=target_region, target_sector=target_sector,
                        employer_context=context,
                        source_context={**source_context, "site_identity": page.get("site_identity", {})}) | {"cache_stale": page.get("stale", False)})
                # Following a contact/team link may be more valuable than another
                # general jobs listing. These links are never assumed to belong
                # to the hiring team simply because they share a domain.
                for link in page.get("contact_links", []):
                    enqueue(link["url"], label=link.get("label", ""), from_url=url)
                await self._progress("page_complete", {"candidates": list(candidates),
                    "search_attempts": searches["attempts"], "crawl_attempts": list(crawl_attempts)})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                crawl_attempts.append({"url": url, "outcome": _failure_outcome(exc), "error": str(exc)[:140]})
        candidates = merge_and_rank(candidates, keyword_profile=profile)
        recommended = [c for c in candidates if c.get("email") and c.get("purpose") == "recruitment"
                       and not c.get("exclusion_reason") and
                       c.get("contact_priority", {}).get("outreach_eligible")]
        bad = any(x["outcome"] not in {"results", "rendering_needed"} for x in crawl_attempts)
        incomplete = searches["completion"] != "complete" or bad or bool(frontier) or time.monotonic() >= deadline
        completion = "partial" if candidates and incomplete else "complete" if candidates else "unresolved"
        return _fit_response({"schema_version": "1.1", "company": company, "completion": completion,
            "stop_reason": "deadline" if time.monotonic() >= deadline else
                 "page_limit" if frontier and len(crawl_attempts) >= page_limit else searches["stop_reason"],
            "candidates": candidates, "contact_categories": shortlist_summary(candidates),
            "recommended_count": len(recommended), "search_attempts": searches["attempts"],
            "crawl_attempts": crawl_attempts, "cache_state": "per_source_observation",
            "employer_context": {"domain": context.domain, "status": context.status,
                                 "evidence_source": context.evidence_source},
            "excluded_domains": excluded_domains[:15],
            "unvisited_pages": len(frontier),
            "page_budget_exhausted": bool(frontier and len(crawl_attempts) >= page_limit)}, max_tokens)

    async def check_job_status(self, url: str, *, refresh: bool = False,
                               mode: str = "static", max_tokens: int = 1400,
                               keyword_profile: KeywordProfile | dict | str | None = None) -> dict[str, Any]:
        """Check whether an individual vacancy still has an accessible application path.

        Returns LIVE, CLOSED or UNKNOWN. A 403, CAPTCHA, stale snapshot or
        inaccessible form must NEVER be reported as a vacancy closure.
        """
        if mode not in {"static", "browser"}:
            raise ValueError("mode must be static or browser; browser rendering requires opt-in")
        validated = await self._validate(url)
        canonical = canonical_job_url(validated)
        platform = platform_of(canonical)
        profile = load_profile(keyword_profile) if keyword_profile is not None else self.profile
        key = _key("job-status-v2", canonical, mode,
                   {name: profile.data[name] for name in ("job_closed", "job_apply", "job_blocked")})
        if not refresh and (cached := self.cache.get(key)):
            return _fit_response({**cached, "cached": True, "cache_state": {
                "cached": True, "stale": False, "age_seconds": cached["cache_age_seconds"]}}, max_tokens)

        from datetime import datetime, timezone
        checked = datetime.now(timezone.utc).isoformat()
        base = {"schema_version": "1.0", "posting_url": canonical, "requested_url": url,
                "platform": platform, "status": "UNKNOWN", "confidence": "low",
                "reason": "insufficient_evidence", "signals": [], "checked_at": checked,
                "application_url": None, "application_links": [], "cached": False,
                "cache_state": {"cached": False, "stale": False, "age_seconds": 0},
                "method": mode}
        route = job_route(canonical)
        if route["kind"] in {"non_job", "application"}:
            # Search/category pages and ATS application forms are not individual postings.
            return _fit_response({**base, "reason": "not_a_specific_job_url", "route": route}, max_tokens)
        try:
            # A status probe bypasses the potentially 24-hour page cache when due.
            html, final_url, cached, stale, upstream = await self._page(validated, mode, refresh=True)
            if upstream == "not_found":
                # Previous HTML cannot overrule the latest 404/410 observation.
                result = {**base, "status": "CLOSED", "confidence": "medium",
                    "reason": "posting_unavailable", "signals": ["fresh_job_url_not_found"]}
                self.cache.set(key, result, self.settings.job_status_ttl)
                return _fit_response(result, max_tokens)
            if stale or upstream:
                # Stale evidence can be displayed elsewhere, but must not determine status.
                return _fit_response({**base, "reason": "upstream_unavailable",
                    "upstream_outcome": upstream, "cached": cached,
                    "cache_state": {"cached": cached, "stale": stale}}, max_tokens)
            if canonical_job_url(final_url) != canonical:
                # Job sites commonly redirect expired jobs to general listings/login.
                return _fit_response({**base, "resolved_url": final_url,
                    "reason": "redirected_from_posting"}, max_tokens)
            page = parse_job_page(html, final_url, keyword_profile=profile)
            if route["kind"] == "inspect" and not is_individual_job_page(page, final_url):
                return _fit_response({**base, "reason": "insufficient_individual_posting_evidence", "route": route}, max_tokens)
            signals = rendering_signals(html) if mode == "static" else []
            status, reason, confidence, evidence = assess_status(page, canonical,
                rendering_needed=bool(signals))
            best = page["application_links"][0]["url"] if page["application_links"] else None
            result = {**base, "status": status, "reason": reason, "confidence": confidence,
                      "signals": evidence + signals, "title": page["title"],
                      "company": page["company"], "location": page["location"],
                      "application_url": best, "application_links": page["application_links"][:3]}
            # Unknown states get short TTL so an app does not consider silence a decision.
            self.cache.set(key, result, self.settings.job_status_ttl if status != "UNKNOWN" else 90)
            return _fit_response(result, max_tokens)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            cause = exc.__cause__ or exc
            status_code = cause.response.status_code if isinstance(cause, httpx.HTTPStatusError) else getattr(cause, "status", None)
            # 404/410 mean the posting URL disappeared, not necessarily that
            # the employer stopped hiring or that another valid posting doesn't exist.
            if status_code in {404, 410}:
                result = {**base, "status": "CLOSED", "confidence": "medium",
                    "reason": "posting_unavailable", "http_status": status_code,
                    "signals": ["job_url_returned_404_or_410"]}
                self.cache.set(key, result, self.settings.job_status_ttl)
                return _fit_response(result, max_tokens)
            result = {**base, "reason": "access_blocked" if status_code in {401, 403, 405, 429} else "fetch_error",
                "http_status": status_code, "error": type(cause).__name__}
            return _fit_response(result, max_tokens)

    async def discover_job(self, company: str, title: str, *, location: str = "",
                           contract_type: str = "", seed_urls: tuple[str, ...] = (),
                           pages: int = 4, provider: str | None = None,
                           refresh: bool = False, max_tokens: int = 4000,
                           deadline_seconds: float = 45,
                           keyword_profile: KeywordProfile | dict | str | None = None,
                           keyword_mode: str = "rank", search_title: str | None = None,
                           reference: str = "", seniority: str = "",
                           employer_context: EmployerContext | dict | None = None) -> dict[str, Any]:
        """Find individual vacancies with explicit route/query/fetch provenance.

        `search_title` broadens discovery queries only; matching ALWAYS uses the
        caller's original title. Candidate URLs are not presumed equivalent from
        company/title alone. ATS application forms remain destinations, not jobs.
        """
        if not company.strip() or not title.strip():
            raise ValueError("company and title are required")
        if keyword_mode not in {"rank", "filter"}:
            raise ValueError("keyword_mode must be rank or filter")
        requested_pages = pages
        pages = max(1, min(pages, self.settings.max_job_discovery_pages))
        deadline = time.monotonic() + max(1, deadline_seconds)
        profile = load_profile(keyword_profile) if keyword_profile is not None else self.profile
        identity = EmployerContext.from_mapping(employer_context, company=company) if employer_context is not None else None
        query_forms = profile.queries("job_queries", company=company, title=search_title or title, location=location)
        max_queries = min(len(query_forms), self.settings.max_search_attempts)
        attempts: list[dict[str, Any]] = []
        route_rejections: list[dict[str, Any]] = []
        eligible: dict[str, dict[str, Any]] = {}
        destinations: list[dict[str, Any]] = []
        search_count = 0
        hosts_deferred: dict[str, dict[str, Any]] = {}
        stop_reason = "search_exhausted"
        query_stop_reason = "queries_exhausted" if query_forms else "no_query_forms"

        def collect(item: dict[str, Any]) -> None:
            original = str(item.get("url", ""))
            try:
                canonical = canonical_job_url(original)
                route = job_route(canonical)
            except (ValueError, UnsafeURLError):
                route_rejections.append({"url": original, "reason": "invalid_url"})
                return
            if route["kind"] == "application":
                destinations.append({"url": canonical, "source": item.get("provider"),
                                     "relation": "unlinked_application_destination"})
                route_rejections.append({"url": canonical, "reason": "application_not_posting"})
                return
            if route["kind"] == "non_job":
                route_rejections.append({"url": canonical, "reason": route["reason"]})
                return
            # For unfamiliar search results, require at least a role token in the
            # result heading, but let explicit seeds pass for HTML inspection.
            if route["kind"] == "inspect" and item.get("provider") != "seed":
                from .job_postings import _terms
                if not _terms(title) & _terms(str(item.get("title", ""))):
                    route_rejections.append({"url": canonical, "reason": "unrecognized_route_without_title_evidence"})
                    return
            if canonical not in eligible:
                eligible[canonical] = {**item, "url": canonical, "route": route}

        for original_url in seed_urls:
            collect({"url": original_url, "original_url": original_url,
                     "provider": "seed", "title": title, "snippet": ""})
        # Only definitely recognized postings can satisfy a pre-fetch stop. An
        # inspect-only route is not confirmed before reading its page.
        def recognized_count() -> int:
            return sum(1 for item in eligible.values() if item["route"]["kind"] == "specific")

        if recognized_count() < pages:
            for query in query_forms[:max_queries]:
                if time.monotonic() >= deadline:
                    query_stop_reason = "deadline"
                    break
                search_count += 1
                try:
                    response = await asyncio.wait_for(self.search(
                        query.strip(), limit=self.settings.max_search_results,
                        provider=provider, refresh=refresh, max_tokens=5500,
                        keyword_profile=profile, keyword_mode=keyword_mode),
                        timeout=max(.1, deadline - time.monotonic()))
                    attempts.append({"stage": "search", "query": query,
                        "provider": response.get("provider"), "outcome": response.get("outcome", "unknown"),
                        "raw_count": response.get("raw_count", 0), "usable_count": response.get("usable_count", 0),
                        "keyword_omitted": response.get("keyword_omitted", 0),
                        "returned_count": len(response.get("results", [])),
                        "cache_state": response.get("cache_state")})
                    for item in response.get("results", []):
                        collect(item)
                except asyncio.CancelledError:
                    raise
                except asyncio.TimeoutError:
                    attempts.append({"stage": "search", "query": query, "outcome": "timeout"})
                except Exception as exc:
                    attempts.append({"stage": "search", "query": query,
                                     "outcome": _failure_outcome(exc), "error_type": type(exc).__name__})
                if recognized_count() >= pages:
                    query_stop_reason = "eligible_route_cap"
                    break
            else:
                if len(query_forms) > max_queries:
                    query_stop_reason = "query_budget_exhausted"
        else:
            query_stop_reason = "seed_cap"

        # Prefer supplied originals, then specific job routes, then unknown
        # routes. Never let ambiguous paths displace confirmed detail routes.
        ranked = sorted(eligible.values(), key=lambda x: (
            x.get("provider") != "seed", x["route"]["kind"] != "specific",
            x.get("rank", 999)))
        matches: list[dict[str, Any]] = []
        inspected = 0
        for hit in ranked:
            if inspected >= pages:
                stop_reason = "page_limit"
                break
            if time.monotonic() >= deadline:
                stop_reason = "deadline"
                break
            url = hit["url"]
            host = urlsplit(url).hostname or ""
            if host in hosts_deferred:
                attempts.append({"stage": "crawl", "url": url, "outcome": "deferred_host_cooldown",
                                 "trigger_url": hosts_deferred[host]["url"], "trigger_status": 429})
                continue
            inspected += 1
            try:
                html, final_url, cached, stale, failure = await asyncio.wait_for(
                    self._page(url, "static", refresh), timeout=max(.1, deadline - time.monotonic()))
                if failure or stale:
                    attempts.append({"stage": "crawl", "url": url, "outcome": failure or "stale_cache",
                                     "cached": cached, "stale": stale})
                    continue
                redirect_to = None
                if canonical_job_url(final_url) != url:
                    final_route = job_route(final_url)
                    attempts.append({"stage": "crawl", "url": url, "outcome": "redirected_from_posting",
                                     "resolved_url": final_url,
                                     "redirect_kind": final_route["kind"]})
                    if final_route["kind"] == "application":
                        destinations.append({"url": final_url, "source": "redirect",
                                             "posting_url": url, "relation": "verified_redirect_to_application"})
                    if final_route["kind"] != "specific":
                        continue
                    redirect_to = canonical_job_url(final_url)
                page = parse_job_page(html, final_url, keyword_profile=profile)
                if hit["route"]["kind"] == "inspect" and not is_individual_job_page(page, final_url):
                    attempts.append({"stage": "crawl", "url": url,
                                     "outcome": "not_individual_posting", "reason": "insufficient_page_evidence"})
                    continue
                render = rendering_signals(html)
                status, reason, confidence, signals = assess_status(page, url, rendering_needed=bool(render))
                match = match_job(page, title=title, company=company, location=location,
                                  contract_type=contract_type, reference=reference,
                                  seniority=seniority, search_hit=hit,
                                  employer_context=identity, source_url=final_url)
                links = [{**link, "posting_url": redirect_to or url, "relation": "published_on_posting"}
                         for link in page["application_links"][:3]]
                effective_url = redirect_to or url
                entry = {"posting_url": effective_url, "original_url": hit.get("original_url", url),
                    "posting_identity": posting_identity(effective_url),
                    "declared_canonical_url": page.get("declared_canonical_url"),
                    "schema_posting_url": page.get("schema_posting_url"),
                    "redirected_from": url if redirect_to else None,
                    "platform": platform_of(url), "route": hit["route"], "title": page["title"],
                    "company": page["company"], "publisher": page.get("publisher"),
                    "employer_evidence": page.get("employer_evidence"),
                    "location": page["location"], "location_evidence": page.get("location_evidence"),
                    "identifier": page.get("identifier"), "match": match,
                    "posting_status": status, "status_reason": reason,
                    "status_confidence": confidence, "application_url": links[0]["url"] if links else None,
                    "application_links": links, "cached": cached,
                    "source": hit.get("provider", "unknown"),
                    "instance_equivalence": "verified_http_redirect" if redirect_to else "unverified"}
                matches.append(entry)
                await self._progress("job_found", {"matches": list(matches)})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                cause = exc.__cause__ or exc
                code = cause.response.status_code if isinstance(cause, httpx.HTTPStatusError) else getattr(cause, "status", None)
                outcome = "rate_limited" if code == 429 else "access_blocked" if code in {401, 403, 405} else "posting_unavailable" if code in {404, 410} else _failure_outcome(cause)
                attempts.append({"stage": "crawl", "url": url, "outcome": outcome,
                                 "http_status": code, "error_type": type(cause).__name__,
                                 "cached_failure": isinstance(cause, CachedPageFailure)})
                if code == 429:
                    hosts_deferred[host] = {"url": url}
        matches.sort(key=lambda m: (m["match"]["score"], m["posting_status"] == "LIVE",
                   bool(m["application_url"])), reverse=True)
        if stop_reason == "search_exhausted":
            stop_reason = "deadline" if time.monotonic() >= deadline else "page_limit" if len(ranked) > inspected else query_stop_reason
        has_errors = any(a.get("outcome") not in {"results", "empty"} for a in attempts)
        incomplete = has_errors or inspected < len(ranked) or search_count < len(query_forms) and query_stop_reason not in {"seed_cap", "eligible_route_cap"}
        completion = "partial" if matches and incomplete else "complete" if matches else "unresolved"
        return _fit_response({"schema_version": "1.1", "company": company, "title": title,
                "search_title": search_title or title, "location": location,
                "contract_type": contract_type, "reference": reference,
                "employer_context": {"domain": identity.domain, "status": identity.status,
                                     "evidence_source": identity.evidence_source} if identity else None,
                "completion": completion, "matches": matches,
                "application_destinations": destinations,
                "search_attempts": attempts, "route_rejections": route_rejections,
                "route_rejection_count": len(route_rejections),
                "eligible_route_count": len(ranked), "inspected_page_count": inspected,
                "query_count": search_count, "query_budget": max_queries,
                "untried_queries": max(0, len(query_forms) - search_count),
                "query_stop_reason": query_stop_reason, "keyword_mode": keyword_mode,
                "requested_page_cap": requested_pages, "effective_page_cap": pages,
                "page_budget_setting": "max_job_discovery_pages",
                "unvisited_candidates": max(0, len(ranked) - inspected),
                "stop_reason": stop_reason}, max_tokens)
