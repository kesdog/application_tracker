# Portable Web Toolbox — embedded async library (v0.4.0)

**An importable Python class, not a service.** Bundle it inside another Python app and `await` it or schedule work using the host application's event loop. It does not run a standalone process, HTTP server, MCP server or Docker container. Its built-in SQLite cache stores *web responses only*. App-specific candidate approval and durable job queues belong to the host application.

## 1. Install inside an existing project

```bash
# Copy the package folder alongside your app's backend source.
mkdir -p libs
cp -r webtoolbox-embedded libs/webtoolbox

# Install lightweight HTTP and CSS extraction only.
python -m pip install -e './libs/webtoolbox'

# Add keyless DDGS search, if needed (upstream can still rate-limit).
python -m pip install -e './libs/webtoolbox[search]'

# Add Crawl4AI browser rendering *only* for domains approved for browser use.
python -m pip install -e './libs/webtoolbox[browser]'
crawl4ai-setup
```

Python 3.11+. Core dependencies: `httpx` and `beautifulsoup4`. `ddgs` and Crawl4AI remain optional via lazy imports. Install once into each application's own virtual environment; never copy code into `.venv/Lib/`.

### Minimal usage

```python
from pathlib import Path
from webtoolbox import Settings, WebToolbox

async def main():
    # Create once per application lifespan and reuse across application tasks.
    async with WebToolbox(Settings(cache_path=Path("data/web-cache.sqlite3"))) as web:
        # Cheap HTML extraction with no browser or model usage.
        page = await web.crawl("https://example.com/careers", contacts=True, structured=True)
        print(page.get("candidates", []))

        # Search with bounded fallback, provider diagnostics and source attribution.
        result = await web.search_with_fallback("Example Inc", official_domain="example.com")
        print(result["completion"], result["attempts"])

        # Schedule work without blocking the host request or opening a new service.
        task = web.submit_research_contacts("Example Inc", official_domain="example.com",
                                            deadline_seconds=50)
        print(task.id, task.status)
        contacts = await task.result()
        print(contacts["candidates"])
```

**Older API remains available:** `await web.search(...)`, `await web.crawl(..., recipe=...)`, `await web.research(...)`, `submit_search`, `submit_crawl`, `submit_research`, `web.job`, and `web.close`. Existing `fields`, `results`, `cached`, `stale`, `url`, etc. remain; diagnostic keys are additive. Opt into structured page results with `structured=True` and contact evidence with `contacts=True`.

### Search-result contract

- `search()` preserves **original URL, canonical URL, provider, source rank and sponsorship (`organic`, `sponsored`, `unknown`)**, and provenance for merged results. Known click-tracking and explicitly sponsored links are removed *before* applying the usable result limit. Ordinary DDGS hits with no sponsorship metadata remain `unknown`.
- `raw_count`, `usable_count` and `filtered` distinguish a genuinely empty response from a provider result that contained only advertisements. Unknown identity is not verified by a company-looking URL.
- `search_with_fallback(company, role="", official_domain=None, providers=("ddgs",), max_attempts=6, deadline_seconds=45)` tries (1) specific recruitment, (2) broader company identity, and (3) a targeted `site:` query **only with a supplied domain**. Providers are explicitly configured, maximum two, across up to six total attempts. Cooldowns avoid repeating rate-limited providers.
- Per-attempt `outcome`: `results`, `empty`, `rate_limited`, `upstream_error`, `timeout` or `cancelled` (cancelled work propagates cancellation to the caller). Run-level `completion`: `complete`, `partial`, `unresolved`; submitted jobs also expose the existing `JobHandle` cancellation state.
- The cache can return stale data and a *separate failed provider outcome*. A rate limit is not evidence that no recruiter exists.

### Contact and extraction evidence

```python
# No scraping code needs to be rewritten for another application's sites.
page = await web.crawl(
    "https://example.com/team", contacts=True, structured=True,
    employer="Example Inc", known_domains=("example.com",),
    mode="auto", max_tokens=4000,
)

# Candidates are evidence-backed, never approved or automatically contacted.
for person in page.get("candidates", []):
    print(person["name"], person["role"], person["email"], person["purpose"])
```

