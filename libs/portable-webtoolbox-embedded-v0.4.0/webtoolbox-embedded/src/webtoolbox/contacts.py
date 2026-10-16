"""Evidence-first contact extraction; does not infer invented addresses or ownership."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parseaddr
from urllib.parse import unquote, urlsplit, urljoin
from typing import Any
from bs4 import BeautifulSoup, Tag, NavigableString

# Extract published addresses only. No address-pattern prediction is performed.
EMAIL_RE = re.compile(r"(?<![\w.+-])[A-Za-z0-9][\w.+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", re.IGNORECASE)
DEFAULT_RECORD_SELECTOR = ".person, .team-member, .contact-card, .employee, [itemtype*='Person'], article.team-member"
# Include French action verbs/stems; many real French hiring pages omit English "recruitment".
RECRUITMENT = ("recruit", "recrut", "postul", "candidat", "embauch", "career", "hiring", "talent", "people ops", "ressources humaines", "rh", "emploi", "jobs")
# Only local, vacancy-specific wording establishes responsibility for a job.
# A team page or a generic corporate footer does not.
VACANCY_CONTACT_CUE = re.compile(
    r"(?:contact|recruteur|recruteuse|responsable).{0,65}(?:cette\s+offre|ce\s+poste|"
    r"this\s+(?:position|role|vacancy))|(?:hiring\s+(?:manager|recruiter))\s+for\s+this\s+role",
    re.IGNORECASE,
)
EXCLUDED = {"privacy": ("privacy", "dpo", "rgpd", "gdpr"), "media": ("press", "presse", "media", "journalist"), "sales": ("sales", "commercial", "business development"), "support": ("support", "helpdesk", "technical support", "assistance technique")}


def purpose_for(*fragments: str) -> tuple[str, str | None]:
    """Return use category and exclusion, keeping all alternatives for diagnostics."""
    haystack = " ".join(fragments).casefold()
    for name, words in EXCLUDED.items():
        if any(word in haystack for word in words):
            return name, f"not_recruitment_{name}"
    if any((bool(re.search(r"(?<!\w)rh(?!\w)", haystack)) if word == "rh" else word in haystack) for word in RECRUITMENT):
        return "recruitment", None
    return "unknown", None


def _path(node: Tag | NavigableString) -> str:
    """Stable-ish DOM path for auditing extraction without sending raw HTML."""
    if isinstance(node, NavigableString):
        node = node.parent
    chunks: list[str] = []
    for _ in range(8):
        if node is None or node.name in {"[document]", "html"}:
            break
        siblings = node.find_previous_siblings(node.name)
        chunks.append(f"{node.name}:nth-of-type({len(siblings) + 1})")
        node = node.parent
    return " > ".join(reversed(chunks))


def _evidence(source: str, node: Tag | NavigableString, excerpt: str, method: str) -> dict[str, Any]:
    return {"source_url": source, "method": method, "path": _path(node), "excerpt": excerpt[:220]}


def _emails_in_scope(scope: Tag | BeautifulSoup, source_url: str, fetched_at: str) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    # Mailto addresses have direct publication evidence and link labels.
    for node in scope.select("a[href]"):
        href = node.get("href", "")
        if not href.lower().startswith("mailto:"):
            continue
        address = unquote(href[7:].split("?", 1)[0]).strip()
        label = node.get_text(" ", strip=True)
        for match in EMAIL_RE.finditer(address):
            email = match.group(0)
            purpose, excluded = purpose_for(label, email, node.parent.get_text(" ", strip=True)[:150])
            found.setdefault(email.casefold(), {"email": email, "purpose": purpose,
                "exclusion_reason": excluded, "label": label, "publication": "published",
                "personal_ownership": "unknown", "deliverability": "not_checked",
                "fetched_at": fetched_at, "evidence": []})["evidence"].append(_evidence(source_url, node, label or href, "mailto_link"))
    # Inspect text nodes separately, not a whole-page concatenation that swaps contacts.
    for node in scope.find_all(string=True):
        if node.parent and node.parent.name in {"script", "style", "noscript"}:
            continue
        raw = str(node)
        for match in EMAIL_RE.finditer(raw):
            email = match.group(0)
            neighboring = node.parent.get_text(" ", strip=True)[:220] if node.parent else raw
            purpose, excluded = purpose_for(neighboring, email)
            entry = found.setdefault(email.casefold(), {"email": email, "purpose": purpose,
                "exclusion_reason": excluded, "label": "", "publication": "published",
                "personal_ownership": "unknown", "deliverability": "not_checked",
                "fetched_at": fetched_at, "evidence": []})
            entry["evidence"].append(_evidence(source_url, node, raw.strip(), "visible_text"))
    return list(found.values())


def _same_page(url_a: str, url_b: str | None) -> bool:
    # Full paths and queries must match; a general careers page is not a job ad.
    if not url_b:
        return False
    a, b = urlsplit(url_a), urlsplit(url_b)
    return (a.hostname or "").lower() == (b.hostname or "").lower() and (a.path.rstrip("/") or "/") == (b.path.rstrip("/") or "/") and a.query == b.query


def _vacancy_match(record: Tag, source_url: str, vacancy_url: str | None,
                   vacancy_reference: str | None) -> tuple[str, list[dict[str, Any]]]:
    # A named contact needs an explicit vacancy-specific phrase in its own
    # scoped record, plus a page or job-reference match supplied by the caller.
    text = record.get_text(" ", strip=True)
    cue = VACANCY_CONTACT_CUE.search(text)
    ref_match = bool(vacancy_reference and re.search(
        rf"(?<!\w){re.escape(vacancy_reference)}(?!\w)", text, re.IGNORECASE))
    if cue and (_same_page(source_url, vacancy_url) or ref_match):
        return "published_for_vacancy", [_evidence(source_url, record, cue.group(0), "explicit_vacancy_contact")]
    return "unknown", []


def _profile_links(record: Tag, source_url: str) -> list[dict[str, Any]]:
    # Preserve explicitly scoped public profile links without visiting them.
    links: list[dict[str, Any]] = []
    for node in record.select("a[href]"):
        href = urljoin(source_url, node.get("href", ""))
        parsed = urlsplit(href)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            continue
        if (host.endswith("linkedin.com") and parsed.path.startswith("/in/")) or (
            "profile" in (node.get("class") or []) or "profil" in (node.get("class") or [])):
            links.append({"url": href, "label": node.get_text(" ", strip=True),
                          "evidence": _evidence(source_url, node, node.get_text(" ", strip=True), "profile_link")})
    return links[:5]


def extract_contacts(html: str, source_url: str, *, record_selector: str = DEFAULT_RECORD_SELECTOR,
                     name_selector: str = ".name, .person-name, h2, h3",
                     role_selector: str = ".role, .position, .job-title, .title",
                     fetched_at: str | None = None, vacancy_url: str | None = None,
                     vacancy_reference: str | None = None) -> list[dict[str, Any]]:
    """Keep each card's fields together and never zip independently collected lists."""
    soup = BeautifulSoup(html, "html.parser")
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    records = soup.select(record_selector)
    candidates: list[dict[str, Any]] = []
    owned_emails: set[str] = set()
    for record in records[:100]:
        name_tag = record.select_one(name_selector)
        role_tag = record.select_one(role_selector)
        name = name_tag.get_text(" ", strip=True) if name_tag else None
        role = role_tag.get_text(" ", strip=True) if role_tag else None
        emails = _emails_in_scope(record, source_url, fetched_at)
        owned_emails.update(e["email"].casefold() for e in emails)
        purpose, excluded = purpose_for(role or "", record.get("class", []) and " ".join(record.get("class", [])) or "")
        if purpose == "unknown" and any(e["purpose"] == "recruitment" for e in emails):
            purpose = "recruitment"
        vacancy_state, vacancy_evidence = _vacancy_match(record, source_url, vacancy_url, vacancy_reference)
        # A scoped card associates the published details but not exact vacancy responsibility.
        if name or role or emails:
            candidates.append({"name": name, "role": role, "email": emails[0]["email"] if len(emails) == 1 else None,
                "emails": emails, "purpose": purpose, "exclusion_reason": excluded,
                "association": {"confidence": "scoped_record" if (name or role) and emails else "not_established",
                                "evidence": [_evidence(source_url, name_tag or role_tag or record, (name or role or ""), "dom_scope")]},
                "vacancy_responsibility": vacancy_state, "vacancy_evidence": vacancy_evidence,
                "profile_urls": _profile_links(record, source_url), "publication": "published" if emails else "unknown",
                "personal_ownership": "unknown", "deliverability": "not_checked", "source_url": source_url,
                "fetched_at": fetched_at,
                "field_evidence": {"name": _evidence(source_url, name_tag, name, "dom_scope") if name_tag else None,
                                   "role": _evidence(source_url, role_tag, role, "dom_scope") if role_tag else None,
                                   "email": emails[0]["evidence"] if len(emails) == 1 else []},
                "extraction_quality": {"state": "scoped" if name or role else "unscoped",
                                       "reasons": ["no_published_email"] if not emails else []}})
    # Published emails outside named cards are unassigned, not attached to nearby names.
    for email in _emails_in_scope(soup, source_url, fetched_at):
        if email["email"].casefold() in owned_emails:
            continue
        candidates.append({"name": None, "role": None, "email": email["email"], "emails": [email],
            "purpose": email["purpose"], "exclusion_reason": email["exclusion_reason"],
            "association": {"confidence": "not_established", "evidence": []},
            "vacancy_responsibility": "unknown", "vacancy_evidence": [], "profile_urls": [], "publication": "published",
            "personal_ownership": "unknown", "deliverability": "not_checked", "source_url": source_url,
            "fetched_at": fetched_at,
            "field_evidence": {"name": None, "role": None, "email": email["evidence"]},
            "extraction_quality": {"state": "unscoped", "reasons": ["unassigned_mailbox"]}})
    return candidates


