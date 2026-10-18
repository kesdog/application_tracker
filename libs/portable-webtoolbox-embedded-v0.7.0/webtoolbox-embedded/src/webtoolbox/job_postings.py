"""Conservative, platform-aware parsing for job listings and application links.

No endpoint on LinkedIn, Indeed, or Free-Work is treated as an official
availability API. Everything inferred from public HTML remains evidence-based.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup
from .security import UnsafeURLError, normalized_url
from .identity import EmployerContext, legal_name_matches


ATS_HOSTS = (
    "greenhouse.io", "lever.co", "ashbyhq.com", "smartrecruiters.com",
    "workdayjobs.com", "recruitee.com", "teamtailor.com", "workable.com",
)
BLOCK_MARKERS = (
    "verify you are human", "checking your browser", "captcha", "enable cookies to continue",
    "unusual traffic", "access denied", "just a moment...", "security verification",
    "verifiez que vous etes humain", "vérifiez que vous êtes humain",
)
# These refer to the *specific job*, not generic site navigation or boilerplate.
CLOSED_MARKERS = (
    "no longer accepting applications", "this job is no longer available",
    "this job has expired", "the job has expired", "this job is closed",
    "this position has been filled", "this position is no longer available",
    "this vacancy is no longer available", "job posting has expired",
    "l'offre recherchee est expiree", "cette offre est expiree",
    "cette offre n'est plus disponible", "cette offre n est plus disponible",
    "offre d'emploi expiree", "ce poste n'est plus disponible",
    "cette annonce n'est plus disponible", "cette offre a ete pourvue",
    "offre cloturee", "offre pourvue", "l'offre n'est plus disponible",
    "ce poste a ete pourvu", "les candidatures sont closes",
)
APPLY_WORDS = (
    "apply", "apply now", "apply for this job", "submit application",
    "postuler", "je postule", "candidater", "envoyer ma candidature",
    "deposer ma candidature", "déposer ma candidature", "rejoindre l'equipe",
)
BAD_DESTINATIONS = (
    "/login", "/signin", "/sign-in", "/register", "/signup", "/sign-up",
    "/auth/", "/privacy", "/terms", "/contact", "/search", "/jobs/search",
)


def _fold(value: str) -> str:
    # Accent-insensitive comparison avoids brittle French punctuation variants.
    raw = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(c for c in raw if not unicodedata.combining(c))
    # Normalize common typographic apostrophes used by French job boards.
    ascii_text = ascii_text.translate(str.maketrans({"’": "'", "‘": "'", "`": "'"}))
    return re.sub(r"\s+", " ", ascii_text.casefold()).strip()


def _is_host(host: str, domain: str) -> bool:
    # Require a DNS label boundary, not a substring such as notlever.co.
    return host == domain or host.endswith("." + domain)


def platform_of(url: str) -> str:
    """Classify the actual host using DNS suffixes, never loose substrings."""
    host = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
    if _is_host(host, "linkedin.com"):
        return "linkedin"
    if _is_host(host, "indeed.com") or _is_host(host, "indeedjobs.com"):
        return "indeed"
    if _is_host(host, "free-work.com"):
        return "freework"
    if _is_host(host, "greenhouse.io") or _is_host(host, "greenhouse.com"):
        return "greenhouse"
    if _is_host(host, "lever.co"):
        return "lever"
    if _is_host(host, "ashbyhq.com"):
        return "ashby"
    if _is_host(host, "smartrecruiters.com"):
        return "smartrecruiters"
    return "other"


def job_route(url: str) -> dict[str, str]:
    """Classify URLs before using an expensive page slot.

    'inspect' routes require single-vacancy HTML evidence. A route alone
    never proves that a position exists or belongs to a specific employer.
    """
    p = urlsplit(url)
    path = p.path.casefold().strip("/")
    host = (p.hostname or "").casefold().removeprefix("www.")
    platform = platform_of(url)
    segments = path.split("/") if path else []
    suffix = segments[-1] if segments else ""
    if re.search(r"(?:^|/)(?:apply|application|candidature-form)(?:/|$)", "/" + path) and platform in {
            "lever", "ashby", "greenhouse", "smartrecruiters"}:
        return {"kind": "application", "reason": "ats_application_form"}
    if re.search(r"(?:^|/)(?:search|results|category|categories|all-jobs|pricing|plans|login|index)(?:/|$)", "/" + path):
        return {"kind": "non_job", "reason": "search_or_category_route"}
    if not path or suffix in {"offres-emploi-en-alternance", "emplois", "jobs", "careers", "project", "offres", "recrutement"}:
        return {"kind": "non_job", "reason": "listing_or_home_route"}
    if platform == "linkedin":
        if re.search(r"(?:^|/)jobs/view/(?:[\w%-]+-)?\d{7,}(?:/|$)", path):
            return {"kind": "specific", "reason": "linkedin_job_id"}
        return {"kind": "non_job", "reason": "linkedin_non_posting"}
    if platform == "indeed":
        if parse_qs(p.query).get("jk") or re.search(r"(?:^|/)(?:viewjob|rc/clk)(?:/|$)", path):
            return {"kind": "specific", "reason": "indeed_job_key"}
        return {"kind": "non_job", "reason": "indeed_non_posting"}
    if platform == "freework":
        if "/job-mission/" in "/" + path + "/" and len(segments) >= 4:
            return {"kind": "specific", "reason": "freework_job_detail"}
        return {"kind": "non_job", "reason": "freework_category_or_search"}
    if host == "iscod.fr" or host.endswith(".iscod.fr"):
        if re.fullmatch(r"offres-emploi-en-alternance/[\w%-]{8,}", path):
            return {"kind": "specific", "reason": "iscod_individual_offer"}
        return {"kind": "non_job", "reason": "iscod_non_offer"}
    if host == "intm.com" or host.endswith(".intm.com"):
        if re.fullmatch(r"project/[\w%-]{6,}", path):
            return {"kind": "inspect", "reason": "intm_project_requires_page_evidence"}
    if host == "hellowork.com" or host.endswith(".hellowork.com"):
        if re.fullmatch(r"fr-fr/emplois/\d+\.html", path):
            return {"kind": "specific", "reason": "hellowork_job_id"}
        return {"kind": "non_job", "reason": "hellowork_category_or_search"}
    if platform in {"lever", "ashby", "greenhouse", "smartrecruiters"}:
        if len(segments) >= 2 or re.search(r"jobs?/\d+", path):
            return {"kind": "specific", "reason": "ats_posting_route"}
    if re.search(r"(?:^|/)(?:job|jobs|posting|position|vacancy|offre|careers)/[\w-]{5,}(?:/|$)", path):
        return {"kind": "specific", "reason": "generic_job_detail_route"}
    # An unfamiliar single-page route can be inspected rather than summarily rejected.
    # Reject obvious policy/marketing URLs and article directories.
    if re.search(r"(?:^|/)(?:privacy|confidentialite|cookies|legal|blog|actualites|news|about|contact)(?:/|$)", path):
        return {"kind": "non_job", "reason": "non_vacancy_content"}
    return {"kind": "inspect", "reason": "unknown_route_requires_page_evidence"}


def is_specific_job_url(url: str) -> bool:
    """True only for recognized *individual* posting routes."""
    return job_route(url)["kind"] == "specific"


def is_individual_job_page(page: dict[str, Any], url: str) -> bool:
    """Inspect ambiguous routes; schema or a clear single-role apply section is needed."""
    if page.get("schema_found"):
        return True
    title = _fold(page.get("title", ""))
    generic = {"jobs", "job offers", "careers", "recrutement", "emplois", "offres d'emploi", "nos offres", "projets"}
    return bool(page.get("has_job_heading") and title not in generic
                and ((page.get("visible_apply_controls") or page.get("application_links"))
                     or (page.get("body_length", 0) > 180 and page.get("vacancy_description_signals")))
                and page.get("body_length", 0) >= 35)


def canonical_job_url(url: str) -> str:
    """Normalize tracking-rich links but retain identifiers needed to open the job."""
    canonical = normalized_url(url)
    parts = urlsplit(canonical)
    if platform_of(canonical) == "linkedin":
        match = re.search(r"/jobs/view/(?:[\w%-]+-)?(\d{7,})(?:/|$)", parts.path)
        if match:
            return f"https://www.linkedin.com/jobs/view/{match.group(1)}/"
    if platform_of(canonical) == "indeed":
        jk = parse_qs(parts.query).get("jk", [])
        if jk and re.fullmatch(r"[A-Za-z0-9]{8,32}", jk[0]):
            return f"https://{parts.hostname}/viewjob?jk={jk[0]}"
    return canonical


def posting_identity(url: str) -> dict[str, str]:
    """Expose source-scoped IDs without claiming cross-platform equivalence."""
    canonical = canonical_job_url(url)
    p = urlsplit(canonical)
    platform = platform_of(canonical)
    path = p.path.strip("/")
    identifier = ""
    kind = "url"
    if platform == "linkedin":
        m = re.search(r"jobs/view/(\d{7,})", path)
        identifier = m.group(1) if m else ""
        kind = "linkedin_id"
    elif platform == "indeed":
        identifier = (parse_qs(p.query).get("jk") or [""])[0]
        kind = "indeed_jk"
    elif platform == "lever":
        m = re.search(r"/([0-9a-f]{8}-[0-9a-f-]{27,})$", "/" + path, re.I)
        identifier = m.group(1).lower() if m else ""
        kind = "lever_uuid"
    elif platform == "greenhouse":
        m = re.search(r"/jobs/(\d+)$", "/" + path)
        identifier = m.group(1) if m else ""
        kind = "greenhouse_id"
    elif re.fullmatch(r"fr-fr/emplois/\d+\.html", path) and "hellowork.com" in (p.hostname or ""):
        identifier = path.rsplit("/", 1)[-1].removesuffix(".html")
        kind = "hellowork_id"
    elif (p.hostname or "").endswith("iscod.fr") and path.startswith("offres-emploi-en-alternance/"):
        identifier = path.rsplit("/", 1)[-1]
        kind = "iscod_slug"
    return {"source_platform": platform, "source_id": identifier,
            "id_type": kind, "canonical_url": canonical}


def _objects(data: Any) -> list[dict[str, Any]]:
    """Flatten only schema.org graphs/arrays, not arbitrary nested dictionaries."""
    if isinstance(data, list):
        return [child for obj in data for child in _objects(obj)]
    if isinstance(data, dict):
        return [data, *(_objects(data.get("@graph", [])) if "@graph" in data else [])]
    return []


def job_schema(soup: BeautifulSoup, url: str) -> dict[str, Any] | None:
    """Read at most one matching JobPosting; multiple cards do not imply a single vacancy."""
    schemas = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (TypeError, ValueError):
            continue
        for item in _objects(data):
            types = item.get("@type", "")
            if (isinstance(types, str) and "JobPosting" in types or
                    isinstance(types, list) and "JobPosting" in types):
                schemas.append(item)
    if len(schemas) == 1:
        return schemas[0]
    if len(schemas) > 1:
        # A list of jobs is not a confirmed posting; match an explicit source URL.
        target = canonical_job_url(url)
        matching = [x for x in schemas if x.get("url") and canonical_job_url(str(x["url"])) == target]
        return matching[0] if len(matching) == 1 else None
    return None


def _plain_value(v: Any) -> str:
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return str(v.get("name") or v.get("value") or "").strip()
    if isinstance(v, list):
        return ", ".join(x for x in (_plain_value(a) for a in v) if x)
    return ""


def _schema_location(data: dict[str, Any] | None) -> str:
    if not data:
        return ""
    location = data.get("jobLocation", {})
    if isinstance(location, list):
        location = location[0] if location else {}
    if isinstance(location, dict):
        address = location.get("address", {})
        if isinstance(address, dict):
            return ", ".join(str(address.get(x, "")) for x in ("addressLocality", "addressRegion") if address.get(x))
        return _plain_value(address)
    return _plain_value(location)


def _url_candidate(raw: str, base: str) -> str | None:
    raw = (raw or "").strip()
    if not raw or raw[0] == "#" or raw.casefold().startswith(("javascript:", "mailto:", "tel:", "data:")):
        return None
    try:
        link = normalized_url(urljoin(base, raw))
    except (ValueError, UnsafeURLError):
        return None
    return link


def application_links(html: str, url: str, schema: dict[str, Any] | None = None, *,
                      keyword_profile: Any = None) -> list[dict[str, Any]]:
    """Return evidence-backed candidate links without navigating or submitting forms."""
    soup = BeautifulSoup(html, "html.parser")
    apply_words = keyword_profile.list("job_apply") if keyword_profile else APPLY_WORDS
    found: dict[str, dict[str, Any]] = {}

    def add(raw: str, label: str, source: str, *, explicit: bool = False) -> None:
        link = _url_candidate(raw, url)
        if not link:
            return
        destination = urlsplit(link)
        path = destination.path.casefold()
        if any(path == x or path.startswith(x + "/") for x in BAD_DESTINATIONS):
            return
        score = 20
        if any(destination.hostname == x or (destination.hostname or "").endswith("." + x) for x in ATS_HOSTS):
            score += 35
        if re.search(r"/(apply|application|candidature|postuler)(?:/|$)", path):
            score += 30
        if explicit:
            score += 30
        if (destination.hostname or "") == (urlsplit(url).hostname or ""):
            score += 5
        if canonical_job_url(link) == canonical_job_url(url):
            # A button pointing back at the posting is not an application form.
            return
        entry = {"url": link, "label": label[:100], "source": source,
                 "requires_login": False, "priority": max(0, min(100, score))}
        existing = found.get(link)
        if existing is None or entry["priority"] > existing["priority"]:
            found[link] = entry

    for node in soup.select("a[href], form[action], [data-apply-url]"):
        label = node.get_text(" ", strip=True) or str(node.get("aria-label") or node.get("title") or "")
        label_fold = _fold(label + " " + str(node.get("class") or ""))
        explicit = any(s in label_fold for s in apply_words)
        raw = node.get("data-apply-url") or node.get("href") or node.get("action")
        href = str(raw or "")
        if not (explicit or re.search(r"/(apply|application|postuler|candidature)(?:/|\?|$)", href.casefold())):
            continue
        # Never submit a form. An action URL is evidence of a destination only.
        add(href, label, "html_form" if node.name == "form" else "html_link", explicit=explicit)

    # Some ATS pages provide the form URL in structured metadata.
    for field in ("applicationUrl", "applyUrl"):
        if schema and isinstance(schema.get(field), str):
            add(str(schema[field]), field, "job_schema", explicit=True)

    return sorted(found.values(), key=lambda x: (-x["priority"], x["url"]))


def parse_job_page(html: str, url: str, *, keyword_profile: Any = None) -> dict[str, Any]:
    """Extract job identity, links, and status signals from a single HTML snapshot."""
    soup = BeautifulSoup(html, "html.parser")
    schema = job_schema(soup, url)
    canonical_link = soup.select_one('link[rel="canonical"][href]')
    declared_canonical = _url_candidate(canonical_link.get("href", ""), url) if canonical_link else None
    schema_source_url = _url_candidate(str(schema.get("url", "")), url) if schema and schema.get("url") else None
    h1 = soup.find("h1")
    title = _plain_value(schema.get("title")) if schema else ""
    if not title and h1:
        title = h1.get_text(" ", strip=True)
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    company = _plain_value(schema.get("hiringOrganization")) if schema else ""
    location = _schema_location(schema)
    contract = _plain_value(schema.get("employmentType")) if schema else ""
    identifier = _plain_value(schema.get("identifier")) if schema else ""
    # ISCOD is the publishing school, not necessarily the partner employer.
    publisher = "ISCOD" if (urlsplit(url).hostname or "").lower().endswith("iscod.fr") else ""
    if publisher and _fold(company) == "iscod":
        company = ""
    # Prefer visible location markers over a search snippet. URL slugs are
    # secondary evidence and never by themselves certify a city match.
    body_snapshot = soup.get_text(" ", strip=True)
    if publisher and not company:
        # Only an explicit partner name counts; 'entreprise partenaire'
        # without a name must leave the actual employer unresolved.
        named_partner = re.search(r"(?:entreprise partenaire|employeur)\s*[:：]\s*([A-Za-zÀ-ÿ0-9 &.'-]{3,65})", body_snapshot, re.I)
        if named_partner:
            company = re.split(r"[.,;|]", named_partner.group(1))[0].strip()
    if not contract:
        labeled_contract = re.search(r"(?:contrat|type de contrat)\s*[:：]\s*(CDI|CDD|alternance|apprentissage|stage)", body_snapshot, re.I)
        if labeled_contract:
            contract = labeled_contract.group(1)
    if not location:
        extracted = re.search(r"(?:poste\s+bas[ée]\s+[àa]|localisation\s*[:：]|lieu\s*[:：])\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s-]{1,42})", body_snapshot, re.I)
        if extracted:
            location = re.split(r"[.,;|\n]", extracted.group(1))[0].strip()
    location_evidence = "schema" if _schema_location(schema) else "visible_text" if location else "unknown"
    slug_city = ""
    if not location:
        for city in ("paris", "nantes", "toulouse", "lyon", "lille", "bordeaux", "balma", "nice", "rennes", "strasbourg", "marseille", "creteil", "fontenay-sous-bois"):
            if re.search(r"(?:^|[-/])" + re.escape(city) + r"(?:[-/.]|$)", _fold(urlsplit(url).path)):
                slug_city = city
                break
        if slug_city:
            location, location_evidence = slug_city, "url_slug"
    # Visibility tests on rendered body rather than inline JS or hidden templates.
    for node in soup.select("script,style,noscript,template,svg,nav,footer,header"):
        node.decompose()
    main = soup.select_one("main,article,[role=main]") or soup.body or soup
    visible = _fold(main.get_text(" ", strip=True))[:100000]
    closed_words = keyword_profile.list("job_closed") if keyword_profile else CLOSED_MARKERS
    blocked_words = keyword_profile.list("job_blocked") if keyword_profile else BLOCK_MARKERS
    apply_words = keyword_profile.list("job_apply") if keyword_profile else APPLY_WORDS
    blocks = [m for m in closed_words if _fold(m) in visible]
    access_blocks = [m for m in blocked_words if _fold(m) in visible]
    links = application_links(html, url, schema, keyword_profile=keyword_profile)
    # Job boards sometimes render an action as a JS-backed button rather than
    # exposing a form URL. Keep that signal separate from a verified destination.
    controls = []
    for node in soup.select("button, input[type=submit], [role=button]"):
        if node.has_attr("disabled") or str(node.get("aria-disabled", "")).lower() == "true":
            continue
        label = (node.get_text(" ", strip=True) or str(node.get("value") or node.get("aria-label") or "")).strip()
        if any(_fold(keyword) in _fold(label) for keyword in apply_words):
            controls.append(label[:80])
    date = str(schema.get("validThrough", "")) if schema else ""
    expired = False
    if date:
        try:
            date_value = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if date_value.tzinfo is None:
                date_value = date_value.replace(tzinfo=timezone.utc)
            expired = date_value < datetime.now(timezone.utc)
        except ValueError:
            pass
    vacancy_description_signals = bool(re.search(r"\b(?:nous recherchons|descriptif du poste|vos missions|votre mission|rejoignez|we are hiring|job description)\b", _fold(visible)))
    return {"title": title[:220], "company": company[:150], "location": location[:150],
            "publisher": publisher, "employer_evidence": "visible_partner_name" if publisher and company else "schema" if company else "unknown",
            "vacancy_description_signals": vacancy_description_signals,
            "location_evidence": location_evidence, "identifier": identifier[:120],
            "declared_canonical_url": declared_canonical,
            "schema_posting_url": schema_source_url,
            "contract_type": contract[:100], "schema_found": schema is not None,
            "closed_signals": blocks, "blocked_signals": access_blocks,
            "schema_valid_through_expired": expired, "application_links": links,
            "visible_apply_controls": controls[:5],
            "body_length": len(visible), "has_job_heading": bool(h1 and len(title) > 4)}


def assess_status(page: dict[str, Any], url: str, *, rendering_needed: bool = False) -> tuple[str, str, str, list[str]]:
    """Distinguish a visible live listing from absence, login walls, and thin shells."""
    if page["blocked_signals"]:
        return "UNKNOWN", "access_blocked", "low", page["blocked_signals"]
    if page["closed_signals"] and (is_specific_job_url(url) or is_individual_job_page(page, url)):
        return "CLOSED", "explicit_closed_notice", "high", page["closed_signals"]
    if rendering_needed:
        return "UNKNOWN", "rendering_needed", "low", ["javascript_shell"]
    if page["schema_valid_through_expired"]:
        return "UNKNOWN", "expired_schema_date", "low", ["validThrough in past"]
    if page["application_links"] and (page["schema_found"] or (is_specific_job_url(url) and page["has_job_heading"]) or is_individual_job_page(page, url)):
        return "LIVE", "application_link_visible", "medium", ["job_detail_and_apply_link"]
    if page["visible_apply_controls"] and (is_specific_job_url(url) or is_individual_job_page(page, url)) and (page["schema_found"] or page["has_job_heading"]):
        return "LIVE", "apply_control_visible", "medium", ["job_detail_and_apply_control_without_url"]
    if page["schema_found"] and is_specific_job_url(url):
        return "UNKNOWN", "job_schema_without_apply_link", "low", ["job_schema"]
    return "UNKNOWN", "insufficient_evidence", "low", []


def _terms(text: str) -> set[str]:
    """Use meaningful tokens; don't inflate matches with generic job terminology."""
    stop = {"dev", "job", "emploi", "offre", "alternance", "h", "f", "the", "et", "de", "la", "le", "un", "une", "junior", "senior", "poste", "engineer"}
    return {x for x in re.findall(r"[\w+#.]{2,}", _fold(text)) if x not in stop}


