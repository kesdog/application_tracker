"""Search-result normalization and provenance; this layer does not assert employer identity."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit
from typing import Any
from .security import normalized_url, UnsafeURLError

# Explicit ad/click endpoints must never occupy the usable-result budget.
TRACKING_PATHS = {"/aclick", "/pagead/aclk", "/pagead/aclick", "/aclk"}
TRACKING_HOSTS = {"googleadservices.com", "www.googleadservices.com", "ad.doubleclick.net"}


def classify_hit(item: dict[str, Any]) -> tuple[str, str | None]:
    """Return sponsorship and an exclusion reason, without inferring organic status."""
    raw = str(item.get("url") or item.get("href") or "")
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    path = parts.path.lower().rstrip("/") or "/"
    flagged = item.get("sponsored", item.get("is_ad"))
    if flagged is True or str(item.get("type", "")).lower() in {"ad", "sponsored"}:
        return "sponsored", "sponsored_result"
    if path in TRACKING_PATHS and ("bing." in host or "google." in host or host in TRACKING_HOSTS):
        return "sponsored", "advertising_redirect"
    if host in TRACKING_HOSTS:
        return "sponsored", "advertising_redirect"
    # Do not unwrap arbitrary redirects; it could misattribute source and identity.
    sponsorship = "organic" if flagged is False or str(item.get("type", "")).lower() == "organic" else "unknown"
    return sponsorship, None


def normalize_hits(raw: list[dict[str, Any]], provider: str, *, official_domain: str | None = None) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Normalize/merge hits and preserve all provider positions and original URLs."""
    merged: dict[str, dict[str, Any]] = {}
    removed = {"sponsored": 0, "invalid_url": 0, "duplicates": 0}
    domain = (official_domain or "").strip().lower().removeprefix("www.")
    for rank, item in enumerate(raw, 1):
        original = str(item.get("url") or item.get("href") or "")
        sponsorship, exclusion = classify_hit(item)
        if exclusion:
            removed["sponsored"] += 1
            continue
        try:
            canonical = normalized_url(original)
        except (UnsafeURLError, ValueError):
            removed["invalid_url"] += 1
            continue
        host = urlsplit(canonical).hostname or ""
        # A supplied domain makes a hit more *relevant*, never identity-confirmed.
        official_site_match = bool(domain and (host == domain or host.endswith("." + domain)))
        provenance = {"original_url": original, "provider": provider, "rank": rank, "sponsorship": sponsorship}
        if canonical in merged:
            merged[canonical]["provenance"].append(provenance)
            removed["duplicates"] += 1
            continue
        merged[canonical] = {
            "title": str(item.get("title", ""))[:180],
            "url": canonical,
            "canonical_url": canonical,
            "original_url": original,
            "snippet": str(item.get("snippet", item.get("body", "")))[:400],
            "provider": provider,
            "rank": rank,
            "sponsorship": sponsorship,
            "provenance": [provenance],
            "official_domain_match": official_site_match,
            "employer_identity": "unknown",
        }
    # Retain relative search order within each group; don't assert verified identity.
    hits = sorted(merged.values(), key=lambda hit: (not hit["official_domain_match"], hit["rank"])) if domain else list(merged.values())
    return hits, removed