def extract_contact_links(html: str, source_url: str) -> list[dict[str, Any]]:
    """Keep displayed link labels with their own URL; never borrow a nearby email."""
    soup = BeautifulSoup(html, "html.parser")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in soup.select("a[href]"):
        href = link.get("href", "")
        label = link.get_text(" ", strip=True)
        if not any(word in f"{href} {label}".casefold() for word in ("career", "recrut", "apply", "emploi", "job", "contact", "candidature")):
            continue
        target = urljoin(source_url, href)
        if urlsplit(target).scheme not in {"http", "https"} or target in seen:
            continue
        seen.add(target)
        output.append({"label": label, "url": target, "evidence": _evidence(source_url, link, label, "linked_page")})
        if len(output) == 20:
            break
    return output


def extract_source_dates(html: str) -> dict[str, str | None]:
    """Keep publisher-declared dates separate from the time the page was fetched."""
    soup = BeautifulSoup(html, "html.parser")
    for selector in ('meta[property="article:modified_time"]', 'meta[itemprop="dateModified"]', 'time[datetime]'):
        tag = soup.select_one(selector)
        if tag:
            value = (tag.get("content") or tag.get("datetime") or "").strip()
            if value:
                return {"last_updated": value, "source": selector}
    return {"last_updated": None, "source": None}


def assess_employer(candidate: dict[str, Any], employer: str | None = None,
                    *, known_domains: tuple[str, ...] = (), confirmed_aliases: tuple[str, ...] = (),
                    conflicting_names: tuple[str, ...] = ()) -> dict[str, Any]:
    """Avoid treating domain matches, web agencies or email formats as identity proof."""
    host = urlsplit(candidate.get("source_url", "")).hostname or ""
    match = "unknown"
    reasons: list[str] = []
    if employer and employer.casefold() in (name.casefold() for name in conflicting_names):
        match, reasons = "conflicting", ["conflicting_entity_evidence"]
    elif employer and employer.casefold() in (name.casefold() for name in confirmed_aliases):
        match, reasons = "confirmed", ["explicitly_confirmed_alias"]
    elif known_domains and any(host == domain or host.endswith("." + domain) for domain in known_domains):
        match, reasons = "provisional", ["recognized_domain_only"]
    elif employer:
        match, reasons = "unknown", ["no_independent_identity_evidence"]
    return {**candidate, "employer_match": {"state": match, "evidence": reasons,
                "supplied_employer": employer, "unresolved_alias": employer if match == "unknown" else None,
                "conflicting_entity": employer if match == "conflicting" else None}}
