**Toolbox v0.7 review and generic company-site profile — 18 October 2026**

v0.7 is better at reading and identifying the original job pages, and it is more conservative about employer evidence. Replaying the previous optimized recipe against the same ten reference identities returns **4/10 original postings, up from 2/10**. A3COM and NOOTA's ISCOD pages are the two recoveries. Stock queries still return 2/10, so the source-aware query recipe remains useful.

The new generic company-site experiment found a useful reusable two-query profile. Across eight known published reference pages on six company/ATS scopes, it retrieved **7/8 reference URLs** and returned **6/8 individual reference postings**, compared with **2/8** returned by the full-title-only query. These eight pages are a separate website-profile study, not eight additional verified original tracker applications. Its six tuning cases returned six references; its two held-out cases returned none for specific parser/search reasons described below. This is a best tested small-sample recipe, not a universal success rate.

The original ten-application comparison uses the previous saved search observations and original-page HTML, with explicit saved failure reports. Newly eligible routes required 58 additional public page observations, captured once and reused. The original reference pages were already captured, so A3COM/NOOTA's paired improvement comes from route/parser behavior rather than a more favorable search engine. The full 100-call comparison has no missing page or query snapshots. Additional alternatives use newly fetched observations and should not be confused with untouched historical evidence. This is a controlled replay, not a fresh ten-URL availability or cold-speed benchmark.

| Original target | Returned by v0.6 | Returned by v0.7 | v0.7 evidence-only match status |
|---|---|---|---|
| A3COM | No | Yes | possible_match |
| SFEIR | Yes | Yes | likely_match |
| DYMENSION | No | No | — |
| ADVANCED Schema | Yes | Yes | possible_match |
| ELDA Technology | No | No | — |
| Capgemini | No | No | — |
| NOOTA | No | Yes | possible_match |
| STORYZY | No | No | — |
| BAO | No | No | — |
| Theodo | No | No | — |

Four returned original URLs does not mean four employer identities were confirmed from public page evidence. SFEIR remains likely. ADVANCED Schema is now possible because its parsed employer is missing; it no longer gains employer confirmation merely from the search snippet. ISCOD is correctly reported as publisher rather than silently as A3COM/NOOTA's actual employer. The saved original URL independently identifies the reference instance for scoring, while publisher/employer identity remains a separate field.

The structured conflict fixes work on real captured pages. The Theodo internship scores 29/unresolved for a CDI request when `contract_type="CDI"` is passed, versus 95/likely previously; the actual CDI candidate scores 100. Capgemini's Nantes URL now supplies labeled slug-derived geography, producing a capped mismatch for a Paris request. A Lever `/apply` form is classified as an application destination rather than another vacancy. The category-flood control now tries its second query and retrieves the posting. Requested/effective page limits and failure/deferred-host metadata are exposed. These improvements are verified in [controls.json](controls.json).

Keep structured constraints in the call. If CDI appears only in the title and `contract_type` is omitted, the Theodo internship still scores 95/likely. `search_title` can be shortened for query generation without replacing the full requested title. Domain or ATS association also needs supplied evidence; a shared ATS hostname should not be marked as a confirmed employer domain.

There is a cost trade-off: stock requests rose from **15 to 41 recorded page calls** across ten applications while exact-original returns stayed at two. The optimized recipe used **12 calls versus 14 previously**, returning four instead of two. Permissive inspect routes help find alternative postings but also admit indices, portfolios, product pages and unrelated jobs. Select a source/company profile before increasing the page cap. Candidate returns, exact reference matches and likely matches are different metrics.

For a specific employer website or verified ATS path, the best training-selected sequence was:

```text
site:COMPANY_SCOPE "{company}" {short_search_title}
site:COMPANY_SCOPE {short_search_title} recrutement emploi careers
```

Use a normalized short search title, keep the full title and structured contract/location/reference for final matching, and start with three pages. Keep keyword required/excluded/preferred lists empty for this baseline. Avoid a universal Python/alternance preference: the profile must work for different technologies and contracts. Hiring words are a query fallback, not proof that a page is an individual vacancy or that any contact is a recruiter.

`COMPANY_SCOPE` can be an employer root such as `ipsosante.fr`, a dedicated careers host such as `careers.capgemini.com`, or a company-specific shared-ATS path such as `jobs.lever.co/theodo`. Bind the scope explicitly. In current v0.7, `site:{domain} ...` silently produces no job queries because `discover_job` does not pass a domain into template expansion, even with an employer context. The reusable template is therefore a **binding envelope**, with six already compiled native profiles in `compiled-company-profiles/`. The envelope itself is not a `load_profile` input. [generic-profile-usage.md](generic-profile-usage.md) explains the tested binder and required scope handling.

The website test compared five query variants, each across all eight cases:

| Variant | Reference URL in top six |
|---|---|
| full | 2/8 |
| short | 5/8 |
| short_company | 5/8 |
| short_hiring | 4/8 |
| short_quoted | 0/8 |

Full means the complete displayed reference title; short means the normalized role without decorative gender/contract/company suffixes. Short_company adds the employer name within the site constraint. Short_hiring adds `recrutement emploi careers`. Short_quoted quotes the entire shortened role. Quoting everything performed poorly here. No target URL, slug, UUID or job ID was put into a search query. References were selected from already captured public postings before collecting the forty new queries. Every query observation was either results (19) or empty (21); there were no provider-error observations to retry in this study.

