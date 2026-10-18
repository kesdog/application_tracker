"""Evidence-conservative contact prioritization for optional recruitment workflows.

This module is independent of transport, search provider, browser and agent stack.
Ranking scores are *ordering heuristics*, not confidence probabilities.
"""

from __future__ import annotations

import copy
import re
from typing import Any
from urllib.parse import urlsplit
from .profiles import KeywordProfile, load_profile, DEFAULTS


_RECRUITER_TITLE = re.compile(
    r"\b(?:recruteur|recruteuse|recruiter|recrutement|recruitment|"
    r"talent\s+acquisition|charg[ée]\s+de\s+recrutement|"
    r"responsable\s+rh|direct(?:eur|rice)\s+(?:des\s+)?ressources\s+humaines|"
    r"human\s+resources|people\s+operations|people\s+ops|"
    r"chief\s+(?:people|human\s+resources)\s+officer|"
    r"(?:head|director|vp|vice\s+president)\s+of\s+(?:people|talent|human\s+resources)|"
    r"(?:directeur|directrice|responsable)\s+(?:du\s+)?(?:personnel|talent|recrutement)|"
    r"(?:directeur|directrice)\s+rh|personalreferent|personalabteilung)\b", re.IGNORECASE
)


def _source_verified(candidate: dict[str, Any]) -> bool:
    """A source-backed mailbox must have evidence of actual publication."""
    return any(
        method.get("publication") == "published" and method.get("evidence")
        and method.get("email")
        for method in candidate.get("emails", [])
    )


