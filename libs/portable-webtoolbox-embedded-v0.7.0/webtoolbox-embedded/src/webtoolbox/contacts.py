"""Evidence-first contact extraction; does not infer invented addresses or ownership."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parseaddr
from urllib.parse import unquote, urlsplit, urljoin
from typing import Any
from bs4 import BeautifulSoup, Tag, NavigableString
from .profiles import KeywordProfile, load_profile
from .identity import EmployerContext, legal_name_matches

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
EXCLUDED = {
    "privacy": ("privacy", "dpo", "rgpd", "gdpr", "cookies", "cookie", "confidentialit", "donnees personnelles"),
    "media": ("press", "presse", "media", "journalist", "globalprteam", "relations presse", "communication presse"),
    "sales": ("sales", "commercial", "business development", "marketing", "marketer", "publicit"),
    "support": ("support", "helpdesk", "technical support", "assistance technique", "service client"),
}
# Legal/privacy pages are not evidence of recruitment purpose, even if a footer says Careers.
SOURCE_PURPOSE = {
    "privacy": ("/privacy", "/confidentialit", "/cookies", "/cookie-policy", "/rgpd", "/donnees-personnelles"),
    "media": ("/presse", "/press", "/media-centre"),
    "sales": ("/marketing", "/advertis"),
}
EXAMPLE_LOCALPART = re.compile(r"^(?:nom(?:[._-]prenom)?|prenom[._-]nom|votre[._-]nom|your[._-]name|name[._-]surname)$", re.I)
EXAMPLE_DOMAINS = {"domaine.com", "domaine.fr", "domain.com", "example.com", "example.net", "test.invalid"}
EXAMPLE_CUE = re.compile(r"\b(?:exemple|example|format\s*[:：]|e\.?g\.?|ex\s*:|placeholder|saisissez|renseignez)\b", re.I)


def classify_email(email: str, context: str, source_url: str, *, profile: KeywordProfile | None = None) -> tuple[str, str | None]:
    """Classify each published spelling without implying its owner or purpose."""
    local, _, domain = email.casefold().partition("@")
    if EXAMPLE_LOCALPART.fullmatch(local) or domain in EXAMPLE_DOMAINS or (
            EXAMPLE_CUE.search(context) and "domaine" in domain):
        return "example", "example_or_placeholder_address"
    # Page purpose uses exact path segments, not incidental footer words.
    path = urlsplit(source_url).path.casefold()
    for purpose, stems in SOURCE_PURPOSE.items():
        if any(path.startswith(stem) or stem in path for stem in stems):
            return purpose, f"not_recruitment_{purpose}_page"
    return purpose_for(context, email, profile=profile)



def purpose_for(*fragments: str, profile: KeywordProfile | None = None) -> tuple[str, str | None]:
    """Return use category and exclusion, keeping all alternatives for diagnostics."""
    haystack = " ".join(fragments).casefold()
    profile = load_profile(profile)
    for name, words in profile.groups("contact_exclusions").items():
        if any(re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", haystack) for word in words):
            return name, f"not_recruitment_{name}"
    # Vacancy confidentiality is not a GDPR request; profile phrases explicitly
    # distinguish confidential hiring from legal privacy notices.
    if any(term in haystack for term in profile.list("vacancy_confidentiality")):
        return "recruitment", None
    if any((bool(re.search(r"(?<!\w)rh(?!\w)", haystack)) if word == "rh" else word in haystack) for word in profile.list("contact_recruitment")):
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


def _emails_in_scope(scope: Tag | BeautifulSoup, source_url: str, fetched_at: str, *, profile: KeywordProfile | None = None) -> list[dict[str, Any]]:
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
            purpose, excluded = classify_email(email, " ".join((label, node.parent.get_text(" ", strip=True)[:150])), source_url, profile=profile)
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
            purpose, excluded = classify_email(email, neighboring, source_url, profile=profile)
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
                     vacancy_reference: str | None = None, keyword_profile: KeywordProfile | None = None) -> list[dict[str, Any]]:
    """Keep each card's fields together and never zip independently collected lists."""
    soup = BeautifulSoup(html, "html.parser")
    fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
    # Only explicitly labelled context from publisher markup is used for fit.
    # Company-name similarity is not an identity proof.
    region_meta = soup.select_one('meta[name="geo.region"], meta[property="place:location:address"], [data-organization-region]')
    sector_meta = soup.select_one('meta[name="industry"], meta[name="sector"], [data-organization-sector]')
    source_region = (region_meta.get("content") or region_meta.get("data-organization-region") or "") if region_meta else ""
    source_sector = (sector_meta.get("content") or sector_meta.get("data-organization-sector") or "") if sector_meta else ""
    records = soup.select(record_selector)
    candidates: list[dict[str, Any]] = []
    owned_emails: set[str] = set()
    for record in records[:100]:
        name_tag = record.select_one(name_selector)
        role_tag = record.select_one(role_selector)
        name = name_tag.get_text(" ", strip=True) if name_tag else None
        role = role_tag.get_text(" ", strip=True) if role_tag else None
        emails = _emails_in_scope(record, source_url, fetched_at, profile=keyword_profile)
        owned_emails.update(e["email"].casefold() for e in emails)
        purpose, excluded = purpose_for(role or "", record.get("class", []) and " ".join(record.get("class", [])) or "", profile=keyword_profile)
        if purpose == "unknown" and any(e["purpose"] == "recruitment" and not e["exclusion_reason"] for e in emails):
            purpose = "recruitment"
        # A page's excluded mailbox is not made safe by a nearby HR title.
        if emails and all(e.get("exclusion_reason") for e in emails):
            excluded = excluded or emails[0]["exclusion_reason"]
            purpose = emails[0]["purpose"]
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
                "fetched_at": fetched_at, "cache_stale": False,
                "source_region": source_region, "source_sector": source_sector,
                "field_evidence": {"name": _evidence(source_url, name_tag, name, "dom_scope") if name_tag else None,
                                   "role": _evidence(source_url, role_tag, role, "dom_scope") if role_tag else None,
                                   "email": emails[0]["evidence"] if len(emails) == 1 else []},
                "extraction_quality": {"state": "scoped" if name or role else "unscoped",
                                       "reasons": ["no_published_email"] if not emails else []}})
    # Published emails outside named cards are unassigned, not attached to nearby names.
    for email in _emails_in_scope(soup, source_url, fetched_at, profile=keyword_profile):
        if email["email"].casefold() in owned_emails:
            continue
        candidates.append({"name": None, "role": None, "email": email["email"], "emails": [email],
            "purpose": email["purpose"], "exclusion_reason": email["exclusion_reason"],
            "association": {"confidence": "not_established", "evidence": []},
            "vacancy_responsibility": "unknown", "vacancy_evidence": [], "profile_urls": [], "publication": "published",
            "personal_ownership": "unknown", "deliverability": "not_checked", "source_url": source_url,
            "fetched_at": fetched_at, "cache_stale": False,
            "source_region": source_region, "source_sector": source_sector,
            "field_evidence": {"name": None, "role": None, "email": email["evidence"]},
            "extraction_quality": {"state": "unscoped", "reasons": ["unassigned_mailbox"]}})
    return candidates


