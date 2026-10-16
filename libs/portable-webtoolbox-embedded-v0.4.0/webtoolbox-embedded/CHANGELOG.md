# Changelog

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