The generic `contacts=True` extractor finds published `mailto:` links **and** visible-text addresses. It preserves all addresses and per-address evidence (`source_url`, extraction method, DOM path, bounded excerpt, label). Person details are associated only inside the same configurable card/section scope; parallel lists are **not** zipped together. A card with two emails retains both options but sets its primary `email` to `null`. Cards without published emails keep `email: null`; the library does not generate email patterns.

Contact assessments include distinct `publication`, `personal_ownership`, `deliverability`, `vacancy_responsibility`, `employer_match`, `association` and `extraction_quality` fields. `personal_ownership`, deliverability and vacancy responsibility remain unknown/not checked without direct evidence. A known domain alone yields **provisional** employer identity. A credited website agency is not automatically an employer. Recruitment-purpose heuristics filter press, privacy, sales and support mailboxes out of the *recommendation view*, while leaving them visible with exclusion reasons in `candidates`. No model, mailbox verification, message sending or site anti-bot bypass is built in.

For unfamiliar HTML structures pass `record_selector=".my-person-card"` or a standard JSON recipe to `crawl`. Generic recipe extraction (`extract_fields`) remains available independently of recruitment-specific rules.


### Contact ranking and vacancy-specific evidence (v0.4)

`contacts=True` now adds a **heuristic `contact_priority`** to each candidate and
sorts candidates by relevance. Scores are ordering weights, **not probabilities**.
The categories, from most useful to least, are:

| Category | Meaning | Contact action |
|---|---|---|
| `vacancy_specific_contact` | A contact card explicitly says this contact handles the supplied vacancy | Check the published contact method and review |
| `named_recruiter` | Named person with a recruitment-related job title | Use their published email if unambiguous, otherwise research their profile |
| `recruitment_mailbox` | Published email explicitly used for hiring | Review as a recruitment recipient |
| `general_company_mailbox` | Published company email without recruitment evidence | Fallback only; verify its purpose |
| `named_other_contact` | Named person not established as a recruiter | Don't assume hiring responsibility |
| `excluded` | Incompatible email purpose or conflicting company identity | Do not recommend |

Vacancy-specific classification is deliberately strict: pass `vacancy_url` (or a
`vacancy_reference` actually present in the **same contact card**) and the card
must contain an explicit *contact for this vacancy* cue. The claim is recorded as
`vacancy_responsibility="published_for_vacancy"` rather than independently confirmed. Merely sharing a page
or being an HR employee does **not** establish responsibility.

```python
from pathlib import Path
from webtoolbox import Settings, WebToolbox

async def lookup_followup_contacts(job_url: str):
    # Embedded in your app; no separate daemon or HTTP server.
    async with WebToolbox(Settings(cache_path=Path('data/web-cache.sqlite3'))) as web:
        result = await web.crawl(
            job_url, mode='auto', contacts=True, structured=True,
            vacancy_url=job_url, employer='Example', known_domains=('example.org',),
            max_tokens=6000,
        )
        # Rank values express evidence relevance, not certainty of deliverability.
        for candidate in result.get('candidates', []):
            print(candidate['name'], candidate['email'], candidate['contact_priority'])
        return result
```

The higher-level `research_contacts(..., vacancy_url=..., vacancy_reference=...)`
accepts the same optional vacancy context, ranks across pages, and deduplicates
repeated *compatible* mailbox observations. It preserves `source_urls` for each
merged candidate. If the same mailbox is described as recruitment and support,
the merged result is marked `conflicting_purpose_evidence` and not recommended.
A named person and an unassigned mailbox are **never merged** just because the
addresses match. Public profile links found inside a person's card are retained
without fetching or logging in to the profile site.

