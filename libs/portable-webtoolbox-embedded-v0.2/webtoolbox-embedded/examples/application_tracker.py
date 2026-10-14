"""Application Tracker adapter: map extracted evidence into unapproved candidates."""

from webtoolbox import WebToolbox

# Keep application-specific fields here, not in the generic crawler package.
CONTACT_RECIPE = {
    "fields": {
        "emails": {
            "selector": "a[href^='mailto:']",
            "attribute": "href",
            "pattern": r"^mailto:([^?]+)",
            "all": True,
        },
        "contact_links": {
            "selector": "a[href*='contact'], a[href*='team']",
            "attribute": "href",
            "absolute_url": True,
            "all": True,
            "max_items": 10,
        },
    }
}


def discover_in_background(web: WebToolbox, posting_url: str) -> str:
    """Called from the tracker application's existing job workflow."""
    # Submits work on the host app's asyncio loop, without a separate process.
    handle = web.submit_crawl(posting_url, recipe=CONTACT_RECIPE, max_tokens=600)
    # Persist this ID in a host table only if you also have a restart/retry strategy.
    return handle.id


async def collect_candidates(web: WebToolbox, job_id: str) -> list[dict[str, str]]:
    """Use source-backed discoveries, but never accept or email them automatically."""
    job = web.job(job_id)
    if job is None:
        raise LookupError("Unknown or expired in-memory discovery job")
    result = await job.result()
    return [
        {"contact_method": "email", "value": address, "source_url": result["url"], "status": "candidate"}
        for address in result["fields"].get("emails", [])
    ]
