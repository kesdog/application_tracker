"""Purpose-aware crawl frontier ranking; no claim of verified employer identity."""
from __future__ import annotations

from urllib.parse import urlsplit
from .security import normalized_url, UnsafeURLError
from .profiles import KeywordProfile, load_profile

BAD = ("cookie", "privacy", "confidential", "politique", "terms", "mentions-legales", "legal", "rgpd", "vendor", "credits", "footer", "search", "recherche", "pagead", "marketing", "presse")
GOOD = ("recruit", "recrut", "career", "carriere", "emploi", "contact", "about", "equipe", "team", "people", "talent", "rh", "staff", "personnel", "postul")


def contact_page_priority(url: str, label: str = "", *, source_host: str = "", official_domain: str = "", keyword_profile: KeywordProfile | None = None) -> int:
    """Prefer employer-side contact/team pages over mirrors, credits, and policy."""
    p = urlsplit(url)
    host = (p.hostname or "").lower()
    path = (p.path or "").casefold()
    title = (label or "").casefold()
    profile = load_profile(keyword_profile)
    bad = profile.list("page_negative")
    good = profile.list("page_positive")
    if any(x in path for x in bad) or any(x in title for x in ("cookies", "privacy", "politique de confidentialit", "vendor credits", "job ads", "pricing", "tarifs", "advertising")):
        return -100
    if host in {"linkedin.com", "www.linkedin.com", "indeed.com", "fr.indeed.com"}:
        return -20
    points = 0
    if official_domain and (host == official_domain or host.endswith("." + official_domain)):
        points += 20
    if source_host and host == source_host:
        points += 10
    for token in good:
        if token in path or token in title:
            points += 12
    if "job" in path or "offre" in path:
        points -= 5
    if not points:
        points = -10
    return points


def prioritize_contact_links(links: list[dict], source_url: str = "", official_domain: str = "", *, keyword_profile: KeywordProfile | None = None) -> list[dict]:
    """Collapse tracking and duplicate language alternatives, retaining provenance."""
    host = (urlsplit(source_url).hostname or "").lower()
    seen: dict[str, dict] = {}
    for link in links:
        try:
            url = normalized_url(link["url"])
        except (KeyError, UnsafeURLError, ValueError):
            continue
        priority = contact_page_priority(url, str(link.get("label", "")), source_host=host, official_domain=official_domain, keyword_profile=keyword_profile)
        if priority < 1:
            continue
        # Language variants from common /fr/ and /en/ routes share a crawl slot.
        p = urlsplit(url)
        path = p.path
        for prefix in ("/fr/", "/en/", "/de/", "/es/"):
            if path.startswith(prefix):
                path = "/" + path[len(prefix):]
                break
        key = f"{p.hostname}|{path.rstrip('/')}|{p.query}"
        if key in seen:
            seen[key].setdefault("alternate_urls", []).append(url)
            continue
        seen[key] = {**link, "url": url, "priority": priority, "alternate_urls": []}
    return sorted(seen.values(), key=lambda x: (-x["priority"], x["url"]))
