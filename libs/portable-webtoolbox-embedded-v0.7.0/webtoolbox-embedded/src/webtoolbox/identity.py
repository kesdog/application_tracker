"""Employer-context boundary: caller-provided identity, not brand substring matching."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit


def domain(value: str) -> str:
    # Hostnames must be complete; normalize schemes, ports and paths away.
    host = urlsplit(value if "://" in value else f"https://{value}").hostname or ""
    return host.casefold().removeprefix("www.").rstrip(".")


def within(host: str, root: str) -> bool:
    return bool(root and (host == root or host.endswith("." + root)))


@dataclass(frozen=True)
class EmployerContext:
    """No implicit confirmation: require an explicit evidence-backed status.

    Example source: 'application_confirmation', 'job_posting', 'user_confirmed'.
    A verified ATS can be crawled, but is not itself the employer's domain.
    """
    company: str
    domain: str = ""
    status: str = "unknown"  # confirmed, provisional or unknown
    evidence_source: str = ""
    evidence_url: str = ""
    aliases: tuple[str, ...] = ()
    ats_domains: tuple[str, ...] = ()
    rejected_domains: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"confirmed", "provisional", "unknown"}:
            raise ValueError("Invalid employer identity status")
        if self.status == "confirmed" and (not self.domain or not self.evidence_source):
            raise ValueError("Confirmed domain requires domain and evidence_source")
        for key in ("domain",):
            object.__setattr__(self, key, domain(getattr(self, key)) if getattr(self, key) else "")
        for key in ("ats_domains", "rejected_domains"):
            object.__setattr__(self, key, tuple(domain(x) for x in getattr(self, key)))

    @classmethod
    def from_mapping(cls, value: "EmployerContext | Mapping[str, Any]", *, company: str = "") -> "EmployerContext":
        if isinstance(value, cls):
            return value
        return cls(company=company or str(value.get("company", "")), domain=str(value.get("domain", "")),
                   status=str(value.get("status", "unknown")),
                   evidence_source=str(value.get("evidence_source", "")),
                   evidence_url=str(value.get("evidence_url", "")),
                   aliases=tuple(value.get("aliases", ())),
                   ats_domains=tuple(value.get("ats_domains", ())),
                   rejected_domains=tuple(value.get("rejected_domains", ())))

    def assess(self, url: str) -> dict[str, Any]:
        host = domain(url)
        if any(within(host, bad) for bad in self.rejected_domains):
            return {"state": "conflicting", "reason": "explicitly_rejected_domain", "host": host}
        if self.domain and within(host, self.domain):
            return {"state": self.status if self.status != "unknown" else "provisional",
                    "reason": "employer_domain_with_supplied_evidence" if self.status == "confirmed" else "unverified_employer_domain",
                    "host": host, "evidence_source": self.evidence_source, "evidence_url": self.evidence_url}
        if any(within(host, ats) for ats in self.ats_domains):
            return {"state": "provisional", "reason": "authorized_ats_not_employer_identity", "host": host}
        return {"state": "unknown", "reason": "domain_outside_employer_context", "host": host}

    def allows_crawl(self, url: str) -> bool:
        result = self.assess(url)
        return result["reason"] in {"employer_domain_with_supplied_evidence", "unverified_employer_domain", "authorized_ats_not_employer_identity"}


def site_identity(html: str, url: str) -> dict[str, Any]:
    """Collect publisher-declared Organization metadata, never agency footer credits.

    Metadata supplies evidence and possible contradictions, not confirmation.
    """
    import json
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    owners = []
    for script in soup.select('script[type="application/ld+json"]')[:25]:
        try:
            parsed = json.loads(script.string or script.get_text() or "")
        except (TypeError, ValueError):
            continue
        documents = parsed if isinstance(parsed, list) else [parsed]
        for doc in documents:
            if not isinstance(doc, dict):
                continue
            documents_at_level = doc.get("@graph", [doc])
            for entity in documents_at_level if isinstance(documents_at_level, list) else []:
                if not isinstance(entity, dict):
                    continue
                kinds = entity.get("@type", [])
                if isinstance(kinds, str):
                    kinds = [kinds]
                if not any(k in {"Organization", "Corporation", "LocalBusiness"} or
                           str(k).endswith("/Organization") for k in kinds):
                    continue
                owner_url = str(entity.get("url") or "")
                if owner_url and not within(domain(owner_url), domain(url)):
                    continue
                address = entity.get("address", {})
                country = address.get("addressCountry", "") if isinstance(address, dict) else ""
                owners.append({"legal_name": str(entity.get("legalName") or entity.get("name") or ""),
                               "description": str(entity.get("description") or "")[:250],
                               "sector": str(entity.get("industry") or "")[:120],
                               "country": str(country or "")[:50],
                               "url": owner_url, "evidence": "same_host_jsonld_organization"})
    if len(owners) == 1:
        return owners[0]
    # Conflicting or multiple organizations on one page are not silently selected.
    return {"evidence": "ambiguous_organizations" if owners else "no_site_organization_metadata",
            "organizations_found": len(owners)}


def legal_name_matches(observed: str, context: EmployerContext) -> bool:
    import re
    legal_suffixes = {"sa", "sas", "sasu", "sarl", "se", "srl", "spa", "gmbh", "ltd", "limited", "llc", "inc"}
    def cleaned(value: str) -> str:
        tokens = [t for t in re.findall(r"\w+", value.casefold()) if t not in legal_suffixes]
        return " ".join(tokens)
    return bool(observed and cleaned(observed) in {cleaned(context.company), *(cleaned(v) for v in context.aliases)})