Eighty-five one/two/three-query combinations were scored using six tuning cases on four scopes: INTM, SPINALCOM, Capgemini and Theodo. ipso and SFEIR were held out as different scopes. The selected two-query plan recovered six tuning references and one held-out URL; native parsing returned six tuning references and zero held-out references. A three-query plan beginning with the bare short title reached the same seven URLs and six parsed references but used more queries. Thus the extra query had no accuracy benefit on this sample.

| Website reference | Bound scope | URL retrieved | Reference returned as individual posting |
|---|---|---|---|
| ipso santé — ipso-django | `ipsosante.fr` | Yes | No |
| INTM — intm-java | `intm.com` | Yes | Yes |
| SPINALCOM — spinalcom-smart-building | `spinalcom.com` | Yes | Yes |
| Capgemini — capgemini-net | `careers.capgemini.com` | Yes | Yes |
| Capgemini — capgemini-react | `careers.capgemini.com` | Yes | Yes |
| SFEIR — sfeir-python | `jobs.lever.co/sfeir` | No | No |
| Theodo — theodo-cdi | `jobs.lever.co/theodo` | Yes | Yes |
| Theodo — theodo-stage | `jobs.lever.co/theodo` | Yes | Yes |

The ipso Django/Vue URL is retrieved at rank one, but even its sole-seed control is rejected as insufficient individual-posting evidence. The page has a detailed role description, a CDI label and recruitment instructions, but lacks the narrow schema/apply/description cues currently accepted by the gate. The parser also extracts `sur l` as its location from an ordinary localization sentence. A generic `rejoignez-nous` index is meanwhile returned as a candidate. This is a page-evidence/parser problem, not a need for more query words.

The saved SFEIR Lever UUID is absent from all five fresh query variants. Other SFEIR UUIDs are returned, but matching employer/title alone cannot prove they are the same vacancy instance. The sole-seed control can parse the saved reference from its captured page; absence in search does not establish closure or removal.

The website study supplied the known company scope as context for its own company domains. Shared ATS scopes retained page-level employer evidence instead of treating the shared host as a confirmed employer. Candidate and resolved URLs were filtered by host plus company path in the experiment adapter; all real query results happened to satisfy those scopes. Native `site:` queries alone are not a strict boundary. `Settings.allowed_hosts` can restrict network hosts, but is instance-wide and cannot distinguish two companies' paths on the same ATS. Do not mutate it per job on a shared concurrent instance; use an operation-level scope filter or separate bound context as appropriate.

For the selected website plan, larger page caps gave no further reference recovery:

| Page cap | Reference URLs retrieved | Individual references returned | Pages inspected across eight | Queries used |
|---|---|---|---|---|
| 3 | 7/8 | 6/8 | 24 | 13 |
| 6 | 7/8 | 6/8 | 41 | 13 |
| 12 | 7/8 | 6/8 | 47 | 16 |

Three pages was the best tested initial cost/coverage choice. Six can remain an app-configured fallback; twelve did not resolve either held-out miss. The new `max_job_discovery_pages` ceiling is separate from contact `max_crawl_pages` and should remain explicit. Keep PDF outcomes and cache failures distinct from no job; INTM results still include unsupported PDF publications that can consume inspection slots.

The remaining defects I would prioritize are:

1. Job queries do not receive their domain/site-scope value, preventing a direct generic domain-templated profile.
2. Native discovery undoes keyword ordering: a synthetic +50 Python search result is ranked first by search but a lower-original-provider-rank Java page is inspected instead under a one-page budget.
3. Explicit seniority is ineffective for junior/senior: the matcher removes those words in its similarity stop list before checking seniority. A Senior Python Developer page still scores 95/likely with `seniority="junior"`.
4. Individual-page versus careers-index detection and geographic extraction need work, demonstrated by ipso rather than hypothetical markup.
5. One shipped offline test leaves the search provider unmocked and can make a real search before testing its mocked page fetches.

The untouched suite produced **124 passes and one failure** in the rate-limit sibling test. That test uses inspect-only short numeric seed routes and accidentally runs a live provider; an unrelated real result changes its assertion. An experiment-only default-empty provider guard yields **125/125 passing**. The guard does not edit shipped tests or production code. It establishes that the deterministic assertions pass under isolated providers, not that the original suite is reliably offline. See [toolbox-feedback.md](toolbox-feedback.md) for concrete fixes and reproduction names.

Validation included 100 previous-benchmark API replays, forty new website query observations, eighty-five website plan combinations, 96 website API replays (including eight known-reference seed controls), scope-prefix boundary assertions, the real contract/location controls, and synthetic domain/ranking/seniority controls. All selected page/query snapshots are complete. The prior benchmark contains public saved responses; 94 additional URL observations cover expanded main/website routes, of which 52 succeeded, 22 were access-blocked, 16 unavailable and four unsupported-PDF/upstream errors. Each was captured once and reused, with at most five active fetch tasks and one request per host. No login, form submission, email operation or anti-bot bypass was used.

Published artifacts include [comparison.csv](comparison.csv), [company-results.csv](company-results.csv), [summary.json](summary.json), [controls.json](controls.json) and the original evaluated source hash manifest. Raw page/query snapshots and the replay harness remain local; this curated report is not a standalone reproducible corpus. The evaluation itself changed no tracker records, settings or product source. For publication, the supplied v0.7 library replaces v0.5, installation/test paths are updated, and the cooldown test explicitly disables job queries. The manifest describes the original evaluated source, before that test-only isolation change. No deployment is implied by publication. My recommendation is to keep the v0.7 route/identity/contract fixes, add the bound company-site profile, and address domain binding, keyword ordering, seniority, and page evidence before presenting all new controls as fully effective.