def rank_contact(candidate: dict[str, Any], *, keyword_profile: KeywordProfile | None = None) -> dict[str, Any]:
    """Add a transparent, non-probabilistic relevance assessment to one record.

    Classification depends on *direct* vacancy evidence or recruiter roles. A
    company domain match alone never establishes personal ownership or hiring
    responsibility. Generic corporate addresses cannot be preferred to proven
    recruitment inboxes merely because their domain matches.
    """
    result = copy.deepcopy(candidate)
    name = (result.get("name") or "").strip()
    role = (result.get("role") or "").strip()
    purpose = result.get("purpose", "unknown")
    vacancy = result.get("vacancy_responsibility", "unknown")
    identity = result.get("employer_match", {}).get("state", "unknown")
    excluded = result.get("exclusion_reason")
    emails = result.get("emails", [])
    fit = result.get("fit", {})
    fit_conflicts = [kind for kind in ("region", "sector") if fit.get(kind, {}).get("state") == "mismatch"]
    if fit_conflicts:
        # Do not erase source evidence; flag mismatch independently of publication.
        result["relevance_warning"] = "mismatch_in_" + "_".join(fit_conflicts)
    has_mailbox = _source_verified(result)
    has_recruitment_mailbox = has_mailbox and any(
        item.get("purpose") == "recruitment" and not item.get("exclusion_reason")
        for item in emails
    )
    # Extra configured titles complement the preexisting multilingual regex.
    extra_titles = load_profile(keyword_profile).list("recruiter_titles")
    is_recruiter = bool(name and (any(
        re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", role.casefold()) for term in extra_titles) or
        (list(extra_titles) == DEFAULTS["recruiter_titles"] and _RECRUITER_TITLE.search(role))))
    associated_recruiter_email = bool(
        is_recruiter and has_mailbox and len(emails) == 1
        and not emails[0].get("exclusion_reason")
        and result.get("association", {}).get("confidence") == "scoped_record"
    )

    reasons: list[str] = []
    if excluded or identity == "conflicting":
        category, score = "excluded", 0
        reasons.append("excluded_purpose" if excluded else "conflicting_employer_identity")
    elif vacancy == "published_for_vacancy" and (name or has_mailbox):
        category, score = "vacancy_specific_contact", 500
        reasons.append("explicit_vacancy_contact_evidence")
    elif is_recruiter:
        category, score = "named_recruiter", 400
        reasons.append("named_person_with_recruitment_title")
    elif has_recruitment_mailbox:
        category, score = "recruitment_mailbox", 300
        reasons.append("published_recruitment_mailbox")
    elif has_mailbox and not name:
        category, score = "general_company_mailbox", 120
        reasons.append("published_mailbox_without_recruitment_purpose")
    elif name:
        category, score = "named_other_contact", 90
        reasons.append("named_contact_without_recruitment_responsibility")
    elif has_mailbox:
        category, score = "other_mailbox", 60
        reasons.append("published_mailbox_without_recruitment_match")
    else:
        category, score = "unresolved", 20
        reasons.append("no_published_contact_method")

    if score and identity == "confirmed":
        score += 15
        reasons.append("confirmed_employer_alias")
    elif score and identity == "provisional":
        score += 5
        reasons.append("domain_match_only_provisional")

    has_email_for_outreach = bool(
        score and result.get("email") and (has_recruitment_mailbox or associated_recruiter_email)
        and identity != "conflicting" and not fit_conflicts
        and (not result.get("identity_required") or identity == "confirmed")
        and not result.get("cache_stale", False)
        and category in {"named_recruiter", "recruitment_mailbox", "vacancy_specific_contact"}
    )
    # A published generic inbox may be presented as a fallback, never as a
    # confirmed recruiting recipient. Users decide whether to contact it.
    if category == "excluded":
        action = "do_not_recommend"
    elif fit_conflicts:
        action = "verify_region_or_team_fit"
    elif result.get("cache_stale", False):
        action = "refresh_stale_evidence"
    elif category == "general_company_mailbox":
        action = "verify_recruitment_purpose"
    elif category in {"named_recruiter", "vacancy_specific_contact"} and not has_mailbox:
        action = "find_contact_method"
    elif result.get("identity_required") and identity != "confirmed":
        action = "verify_employer_identity"
    elif not has_email_for_outreach:
        action = "verify_recipient"
    elif identity == "unknown":
        action = "verify_employer_identity"
    else:
        action = "review_before_follow_up"

    result["contact_priority"] = {
        "category": category,
        "score": score,
        "score_type": "heuristic_not_confidence",
        "reasons": reasons,
        "outreach_eligible": has_email_for_outreach,
        "recommended_action": action,
    }
    return result


def _dedupe_key(candidate: dict[str, Any]) -> tuple[str, ...]:
    """A named person's address cannot be merged with an unnamed mailbox."""
    name = " ".join((candidate.get("name") or "").casefold().split())
    role = " ".join((candidate.get("role") or "").casefold().split())
    email = (candidate.get("email") or "").casefold().strip()
    if name:
        # Preserve conflicting associations; don't assume identical names or
        # parallel lists imply the same person or a shared email.
        host = (urlsplit(candidate.get("source_url") or "").hostname or "").lower()
        return ("person", name, role, email, host)
    if email:
        return ("mailbox", email)
    return ("unresolved", candidate.get("source_url") or "", role)


def merge_and_rank(candidates: list[dict[str, Any]], *, keyword_profile: KeywordProfile | None = None) -> list[dict[str, Any]]:
    """Deduplicate exact evidence-compatible records and rank valuable leads.

    All source URLs are retained. Incompatible purposes or ownership claims
    must not be combined; existing source-backed assertions stay unchanged.
    """
    collected: dict[tuple[str, ...], dict[str, Any]] = {}
    for source in candidates:
        key = _dedupe_key(source)
        if key not in collected:
            record = copy.deepcopy(source)
            record["source_urls"] = [source["source_url"]] if source.get("source_url") else []
            record["source_observations"] = [{
                "source_url": source.get("source_url"),
                "fetched_at": source.get("fetched_at"),
                "cache_stale": source.get("cache_stale", False),
                "purpose": source.get("purpose"),
                "exclusion_reason": source.get("exclusion_reason")
            }]
            collected[key] = record
            continue
        current = collected[key]
        observation = {"source_url": source.get("source_url"),
                       "fetched_at": source.get("fetched_at"),
                       "cache_stale": source.get("cache_stale", False),
                       "purpose": source.get("purpose"),
                       "exclusion_reason": source.get("exclusion_reason")}
        if observation not in current["source_observations"]:
            current["source_observations"].append(observation)
        # Both sources must be fresh before a merged record can claim freshness.
        current["cache_stale"] = current.get("cache_stale", False) or source.get("cache_stale", False)
        # Preserve identity conflict from either source; no automatic upgrade on merge.
        existing_identity = current.get("employer_match", {}).get("state", "unknown")
        new_identity = source.get("employer_match", {}).get("state", "unknown")
        if "conflicting" in {existing_identity, new_identity}:
            current.setdefault("employer_match", {})["state"] = "conflicting"
        elif existing_identity == "confirmed" and new_identity not in {"confirmed", "unknown"}:
            current.setdefault("employer_match", {})["state"] = "provisional"
        # A mismatch from either source must remain visible, not become a fresh verified match.
        for dimension in ("region", "sector"):
            v = source.get("fit", {}).get(dimension)
            if v and v.get("state") == "mismatch":
                current.setdefault("fit", {})[dimension] = copy.deepcopy(v)
        if (current.get("purpose") != source.get("purpose") or
                current.get("exclusion_reason") != source.get("exclusion_reason")):
            # Contradictory pages must not upgrade a generic/support mailbox to
            # a validated recruitment address. Keep both assertions traceable.
            observations = current.setdefault("purpose_evidence", [{
                "purpose": current.get("purpose"),
                "exclusion_reason": current.get("exclusion_reason"),
                "source_url": current.get("source_url"),
            }])
            observation = {"purpose": source.get("purpose"),
                           "exclusion_reason": source.get("exclusion_reason"),
                           "source_url": source.get("source_url")}
            if observation not in observations:
                observations.append(observation)
            current["purpose"] = "ambiguous"
            current["exclusion_reason"] = "conflicting_purpose_evidence"
        if source.get("source_url") and source["source_url"] not in current["source_urls"]:
            current["source_urls"].append(source["source_url"])
        for item in source.get("emails", []):
            matching = next((e for e in current.get("emails", [])
                             if e.get("email", "").casefold() == item.get("email", "").casefold()
                             and e.get("purpose") == item.get("purpose")), None)
            if matching:
                matching.setdefault("evidence", []).extend(copy.deepcopy(item.get("evidence", [])))
            else:
                current.setdefault("emails", []).append(copy.deepcopy(item))
        # Do not upgrade unknown vacancy responsibility by combining unrelated
        # cards. Preserve strongest evidence only when exactly the same record.
        if source.get("vacancy_responsibility") == "published_for_vacancy":
            current["vacancy_responsibility"] = "published_for_vacancy"
            if source.get("vacancy_evidence"):
                current["vacancy_evidence"] = copy.deepcopy(source["vacancy_evidence"])
    ranked = [rank_contact(c, keyword_profile=keyword_profile) for c in collected.values()]
    return sorted(ranked, key=lambda c: (-c["contact_priority"]["score"],
                                        not bool(c.get("email")),
                                        (c.get("name") or c.get("email") or "").casefold()))


def shortlist_summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """Small aggregations are safe for model-facing responses and UI badges."""
    groups: dict[str, int] = {}
    for candidate in candidates:
        kind = candidate.get("contact_priority", {}).get("category", "unresolved")
        groups[kind] = groups.get(kind, 0) + 1
    return groups
