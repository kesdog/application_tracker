## 0.7.0 — source-aware job discovery and evidence-bounded matching (2026-10-18)

- Recognize ISCOD/HelloWork detail routes and inspect INTM/unknown paths using single-job page evidence; reject generic search/category and ATS application routes.
- Accumulate eligible results before stopping a query ladder, track query and route rejection diagnostics, and distinguish requested vs effective crawl limits.
- Apply optional strict `keyword_mode=filter` in job discovery; support `search_title` as query-only input.
- Normalize contracts and cap confirmed title/contract/location/employer/reference contradictions rather than rewarding title overlap alone.
- Treat ISCOD as a publisher, retain partner identity uncertainty, and extract visible city, reference, schema, URL-slug and publisher evidence independently.
- Keep posting URL, application destination, source-scoped IDs, declared canonical URLs, and verified redirect relationships distinct; never infer cross-platform posting equivalence from titles alone.
- Preserve 401/403/404/410/429 outcome and host-deferred diagnostics; short-lived failure cache reduces repeat blocked fetches across keyword profiles, with forced retries clearing successful failures.
- Add 17 offline v0.7 regression cases; full suite: 125 passing. Benchmark report/JSON captures were not available as raw local files; cases are reconstructed from the provided observations.

# Changelog

## 0.5.0 — 2026-10-17

- Adds `discover_job()` / `submit_discover_job()` to find and rank individual postings and extract *published* application URLs without automatically submitting forms.
- Adds `check_job_status()` / `submit_check_job_status()` using one static GET per due check (15-minute status cache) and evidence-based `LIVE` / `CLOSED` / `UNKNOWN` outcomes. JavaScript browser mode remains opt-in.
- Recognizes canonical LinkedIn IDs and slug URLs, Indeed `jk` references and Free-Work vacancy URLs; recognizes job-specific Greenhouse/Lever/Ashby/SmartRecruiters pages and generic careers paths.
- Treats 403/429, login redirects, JavaScript shells, expiring `validThrough` metadata and unverified forms as uncertain; distinguishes 404/410 posting disappearance from employer hiring status.
- Uses full-record truncation for discovery matches, preserving complete URLs and recording omissions. Existing search, contact discovery, caching, scheduling and source formats stay supported.
- Incorporates the tracker field review: placeholder-address diagnostics, marketing/press/privacy exclusions, independent employer/region/sector assessments and expanded multilingual HR leadership titles.
- Makes fallback search contact-aware, prioritizes first-party contact/team pages, follows links within the page budget, and suppresses low-value policy, vendor and duplicate-language links.
- Normalizes provider exceptions across `search`, `search_with_fallback` and `research`; DDGS explicit “No results found” is empty, while failed/rate-limited searches remain distinct outcomes. Cancellation propagates.
- Retains per-source freshness and evidence observations across deduplication; stale contact records require revalidation. Output budgets mark incomplete responses `partial` with original counts.
- **90 offline tests passed** (73 job-discovery/baseline tests + 17 tracker-review regressions). Live DDGS/browser/site integration remains unverified in this environment.

## 0.4.0 — 2026-10-14

- Adds ranked categories: explicit vacancy contact, named recruiter, recruitment mailbox, general mailbox, named non-recruiter and excluded contact. The score is a heuristic, not probabilistic confidence.
- Vacancy responsibility requires both a caller-supplied matching vacancy URL/reference and explicit wording inside a scoped person card. The claim is labeled `published_for_vacancy`, not independently verified; unknown remains unknown by default.
- Maintains public profile links attached to the original person card without accessing LinkedIn accounts.
- Deduplicates compatible published mailboxes across fetched pages, retaining source URLs and evidence. Conflicting purpose claims remain explicit and suppress recommendations.
- Makes reusable `rank_contact()`, `merge_and_rank()` and `shortlist_summary()` importable from the package. Adds category diagnostics to structured crawl and research responses.
- Existing entry points, return fields and self-hosted in-process queue remain compatible. No background service, new external dependency or token-consuming LLM added.
- 42 offline tests passed, including new job-posting/team-card fixtures. Live search and Chromium have not been validated in this execution environment.

