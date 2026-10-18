"""Portable, validated keyword configuration with no model or network dependency."""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from .job_postings import CLOSED_MARKERS, APPLY_WORDS, BLOCK_MARKERS

# Configurable defaults replace magic strings in separate extraction modules.
DEFAULTS: dict[str, Any] = {
    "contact_recruitment": ["recruit", "recrut", "postul", "candidat", "embauch", "career", "hiring", "talent", "people ops", "ressources humaines", "rh", "emploi", "jobs"],
    "contact_exclusions": {
        "privacy": ["privacy", "dpo", "rgpd", "gdpr", "cookies", "cookie", "données personnelles", "donnees personnelles", "politique de confidentialité", "protection des données", "privacy policy", "droit d'accès"],
        "media": ["press", "presse", "media", "journalist", "globalprteam", "relations presse", "communication presse"],
        "sales": ["sales", "commercial", "business development", "marketing", "marketer", "publicit"],
        "support": ["support", "helpdesk", "technical support", "assistance technique", "service client"],
    },
    "vacancy_confidentiality": ["confidentialité des offres", "postes confidentiels", "offres confidentielles", "vacances confidentielles", "recrutement confidentiel"],
    "page_positive": ["recruit", "recrut", "career", "carriere", "emploi", "contact", "about", "equipe", "team", "people", "talent", "rh", "staff", "personnel", "postul"],
    "page_negative": ["cookie", "privacy", "/confidentialit", "/confidentiality", "politique", "terms", "mentions-legales", "legal", "rgpd", "vendor", "credits", "footer", "search", "recherche", "pagead", "marketing", "presse", "pricing", "tarifs", "tarif", "abonnement", "advertis", "sponsor", "publicit", "offres-promotionnelles"],
    "recruiter_titles": ["chief people officer", "talent acquisition", "responsable recrutement", "chargé de recrutement", "chargée de recrutement", "responsable ressources humaines", "directeur des ressources humaines", "directrice des ressources humaines", "responsable rh", "it recruiter", "recruiter", "recruteur", "recruteuse", "recrutement", "recruitment", "human resources"],
    "contact_queries": ["{company} {role} recrutement contact RH", "{company} official company site identity", "site:{domain} recrutement careers contact", "{company} equipe recrutement adresse candidature"],
    "job_queries": ['"{company}" "{title}" {location} emploi candidature', "{company} {title} {location} postuler job"],
    "job_closed": list(CLOSED_MARKERS),
    "job_apply": list(APPLY_WORDS),
    "job_blocked": list(BLOCK_MARKERS),
    "keywords": {"required": [], "preferred": {}, "excluded": [], "synonyms": {}},
}


def _terms(value: Any, *, key: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 100 or not all(isinstance(v, str) and 0 < len(v) <= 100 for v in value):
        raise ValueError(f"{key} must be a list of at most 100 short strings")
    return [v.strip().casefold() for v in value]


@dataclass(frozen=True)
class KeywordProfile:
    """Immutable-ish profile: validated deep copies, no global keyword mutation."""
    data: dict[str, Any]

    def list(self, key: str) -> tuple[str, ...]:
        return tuple(self.data[key])

    def groups(self, key: str) -> dict[str, tuple[str, ...]]:
        return {name: tuple(values) for name, values in self.data[key].items()}

    def queries(self, key: str, **args: str) -> list[str]:
        # Only a fixed mapping is interpolated; caller never executes template text.
        result = []
        for template in self.data[key]:
            if "{domain}" in template and not args.get("domain"):
                continue
            query = " ".join(template.format(**{k: v or "" for k, v in args.items()}).split())
            if query:
                result.append(query[:300])
        return result[:6]

    def score_text(self, text: str) -> dict[str, Any]:
        terms = self.data["keywords"]
        normalized = text.casefold()
        def found(term: str) -> bool:
            # Matching full terms rather than arbitrary fragments avoids a name collision.
            variations = [term, *terms["synonyms"].get(term, [])]
            return any(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", normalized) for word in variations)
        matched = [term for term in terms["required"] if found(term)]
        excluded = [term for term in terms["excluded"] if found(term)]
        preferred = {term: weight for term, weight in terms["preferred"].items() if found(term)}
        return {"eligible": not excluded and len(matched) == len(terms["required"]),
                "missing_required": [t for t in terms["required"] if t not in matched],
                "excluded": excluded, "matched_preferred": preferred, "score": sum(preferred.values())}


def load_profile(source: KeywordProfile | Mapping[str, Any] | Path | str | None = None) -> KeywordProfile:
    """Overlay only supplied keys; omit any key to keep stable library defaults."""
    if isinstance(source, KeywordProfile):
        return source
    if isinstance(source, (str, Path)):
        override = json.loads(Path(source).read_text(encoding="utf-8"))
    else:
        override = dict(source or {})
    if not isinstance(override, dict) or set(override) - set(DEFAULTS):
        raise ValueError("Unknown keyword profile keys")
    data = copy.deepcopy(DEFAULTS)
    for key, value in override.items():
        if key in {"contact_exclusions", "keywords"}:
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be an object")
            if set(value) - set(data[key]):
                raise ValueError(f"Unknown {key} keys")
            data[key].update(copy.deepcopy(value))
        else:
            data[key] = copy.deepcopy(value)
    for key in ("contact_recruitment", "vacancy_confidentiality", "page_positive", "page_negative", "recruiter_titles", "job_closed", "job_apply", "job_blocked"):
        data[key] = _terms(data[key], key=key)
    for k, v in data["contact_exclusions"].items():
        data["contact_exclusions"][k] = _terms(v, key=k)
    for key in ("contact_queries", "job_queries"):
        items = data[key]
        if not isinstance(items, list) or len(items) > 6 or not all(isinstance(t, str) and len(t) <= 300 for t in items):
            raise ValueError(f"{key} must be a list of 0..6 query templates")
        for template in items:
            # Restrict to known safe placeholders, no attribute/index access.
            if any(token not in {"company", "role", "domain", "title", "location"} for token in re.findall(r"\{([^{}]+)\}", template)):
                raise ValueError(f"Unsupported query placeholder in {key}")
    keywords = data["keywords"]
    for name in ("required", "excluded"):
        keywords[name] = _terms(keywords[name], key=name)
    if not isinstance(keywords["preferred"], dict) or len(keywords["preferred"]) > 100 or not all(
            isinstance(k, str) and 0 < len(k) <= 100 and type(v) in {int, float} and -100 <= v <= 100
            for k, v in keywords["preferred"].items()):
        raise ValueError("preferred must map up to 100 terms to bounded numeric weights")
    keywords["preferred"] = {k.casefold(): v for k, v in keywords["preferred"].items()}
    if not isinstance(keywords["synonyms"], dict) or len(keywords["synonyms"]) > 100:
        raise ValueError("synonyms must be a small dictionary")
    keywords["synonyms"] = {key.casefold(): _terms(value, key=key) for key, value in keywords["synonyms"].items()}
    return KeywordProfile(data)
