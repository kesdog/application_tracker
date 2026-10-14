# Portable Web Toolbox — embedded async library (v0.2)

A small **importable Python package**, not a service. Mount it into any Python application and call `await web.crawl(...)`, or call `web.submit_crawl(...)` to execute asynchronously while the rest of the app continues. No dedicated HTTP server, Docker container, CLI, MCP process, or API key is needed for page extraction.

## Install in an existing application

```bash
# Place the package in the application repository (or install a wheel later).
mkdir -p libs
cp -r webtoolbox-embedded libs/webtoolbox

# Install directly into the application's Python environment.
pip install -e './libs/webtoolbox'

# Add browser rendering only when a site needs JavaScript.
pip install -e './libs/webtoolbox[browser]'
crawl4ai-setup

# Optional keyless search provider (may rate-limit).
pip install -e './libs/webtoolbox[search]'
```

Python 3.11+; `httpx` + `beautifulsoup4` are the only required runtime dependencies. Crawl4AI and DDGS are optional extras. Chromium runs **inside your application process**, not as a separate server. You can also install from the package root with `pip install -e '.[all]'`.

## 1. Call from any asynchronous Python code

```python
import asyncio
from pathlib import Path
from webtoolbox import Settings, WebToolbox

# An extraction recipe only specifies data fields; no model tokens are consumed.
RECIPE = {
    "fields": {
        "emails": {
            "selector": "a[href^='mailto:']",
            "attribute": "href",
            "pattern": r"^mailto:([^?]+)",
            "all": True,
        }
    }
}

async def main():
    # Keep the cache in this application's own data directory.
    settings = Settings(cache_path=Path("./data/web-cache.sqlite3"))
    async with WebToolbox(settings) as web:
        # Direct call: await only if this application flow requires the result now.
        result = await web.crawl("https://example.com", recipe=RECIPE)
        print(result["fields"])

        # Background call: schedules immediately and returns without waiting.
        job = web.submit_crawl("https://example.org", recipe=RECIPE)
        print(job.id, job.status)  # queued / running / completed / failed / cancelled

        # Other async application work can continue while the crawler runs.
        await asyncio.sleep(0)
        result = await job.result()
        print(result["fields"], result["cached"])

asyncio.run(main())
```

The `WebToolbox` object is intended to be **created once per running app / event loop**, then injected into services and workers; don't instantiate a browser per request. `web.close()` waits for submitted jobs before closing the client/browser. The context manager calls it automatically.

### Background jobs

- `web.submit_crawl(url, recipe=..., mode='static', on_result=async_callback) -> JobHandle`
- `web.submit_search(query, limit=...) -> JobHandle`
- `web.submit_research(query, pages=..., recipe=...) -> JobHandle`
- `web.job(job_id)` returns a handle while active, plus a bounded in-memory completion history.
- `job.status`, `job.done`, `job.error`, `job.cancel()`, `await job.result()`.
- Identical **active** jobs return the same handle so an application doesn't duplicate crawls when several agents ask at once. Jobs with distinct callbacks are separate, but their URL fetches are coalesced.
- Optional `on_result` is an async callback, awaited before the job is marked completed; use it to save extracted data to the host application's database without writing your own monitor loop.
- `Settings(background_concurrency=2, max_pending_jobs=100, completed_job_history=100)` controls concurrency, queue size and memory use.

### Handling finished work

```python
# Inside an application-owned async task, or a job-monitor coroutine:
async def save_candidates(extracted):
    # This runs when extraction finishes; application policy decides what can be saved.
    await host_app_save_candidates(extracted["fields"], extracted["url"])

# No blocking wait: the toolbox awaits the callback in the scheduled job.
job = web.submit_crawl(url, recipe=recipe, on_result=save_candidates)

# When needed, poll status or await job.result() for errors and completion.
assert job.id
```

The cache is persistent (SQLite), **but background jobs are deliberately in-process**. An application shutdown waits for work to finish by default, but a crash or restart will lose its queued jobs. If you need persistent retries across restarts, store the jobs in the host app's database and requeue them on startup. That's outside this library's scope.

## 2. Configure site extraction without modifying Python code

Pass a recipe by dictionary or local JSON file path:

```python
# The same class can extract job contacts, product specs or article metadata.
result = await web.crawl(
    "https://example.com/careers",
    recipe="recipes/contacts.json",
    mode="static",    # default: cheap HTTPX + CSS; 'browser' for JS, 'auto' for thin JS shells
    max_tokens=350,    # approximate output budget; not billable model usage
)
print(result["fields"])
```

Recipe calls automatically omit page text (`include_text=False` unless explicitly requested). To return a short article excerpt instead use `await web.crawl(url, include_text=True, query='roles', max_tokens=500)`. Search results are snippets only; `web.research(query, pages=2)` fetches selected results instead of every hit. No LLM is invoked anywhere.

### Cache and safety

- Search cache TTL is 6 hours; page cache TTL is 24 hours by default.
- Identical page fetches with different recipes reuse the same cached HTML (no extra fetch).
- Rate limiting is domain-aware. `concurrent_fetches` and `background_concurrency` are independent limits.
- Stale cache is returned with `stale=True` if the provider/fetch fails.
- HTTP fetches validate each redirect and block local/private URLs by default; browser crawls should only be used with trusted or allowlisted domains because browser subresources are outside the HTTP redirect validator.
- Websites may block crawling, require authentication or prohibit automation. The toolbox intentionally does not bypass those controls.
- `approx_output_tokens` uses character heuristics, not a model tokenizer. A strict token cap may truncate long extracted values; increase the budget if complete structured fields are necessary.

## App integration examples

- [`examples/application_tracker.py`](examples/application_tracker.py): a contact-discovery adapter; keeps the app's own address book and candidate approval workflow.
- [`examples/fastapi_lifespan.py`](examples/fastapi_lifespan.py): create **one embedded instance** in the host app's lifespan (does not create a standalone API or server).

## Tests

```bash
# From the library root:
pip install -e '.[dev]'
pytest -q
```

Offline tests exercise fake network responses and background task behavior. Live DDGS and Crawl4AI/Chromium operations must be tested in a network/browser-enabled host environment after installing their optional extras.