## 0.3.1 — 2026-10-14

- Recognize French recruitment terms (`recrutement`, `postuler`, `candidater`) when classifying published professional contact addresses.
- Regression-test short, source-grounded examples for Livract, A3COM, and WeadminIT, while excluding press/support mailboxes.
- Manual offline replay: published emails from I DOM YOU, Livract, A3COM, CELAD and WeadminIT extracted; four correctly recommended as recruitment-purpose; general IDOMYOU support remains unclassified.
- 34 offline tests pass. Live browser/provider testing is **not** verified; this environment cannot resolve external hostnames.

## 0.3.0 — 2026-10-14

Built on embedded v0.2.0 without introducing any service, server, or always-on worker.

- **P0:** Search results retain source rank and URL provenance, canonicalize tracking variants, exclude known ad redirects, preserve unknown sponsorship, and track raw and usable counts. A bounded provider/query ladder reports outcomes and stale-cache details separately.
- **P0:** Compact outputs omit full candidate records and fields instead of splitting emails, URLs or personal records. Omission counts and reasons are explicit, and text excerpts are reduced independently.
- **P1:** Adds published plain-text emails, mailto evidence, per-card name/role/email grouping, named records with no published inbox, contact-purpose exclusion diagnostics, uncertain identity/ownership states, and links with associated labels.
- **P2:** Adds JS-shell hints without automatic Chromium, 403/405 blocked responses, request/progress hooks, deadlines, host-aware concurrency and a partial-result handle for cancelled in-process jobs.
- **Tests:** Existing 18 regressions preserved, with 14 additional offline tests and representative synthetic HTML fixtures. No live provider/browser smoke test performed in this environment.

**Migration note:** `mode="auto"` now detects rendering needs instead of invoking Chromium. Opt into actual Chromium with `mode="browser"`. The legacy `search()`, `crawl()`, `research()` and `submit_*` entry points remain available. Structured contact output is opt-in through `contacts=True` / `structured=True`.

## 0.6.0 — evidence-bound domains and editable keyword profiles (2026-10-17)

- Optional `EmployerContext` with explicitly evidenced employer domain, aliases, vetted ATS hosts and domain exclusions; no substring identity promotion. `official_domain` by itself is now a **provisional hint** and no longer creates an outreach-eligible recipient.
- Employer-aware crawl frontier: non-allowed search hits are omitted *before* page budgeting; relevant team/recruitment links beat advertising, pricing, privacy and job-mirror pages; an employer homepage is a seed when searches yield empty results.
- Public JSON-LD organization name/sector/country retained as source assertions; unresolved legal names result in identity review rather than automatic confirmation. Web agency footer credits are not treated as employer identity.
- Fix French vacancy-confidentiality false positives: `confidentialité` in an invitation to apply is not a privacy-policy request. Privacy pages and placeholders remain excluded.
- Reusable `load_profile()` reads JSON or dict overrides for contact-purpose terms, recruiter titles, search templates, page frontiers, and job CLOSED/APPLY/BLOCKED terms. `Settings.keyword_profile` selects a per-app profile; search/crawl/research/job methods permit call-level overrides. Generic search results may be ranked or strictly filtered by required/preferred/excluded terms and synonyms.
- Search-rank before top-N; retain raw search results in cache so edits to profiles do not trigger new upstream requests. Cache posting statuses separately for different status keyword profiles.
- Incomplete crawl frontiers now report `completion=partial`, `stop_reason=page_limit`, `unvisited_pages`, and `page_budget_exhausted`; no source disappearance implies no contact exists.
- 107 offline tests passing (including 17 new v0.6 regressions); live provider/Chromium tests still required in the host environment.
