"""Reusable async toolbox: search -> fetch -> extract -> short evidence-backed output."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
import logging
from weakref import WeakValueDictionary
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
from .jobs import JobHandle

logger = logging.getLogger(__name__)


def _key(prefix: str, *values: object) -> str:
    # Stable independent key space for search, raw pages and extraction views.
    raw = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str)
    return prefix + ":" + hashlib.sha256(raw.encode()).hexdigest()


def _fit_response(response: dict[str, Any], budget: int) -> dict[str, Any]:
    """Bound returned JSON size; token counts are approximate, not billed usage."""
    out = dict(response)
    budget = max(120, min(8000, budget))
    # Copy mutable nested structures: truncating output must not corrupt the cache.
    if isinstance(out.get("results"), list):
        out["results"] = [dict(item) for item in out["results"]]
    if isinstance(out.get("fields"), dict):
        out["fields"] = dict(out["fields"])
    for _ in range(150):
        size = approx_tokens(json.dumps(out, ensure_ascii=False)) + 10  # Metadata allowance.
        if size <= budget:
            break
        if isinstance(out.get("text"), str) and len(out["text"]) > 50:
            out["text"] = out["text"][:max(50, int(len(out["text"]) * 0.72))]
            continue
        # Keep the search result URLs and cut snippets before discarding a source.
        results = out.get("results", [])
        if isinstance(results, list):
            largest = max((i for i in results if isinstance(i, dict)),
                          key=lambda i: len(i.get("snippet", "")), default=None)
            if largest is not None and len(largest.get("snippet", "")) > 55:
                largest["snippet"] = largest["snippet"][:max(55, int(len(largest["snippet"]) * 0.7))]
                continue
        if isinstance(out.get("fields"), dict) and out["fields"]:
            largest_field = max(out["fields"], key=lambda k: len(str(out["fields"][k])))
            value = out["fields"][largest_field]
            if isinstance(value, list) and len(value) > 1:
                out["fields"][largest_field] = value[:-1]
                continue
            if isinstance(value, str) and len(value) > 64:
                out["fields"][largest_field] = value[:len(value)//2]
                continue
        if isinstance(results, list) and len(results) > 1:
            results.pop()
            continue
        break
    out["approx_output_tokens"] = approx_tokens(json.dumps(out, ensure_ascii=False))
    return out


class WebToolbox:
    """Drop-in async API and background task scheduler for any Python application."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.cache = SQLiteCache(self.settings.cache_path)
        # trust_env=False avoids an implicit machine-wide proxy for arbitrary user URLs.
        self.client = httpx.AsyncClient(timeout=self.settings.request_timeout, trust_env=False, follow_redirects=False,
                                        headers={"User-Agent": "PortableWebToolbox/0.1 (+local-research)"})
        self._semaphore = asyncio.Semaphore(self.settings.concurrent_fetches)
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

    def _submit(self, operation: str, *args: object, on_result: Callable[[dict[str, Any]], Awaitable[None]] | None = None, **kwargs: Any) -> JobHandle:
        """Schedule work on the caller's running event loop, deduplicating identical jobs."""
        if self._closed:
            raise RuntimeError("WebToolbox has been closed")
        # asyncio.create_task explicitly requires a running loop; no hidden threads.
        asyncio.get_running_loop()
        # Distinct callbacks require distinct jobs; they may still share fetched HTML.
        request_key = _key("inflight", operation, args, kwargs, id(on_result) if on_result else None)
        existing = self._inflight_jobs.get(request_key)
        if existing is not None and not existing.done:
            return existing
        if len(self._active_jobs) >= self.settings.max_pending_jobs:
            raise RuntimeError("Too many pending WebToolbox jobs")
        handle = JobHandle(id=str(uuid.uuid4()), operation=operation)

        async def execute() -> dict[str, Any]:
            try:
                async with self._background_semaphore:
                    handle._state = "running"
                    # Each operation remains callable directly with `await` as well.
                    result = await getattr(self, operation)(*args, **kwargs)
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
        """Follow at most three redirects, validating each new destination."""
        async with self._semaphore:
            for _ in range(4):
                target = await self._validate(url)
                await self._throttle(target)
                async with self.client.stream("GET", target, headers={"Accept": "text/html,application/xhtml+xml"}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise RuntimeError("Redirect without a Location header")
                        url = urljoin(target, location)
                        continue
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type", "").lower():
                        raise RuntimeError("Only HTML pages are supported in v0.1")
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
        async with self._semaphore:
            await self._throttle(url)
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

    async def _page(self, url: str, mode: str, refresh: bool) -> tuple[str, str, bool, bool]:
        if mode not in {"static", "browser", "auto"}:
            raise ValueError("mode must be static, browser or auto")
        validated = await self._validate(url)
        cache_key = _key("page", validated, mode)
        if not refresh and (record := self.cache.get(cache_key)):
            return record["html"], record["final_url"], True, False

        # Two recipes for one uncached URL share one fetch; cache is checked again under the lock.
        lock = self._page_locks.get(cache_key)
        if lock is None:
            lock = asyncio.Lock()
            self._page_locks[cache_key] = lock
        async with lock:
            if not refresh and (record := self.cache.get(cache_key)):
                return record["html"], record["final_url"], True, False
            old = self.cache.get(cache_key, allow_stale=True)
            try:
                if mode == "browser":
                    html, final = await self._browser_fetch(validated)
                else:
                    html, final = await self._static_fetch(validated)
                    if mode == "auto":
                        # Only escalate thin JavaScript shell pages to a browser.
                        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
                        if len(text) < 180:
                            html, final = await self._browser_fetch(validated)
                self.cache.set(cache_key, {"html": html, "final_url": final}, self.settings.crawl_ttl)
                return html, final, False, False
            except (httpx.HTTPError, RuntimeError) as exc:
                if old:
                    return old["html"], old["final_url"], True, True
                raise RuntimeError(f"Could not retrieve {validated}: {exc}") from exc

    async def search(self, query: str, *, limit: int = 5, refresh: bool = False, max_tokens: int | None = None) -> dict[str, Any]:
        """Only short search-result metadata; does not fetch every search hit."""
        if not query.strip() or len(query) > 300:
            raise ValueError("query must be between 1 and 300 characters")
        limit = max(1, min(limit, self.settings.max_search_results))
        provider = self.settings.search_provider.lower()
        key = _key("search", provider, self.settings.searxng_url if provider == "searxng" else "", query.casefold().strip())
        cached = self.cache.get(key) if not refresh else None
        if cached:
            # Reuse the same provider call for requests with different result limits.
            return _fit_response({**cached, "results": cached["results"][:limit]}, max_tokens or self.settings.max_tokens)
        old = self.cache.get(key, allow_stale=True)
        try:
            if provider == "ddgs":
                raw = await ddgs_search(query, self.settings.max_search_results)
            elif provider == "searxng":
                raw = await searxng_search(query, self.settings.max_search_results, self.settings.searxng_url, self.client)
            else:
                raise ValueError("WT_SEARCH_PROVIDER must be ddgs or searxng")
        except Exception as exc:
            # Preserve stale search results if upstream is temporarily blocked/offline.
            if old is not None:
                return _fit_response({**old, "results": old["results"][:limit], "warning": str(exc)[:130]},
                                     max_tokens or self.settings.max_tokens)
            raise
        hits = []
        for item in raw:
            try:
                url = await self._validate(item["url"])
            except (UnsafeURLError, KeyError):
                continue
            if any(existing["url"] == url for existing in hits):
                continue
            hits.append({"title": item.get("title", "")[:180], "url": url,
                         "snippet": item.get("snippet", "")[:400]})
        result = {"query": query, "provider": provider, "results": hits, "cached": False, "stale": False}
        self.cache.set(key, result, self.settings.search_ttl)
        return _fit_response({**result, "results": hits[:limit]}, max_tokens or self.settings.max_tokens)

    async def crawl(self, url: str, *, recipe: str | dict[str, Any] | None = None,
                    mode: str = "static", query: str = "", refresh: bool = False,
                    max_tokens: int | None = None, include_text: bool | None = None) -> dict[str, Any]:
        """A page request returns small text and optionally typed structured fields."""
        spec = read_recipe(recipe)
        max_tokens = max_tokens or self.settings.max_tokens
        html, final_url, cached, stale = await self._page(url, mode, refresh)
        fields = extract_fields(html, spec, final_url) if spec else {}
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(" ", strip=True)[:160] if soup.title else ""
        # Recipes default to fields-only: keep full page text out of agent context.
        want_text = (not bool(spec)) if include_text is None else include_text
        result = {"url": final_url, "title": title, "fields": fields,
                  "cached": cached, "stale": stale, "mode": mode}
        if want_text:
            # Prefer article/main content and strip repeated navigation noise.
            main = soup.select_one(spec.get("content_selector", "main, article, [role=main]")) if spec else soup.select_one("main, article, [role=main]")
            candidate = main or soup.body or soup
            for node in candidate.select("script, style, nav, footer, noscript, svg, form"):
                node.decompose()
            content = candidate.get_text("\n", strip=True)
            result["text"] = compact_text(content, query=query, max_chars=min(14000, max_tokens*4))
        return _fit_response(result, max_tokens)

    async def research(self, query: str, *, pages: int = 2, recipe: str | dict[str, Any] | None = None,
                       mode: str = "static", refresh: bool = False, max_tokens: int | None = None) -> dict[str, Any]:
        """Search, read only top hits, and return citations and bounded extracts."""
        budget = max_tokens or self.settings.max_tokens
        pages = max(1, min(pages, self.settings.max_crawl_pages))
        search_response = await self.search(query, limit=max(3, pages), refresh=refresh, max_tokens=2000)
        results: list[dict[str, Any]] = []
        warnings: list[str] = []
        # Limit each page before aggregation to avoid returning full page documents.
        for hit in search_response["results"][:pages]:
            try:
                page = await self.crawl(hit["url"], recipe=recipe, mode=mode, query=query,
                                       refresh=refresh, max_tokens=max(180, budget // pages), include_text=True)
                results.append({"url": page["url"], "title": page["title"],
                                "snippet": page.get("text", ""), "fields": page["fields"],
                                "cached": page["cached"], "stale": page["stale"]})
            except (ValueError, RuntimeError, httpx.HTTPError) as exc:
                # Expose a short error, but retain other successful results.
                warnings.append(f"{hit['url']}: {str(exc)[:130]}")
        return _fit_response({"query": query, "provider": search_response["provider"],
                              "results": results, "warnings": warnings}, budget)