def _contract_set(value: str) -> set[str]:
    """Normalize explicit contract variants and schema.org employmentType codes."""
    value = _fold(value)
    codes = set()
    for pattern, code in ((r"(?<!\w)cdi(?!\w)|permanent|full.time|full_time|temps plein", "permanent"),
                          (r"(?<!\w)cdd(?!\w)|fixed.term|temporary|contractor", "fixed_term"),
                          (r"internship|(?<!\w)intern(?!\w)|(?<!\w)stage(?!\w)|stagiaire", "internship"),
                          (r"alternance|apprentice|apprentissage|apprenti|work.study", "apprenticeship")):
        if re.search(pattern, value):
            codes.add(code)
    return codes


def _location_matches(requested: str, observed: str) -> bool:
    # An observed place must be matched as a geographical token, not a substring.
    return bool(re.search(r"(?<!\w)" + re.escape(_fold(requested)) + r"(?!\w)", _fold(observed)))


def match_job(page: dict[str, Any], *, title: str, company: str = "", location: str = "",
              contract_type: str = "", reference: str = "", seniority: str = "",
              search_hit: dict[str, Any] | None = None,
              employer_context: EmployerContext | None = None, source_url: str = "") -> dict[str, Any]:
    """Rank page evidence without promoting snippets, publishers or contradictions."""
    evidence: list[str] = []
    score = 0
    job_title = page.get("title", "")
    if not job_title:
        return {"score": 0, "status": "unresolved", "evidence": ["missing_title"], "hard_conflicts": []}
    requested = _terms(title)
    overlap = len(requested & _terms(job_title)) / max(1, len(requested))
    if requested:
        if overlap >= .85:
            score += 55
            evidence.append("title_tokens_match")
        elif overlap >= .5:
            score += 30
            evidence.append("partial_title_match")
        else:
            evidence.append("title_mismatch")
    else:
        evidence.append("title_not_supplied")
    hard: list[str] = []
    observed_employer = page.get("company", "")
    verified_domain = bool(employer_context and source_url and
                           employer_context.assess(source_url)["state"] == "confirmed")
    if company:
        if observed_employer:
            if _fold(company) == _fold(observed_employer) or (employer_context and legal_name_matches(observed_employer, employer_context)):
                score += 25
                evidence.append("employer_schema_match")
            elif _fold(company) in _fold(observed_employer) and len(_fold(company)) > 4:
                evidence.append("employer_name_overlap_unverified")
            else:
                evidence.append("employer_conflict")
                hard.append("employer_conflict")
        elif verified_domain:
            score += 25
            evidence.append("employer_confirmed_domain")
        else:
            evidence.append("employer_unverified" if page.get("publisher") else "employer_missing")
    if location:
        observed_location = page.get("location", "")
        if observed_location:
            if _location_matches(location, observed_location):
                score += 15 if page.get("location_evidence") != "url_slug" else 6
                evidence.append("location_match")
            else:
                evidence.append("location_mismatch")
                hard.append("location_mismatch")
        else:
            evidence.append("location_missing")
    if contract_type:
        desired_contracts = _contract_set(contract_type)
        found_contracts = _contract_set(page.get("contract_type", ""))
        if desired_contracts and found_contracts:
            if desired_contracts & found_contracts:
                score += 5
                evidence.append("contract_match")
            else:
                evidence.append("contract_mismatch")
                hard.append("contract_mismatch")
        else:
            evidence.append("contract_unverified")
    if reference:
        identifier = str(page.get("identifier", ""))
        if identifier and _fold(reference) == _fold(identifier):
            score += 10
            evidence.append("reference_match")
        elif identifier:
            evidence.append("reference_mismatch")
            hard.append("reference_mismatch")
        else:
            evidence.append("reference_missing")
    if seniority:
        seniority_terms = {"junior", "senior", "lead", "principal", "stagiaire", "alternant"}
        expected = _fold(seniority)
        found = set(_terms(job_title)) & seniority_terms
        if expected in seniority_terms and found and expected not in found:
            evidence.append("seniority_mismatch")
            hard.append("seniority_mismatch")
    # Definite contradictory evidence outranks a similar title and keyword weights.
    if hard:
        score = min(score, 29)
    score = max(0, min(100, score))
    employer_supported = (not company or "employer_schema_match" in evidence or "employer_confirmed_domain" in evidence)
    status = "likely_match" if score >= 75 and "title_tokens_match" in evidence and not hard and employer_supported else "possible_match" if score >= 30 and not hard else "unresolved"
    return {"score": score, "status": status, "evidence": evidence, "hard_conflicts": hard,
            "employer_identity": "confirmed_by_page" if "employer_schema_match" in evidence else "confirmed_by_source" if "employer_confirmed_domain" in evidence else "unverified"}
