"""Deterministic, LLM-free extraction with portable JSON recipes."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup
from urllib.parse import urljoin


class InvalidRecipe(ValueError):
    """The extraction recipe does not have a supported shape."""


def read_recipe(recipe: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    if recipe is None:
        return {}
    if isinstance(recipe, dict):
        data = recipe
    else:
        path = Path(recipe).expanduser()
        data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("fields", {}), dict):
        raise InvalidRecipe("Recipe must contain an object called 'fields'")
    return data


def extract_fields(html: str, recipe: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Fields: {name: {selector, attribute?, all?, pattern?, max_items?}}."""
    soup = BeautifulSoup(html, "html.parser")
    scope = recipe.get("scope")
    if scope:
        # A missing optional scope produces an empty result rather than an exception.
        soup = soup.select_one(scope) or BeautifulSoup("", "html.parser")
    output: dict[str, Any] = {}
    fields = recipe.get("fields", {})
    if len(fields) > 30:
        raise InvalidRecipe("Maximum 30 fields per recipe")
    for name, spec in fields.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("selector"), str):
            raise InvalidRecipe(f"Field {name!r} requires a CSS selector")
        nodes = soup.select(spec["selector"])[: min(100, max(1, int(spec.get("max_items", 20))))]
        values: list[str] = []
        for node in nodes:
            value = node.get(spec["attribute"], "") if spec.get("attribute") else node.get_text(" ", strip=True)
            value = " ".join(str(value).split())
            if spec.get("absolute_url") and value:
                value = urljoin(base_url, value)
            pattern = spec.get("pattern")
            if pattern:
                match = re.search(pattern, value)
                value = match.group(1) if match and match.lastindex else (match.group(0) if match else "")
            if value and value not in values:
                values.append(value[:1000])
        output[name] = values if spec.get("all", False) else (values[0] if values else None)
    return output


def compact_text(text: str, query: str = "", max_chars: int = 2500) -> str:
    """Remove whitespace noise and prioritize lines matching the retrieval query."""
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line and len(line) > 2]
    # Keep order, drop repeated navigation/footers and repeated extracted boilerplate.
    unique = list(dict.fromkeys(lines))
    if query:
        terms = {word.lower() for word in re.findall(r"[\w\-]{3,}", query)}
        ranked = sorted(enumerate(unique), key=lambda pair: (-sum(t in pair[1].lower() for t in terms), pair[0]))
        # Preserve meaningful local context by giving matching lines priority.
        if any(sum(t in value.lower() for t in terms) for _, value in ranked):
            unique = [value for _, value in ranked]
    return "\n".join(unique)[:max(0, max_chars)]


def approx_tokens(text: str) -> int:
    # Fast approximation rather than a model-specific tokenizer (~4 characters/token).
    return (len(text) + 3) // 4
