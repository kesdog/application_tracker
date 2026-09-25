"""Recognize known job boards from a posting URL's hostname."""
from urllib.parse import urlsplit


JOB_BOARD_DOMAINS = {
    "INDEED": ("indeed.com", "indeed.fr", "indeed.co.uk", "indeed.de"),
    "LINKEDIN": ("linkedin.com",),
    "FREEWORK": ("free-work.com",),
    "HELLOWORK": ("hellowork.com",),
}


def infer_job_source(job_url: str | None) -> str:
    if not job_url:
        return "OTHER"
    parsed = urlsplit(job_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "OTHER"
    hostname = parsed.hostname.lower().rstrip(".")
    for source, domains in JOB_BOARD_DOMAINS.items():
        if any(hostname == domain or hostname.endswith(f".{domain}") for domain in domains):
            return source
    return "OTHER"
