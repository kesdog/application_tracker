"""Host-owned discovery job adapter: no contact approval or automatic sending."""

from pathlib import Path
from webtoolbox import WebToolbox, Settings


def make_toolbox(data_dir: Path) -> WebToolbox:
    # A single instance should be injected into the application's lifespan.
    return WebToolbox(Settings(
        cache_path=data_dir / "webtoolbox.sqlite3",
        concurrent_fetches=5,
        per_host_concurrency=1,
        background_concurrency=5,
        max_search_attempts=6,
        search_deadline_seconds=45,
    ))


def discover_from_posting(web: WebToolbox, url: str, *, on_result=None, on_progress=None):
    """Discover only published data; the tracker must persist and approve candidates."""
    # These callbacks run in-process and may be asynchronous.
    return web.submit_crawl(url, contacts=True, structured=True, mode="auto",
                            max_tokens=5500, on_result=on_result, on_progress=on_progress,
                            deadline_seconds=45)


def discover_by_employer(web: WebToolbox, employer: str, *, domain: str | None = None, on_result=None):
    """Fallback discovery when a job posting does not contain contact details."""
    # The generic toolbox only handles evidence; application DB owns durable job IDs.
    return web.submit_research_contacts(employer, official_domain=domain,
                       on_result=on_result, deadline_seconds=50)


async def candidates_after_completion(job) -> list[dict]:
    # Sending follow-ups remains an explicit human action in Application Tracker.
    response = await job.result()
    # Retain named people who have no published address; they can be researched later.
    return response.get("candidates", [])