def extract_contact_links(html: str, source_url: str, *, keyword_profile: KeywordProfile | None = None) -> list[dict[str, Any]]:
    """Rank scoped relevant follow-on pages; preserve each link's label and evidence."""
    from .frontier import prioritize_contact_links
    soup = BeautifulSoup(html, "html.parser")
    raw = []
    for node in soup.select("a[href]"):
        href = urljoin(source_url, str(node.get("href", "")))
        label = node.get_text(" ", strip=True)
        if urlsplit(href).scheme not in {"http", "https"}:
            continue
        raw.append({"label": label, "url": href,
                    "evidence": _evidence(source_url, node, label, "linked_page")})
    return prioritize_contact_links(raw, source_url, keyword_profile=keyword_profile)[:20]


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
                    conflicting_names: tuple[str, ...] = (),
                    target_region: str | None = None, target_sector: str | None = None,
                    source_context: dict[str, str] | None = None, employer_context: EmployerContext | None = None) -> dict[str, Any]:
    """Avoid treating domain matches, web agencies or email formats as identity proof."""
    host = urlsplit(candidate.get("source_url", "")).hostname or ""
    match = "unknown"
    reasons: list[str] = []
    if employer_context is not None:
        assessment = employer_context.assess(candidate.get("source_url", ""))
        match = assessment["state"]
        reasons = [assessment["reason"]]
    elif employer and employer.casefold() in (name.casefold() for name in conflicting_names):
        match, reasons = "conflicting", ["conflicting_entity_evidence"]
    elif employer and employer.casefold() in (name.casefold() for name in confirmed_aliases):
        match, reasons = "confirmed", ["explicitly_confirmed_alias"]
    elif known_domains and any(host == domain or host.endswith("." + domain) for domain in known_domains):
        match, reasons = "provisional", ["recognized_domain_only"]
    elif employer:
        match, reasons = "unknown", ["no_independent_identity_evidence"]
    context = source_context or {}
    owner = context.get("site_identity") or {}
    unresolved_legal_name = False
    if employer_context and owner.get("evidence") == "same_host_jsonld_organization" and owner.get("legal_name"):
        if not legal_name_matches(owner["legal_name"], employer_context):
            # A holding company/brand alias is possible; do not assert a false
            # contradiction or silently certify the published entity.
            unresolved_legal_name = True
            if match == "confirmed":
                match = "provisional"
            reasons.append("unresolved_publisher_legal_name")
    record_text = " ".join(str(x) for x in (candidate.get("role"), candidate.get("name"), context.get("description")) if x)
    # Country/industry checks never confirm identity; they only flag explicit mismatches.
    observed_region = (context.get("region") or "").casefold()
    if not observed_region:
        for label in ("usa", "united states", "france", "italy", "italia", "toulouse", "paris"):
            if re.search(r"(?<!\w)" + re.escape(label) + r"(?!\w)", record_text.casefold()):
                observed_region = label
                break
    observed_sector = (context.get("sector") or "").casefold()
    sector_tags = {
        "technology": ("it", "software", "informatique", "technologie", "technology", "web", "developp", "développ", "digital", "sirh", "hris"),
        "industry": ("industrie", "industry", "industrial", "hydraulics", "hydraulique", "manufactur", "fabrication"),
        "services": ("recruitment", "recrutement", "rh", "ressources humaines", "human resources"),
    }
    def fit(wanted: str | None, observed: str, *, dimension: str) -> dict[str, Any]:
        if not wanted or not observed:
            return {"state": "unknown", "requested": wanted, "observed": observed or None, "evidence": []}
        a, b = wanted.casefold().strip(), observed.casefold().strip()
        # Geographic generalization: France supports a French city, not an
        # assignment to that city; a named non-French country is a mismatch.
        french_cities = {"toulouse", "paris", "lyon", "bordeaux", "balma", "lille", "nantes"}
        if dimension == "region" and ((a in french_cities and b == "france") or (b in french_cities and a == "france")):
            state = "country_only"
        elif dimension == "sector":
            ga = next((k for k, tokens in sector_tags.items() if any(x == a or (len(x) > 3 and x in a) for x in tokens)), None)
            gb = next((k for k, tokens in sector_tags.items() if any(x == b or (len(x) > 3 and x in b) for x in tokens)), None)
            state = "supported" if ga and gb and ga == gb else "mismatch" if ga and gb and ga != gb else "unknown"
        else:
            # Refuse to infer incompatible regions from unrecognized postal codes
            # or broad localities. A France/USA country mismatch is meaningful.
            nations = {"france": "fr", "usa": "us", "united states": "us",
                       "italia": "it", "italy": "it", "germany": "de", "allemagne": "de"}
            if a == b:
                state = "supported"
            elif (a in nations and b in nations and nations[a] != nations[b]) or (a in french_cities and b in french_cities and a != b):
                state = "mismatch"
            elif a in nations or b in nations:
                state = "unknown"
            else:
                state = "unknown"
        return {"state": state, "requested": wanted,
                "observed": observed, "evidence": ["explicit_source_context_not_vacancy_assignment"]}
    return {**candidate, "employer_match": {"state": match, "evidence": reasons,
                "supplied_employer": employer, "unresolved_alias": employer if match == "unknown" else None,
                "conflicting_entity": employer if match == "conflicting" else None,
                "domain_evidence": employer_context.assess(candidate.get("source_url", "")) if employer_context else None},
            "identity_required": bool(employer_context),
            "site_identity": owner,
            "identity_warning": "unresolved_publisher_legal_name" if unresolved_legal_name else None,
            "fit": {"region": fit(target_region, observed_region, dimension="region"),
                    "sector": fit(target_sector, observed_sector, dimension="sector"),
                    "vacancy_team_responsibility": "unknown"}}
