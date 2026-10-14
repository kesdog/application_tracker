"""Configuration for an embedded, asynchronous web toolbox."""

from dataclasses import dataclass, field
from pathlib import Path
import os


def _env_bool(name: str, default: bool = False) -> bool:
    # Do not interpret the string "false" as truthy.
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    # Consumers can override the cache location to put it under their app-data path.
    cache_path: Path = field(default_factory=lambda: Path(os.getenv("WT_CACHE_PATH", "~/.cache/webtoolbox/cache.sqlite3")).expanduser())
    search_provider: str = field(default_factory=lambda: os.getenv("WT_SEARCH_PROVIDER", "ddgs"))
    searxng_url: str = field(default_factory=lambda: os.getenv("WT_SEARXNG_URL", "http://localhost:8080"))
    request_timeout: float = 15.0
    search_ttl: int = 6 * 3600
    crawl_ttl: int = 24 * 3600
    max_search_results: int = 10
    max_crawl_pages: int = 3
    max_tokens: int = 1000
    concurrent_fetches: int = 2
    background_concurrency: int = 2
    max_pending_jobs: int = 100
    completed_job_history: int = 100
    domain_delay_seconds: float = 0.75
    allow_private_urls: bool = field(default_factory=lambda: _env_bool("WT_ALLOW_PRIVATE_URLS"))
    allowed_hosts: tuple[str, ...] = field(default_factory=lambda: tuple(x.strip().lower() for x in os.getenv("WT_ALLOWED_HOSTS", "").split(",") if x.strip()))
