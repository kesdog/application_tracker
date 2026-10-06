"""Contract categories used by filters and agent input validation."""
import re
import unicodedata
from typing import Literal

ContractCategory = Literal["CDI", "CDD", "PART_TIME", "APPRENTICESHIP_INTERNSHIP"]
CONTRACT_OPTIONS = {
    "CDI": "Full time (CDI)",
    "CDD": "Fixed term (CDD)",
    "PART_TIME": "Part time (Temps partiel)",
    "APPRENTICESHIP_INTERNSHIP": "Apprenticeship / Internship (Alternance / Stage)",
}
CONTRACT_CATEGORIES = {
    "CDI": ("cdi", "permanent", "full time", "temps plein", "contrat a duree indeterminee"),
    "CDD": ("cdd", "fixed", "contrat a duree determinee"),
    "PART_TIME": ("part time", "temps partiel"),
    "APPRENTICESHIP_INTERNSHIP": ("alternance", "apprenticeship", "apprentice", "internship", "intern", "stage", "stagiaire", "apprentissage"),
}


def matches_contract_category(value: str | None, category: str) -> bool:
    text = unicodedata.normalize("NFKD", (value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())
    return any(f" {term} " in f" {text} " for term in CONTRACT_CATEGORIES[category])


def canonical_contract(value):
    if value is None or isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, str):
        canonical = value.strip().upper()
        if canonical in CONTRACT_CATEGORIES:
            return canonical
        matches = [category for category in CONTRACT_CATEGORIES if matches_contract_category(value, category)]
        if len(matches) == 1:
            return matches[0]
    raise ValueError("Choose CDI, CDD, PART_TIME or APPRENTICESHIP_INTERNSHIP; use null if the contract is unknown or ambiguous")
