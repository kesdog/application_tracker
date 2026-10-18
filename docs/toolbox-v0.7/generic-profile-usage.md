**Generic company-site posting profile**

The selected profile uses two scoped queries with a short `search_title`, while retaining the full requested `title` and structured constraints for final matching. `generic-company-site-template.json` is a binding envelope, not a native keyword-profile file. Replace its scope token before loading it, or start with a compiled profile. The experiment binder remains local. The six JSON files in `compiled-company-profiles/` are already valid native v0.7 profiles.

Example profile binding:

```python
import json
from pathlib import Path

# Run from the repository root.
profile = json.loads(Path(
    "docs/toolbox-v0.7/compiled-company-profiles/careers.capgemini.com.json"
).read_text(encoding="utf-8"))
result = await web.discover_job(
    company="Capgemini",
    title="Développeuse / Développeur C# .NET",
    search_title="développeur C# .NET",
    location="Issy-les-Moulineaux",
    contract_type="CDI",
    employer_context=verified_context,  # an existing evidence-backed context
    keyword_profile=profile,
    keyword_mode="rank",
    pages=3,
    max_tokens=8000,
)
```

This example demonstrates query binding only and assumes an existing WebToolbox instance. Supply `verified_context` from reviewed domain evidence; if it is unavailable, omit that argument and preserve unverified employer identity. The experiment also used `ScopedReplay` candidate/redirect filtering. For production, enforce the selected host and optional company-path prefix before accepting candidates or following redirects, using verified company/ATS relationships. A shared `jobs.lever.co` host is not a company scope; use a path such as `jobs.lever.co/theodo`. Host-level `Settings.allowed_hosts` can restrict live requests but does not enforce company path prefixes and should not be mutated per concurrent operation.

The native job-template formatter currently does not receive `{domain}`, so a direct `site:{domain}` profile would run zero queries. Compiled examples bind a literal scope instead. The template's `keywords` are deliberately empty: standalone keyword ranking is currently undone by the discovery candidate sort, and no mandatory employer/technology/city words improved the previous tests. Do not insert Python, alternance or a city into every job profile.

Use `Settings.max_job_discovery_pages` for the job ceiling. Three pages recovered the same seven/eight reference URLs and six/eight parsed references as larger caps in this website study. Retain the app's per-job override when adopting the profile; these artifacts have not changed the tracker settings. The eight reference pages are a small positive sample across six scopes; the two held-out website cases still failed exact-reference parsing/recovery. This is a tested baseline, not a universal optimum.

When an original URL is already known, a seed-only call with `keyword_profile={"job_queries": []}` avoids accidental searches while inspecting an unfamiliar route. Keep the original URL and reference even when another publisher has a similar role. A 401/403/429 remains unobserved/blocked; a 404/410 concerns that URL only.
