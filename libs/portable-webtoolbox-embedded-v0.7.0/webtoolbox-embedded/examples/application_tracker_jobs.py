"""Application Tracker integration sketch: in-process and database-agnostic."""

from pathlib import Path
from webtoolbox import Settings, WebToolbox


async def check_applied_posting(posting_url: str, save_status):
    """Persist one observation through an application-owned async callback."""
    async with WebToolbox(Settings(cache_path=Path("data/web-cache.sqlite3"))) as toolbox:
        # Refresh is explicit when the application wants a new observation.
        job = toolbox.submit_check_job_status(posting_url, refresh=True, on_result=save_status)
        return await job.result()


async def find_application_link(company: str, role: str, location: str):
    """Find options without selecting/sending applications on behalf of the user."""
    async with WebToolbox(Settings(cache_path=Path("data/web-cache.sqlite3"))) as toolbox:
        # Match role and region, retaining alternatives for review.
        return await toolbox.discover_job(company, role, location=location, pages=3)