Results include `contact_categories`, and each candidate's `contact_priority`
contains `category`, `score`, `score_type`, `reasons`, `outreach_eligible` and
`recommended_action`. A person with no published mailbox remains a lead with
`recommended_action='find_contact_method'`; the worker does not fabricate an
address or send an email. `outreach_eligible` does **not** indicate that an
address is deliverable or that the person handles the vacancy. A missing
employer identity confirmation yields `verify_employer_identity`.

Rank existing source-backed contacts without searching:

```python
from webtoolbox import merge_and_rank

# Reuse the exact same heuristics on candidates already in your app's database.
ordered = merge_and_rank(saved_candidates)
```

### Token budget and truncation

`max_tokens` is an **approximate character-based budget**, not an exact tokenizer. Excerpts are bounded independently of fields. It never silently truncates addresses, URLs or individual candidate records; if the response is too large, entire records or fields are omitted. `truncation` reports `omitted_records`, `omitted_fields`, `omitted_text_chars` and `reasons`. A structured record that cannot fit is reported as omitted, not returned with partial values. Reduced raw page text is additionally marked with `text_reduction`.

### Browser and access conditions

- `mode="static"` (default) uses HTTPX only. `mode="auto"` also uses HTTPX **only**, but marks suspected JavaScript shells with `outcome="rendering_needed"` and `rendering_signals`; it **never launches Chromium automatically**.
- Only explicit `mode="browser"` imports Crawl4AI and starts Chromium. No bypass of forbidden pages or CAPTCHA is attempted.
- `403` and `405` are surfaced as `blocked` in `structured=True`, and the same resource is not fetched again within that toolbox run. If stale HTML exists, it remains available with `stale=True` and `upstream_outcome="blocked"`. An ordinary empty static page is not automatically called a JS shell.
- HTTP fetches validate redirects and reject private/local destinations by default. Browser subresources aren't subject to HTTPX's redirect validator; restrict `allowed_hosts` and only enable browser for trusted domains.

### Lifecycle, hooks, concurrency and deadlines

```python
from webtoolbox import Settings, WebToolbox

# Keep one toolbox instance for the lifespan of the embedding app.
web = WebToolbox(Settings(background_concurrency=5, concurrent_fetches=5,
                          per_host_concurrency=1, domain_delay_seconds=0.75),
                 on_request=lambda request: print("fetch", request["url"]))

# Progress callback may be sync or async. Submission requires a running event loop.
job = web.submit_research("engineer recruiting", pages=2,
                          on_progress=lambda info: print(info), deadline_seconds=45)

# Read the last completed partial evidence if the job is cancelled.
job.cancel()
partial = job.partial

# Close from the host application's async shutdown/lifespan hook:
await web.close(cancel_pending=True)
```

The host-level `background_concurrency` governs the in-process queue, `per_host_concurrency` applies to fetches within the same toolbox instance, and requests to one slow host do not occupy the global network semaphore while waiting. Callbacks can report requests and progress. Work is cooperatively cancellable, and research jobs publish partial results after completed pages. **Job IDs, pending work and in-process history are not durable across app crashes/restarts.** The embedding application owns persistence, retry policies, and recovery. `web.close()` otherwise waits for pending jobs to finish.

### App integration examples

- [`examples/application_tracker.py`](examples/application_tracker.py): adaptation for candidate review and a tracker-owned durable queue.
- [`examples/fastapi_lifespan.py`](examples/fastapi_lifespan.py): single toolbox instance injected into an existing FastAPI lifespan.
- [`recipes/`](recipes): reusable CSS-based extraction recipes for general applications.

### Tests and limitations

```bash
# Run offline tests (including fixtures for plain-text mailboxes, scoped people cards,
# advertising links, JS shells, blocked responses and overlapping host fetches).
python -m pip install -e '.[dev]'
python -m pytest -q
```

The tests use fake providers and local fixtures, **not live employer contact pages**. They do not establish real-world accuracy, rate-limit behavior of DDGS, or successful Crawl4AI browser installation. Live DDGS/Chromium smoke testing is a separate manual verification task in a suitable environment. This version retains optional dependencies so apps that only use HTTPX do not pay the installation and startup cost of a browser.
