"""Search backends are interchangeable; crawling itself never needs an API key."""

from __future__ import annotations

import asyncio
from typing import Any
import httpx


async def ddgs_search(query: str, limit: int) -> list[dict[str, str]]:
    """Keyless search; upstream engines may throttle or challenge requests."""
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError("Install the search extra: pip install -e '.[search]'") from exc

    def _sync() -> list[dict[str, str]]:
        # DDGS is synchronous; isolate it from the event loop.
        with DDGS(timeout=15) as searcher:
            return list(searcher.text(query, max_results=limit))

    raw = await asyncio.to_thread(_sync)
    return [{"title": str(x.get("title", "")), "url": str(x.get("href", "")), "snippet": str(x.get("body", ""))} for x in raw]


async def searxng_search(query: str, limit: int, base_url: str, client: httpx.AsyncClient) -> list[dict[str, str]]:
    """Search a specifically configured SearXNG server (JSON must be enabled)."""
    # This is a trusted operator-configured URL, not an arbitrary MCP argument.
    response = await client.get(f"{base_url.rstrip('/')}/search", params={"q": query, "format": "json"}, timeout=20)
    response.raise_for_status()
    data: dict[str, Any] = response.json()
    return [{"title": str(x.get("title", "")), "url": str(x.get("url", "")), "snippet": str(x.get("content", ""))} for x in data.get("results", [])[:limit]]
