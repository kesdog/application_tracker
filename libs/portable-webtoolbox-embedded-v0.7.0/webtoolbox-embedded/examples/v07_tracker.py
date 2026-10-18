"""One async discovery operation to call from the host's durable worker queue."""
from pathlib import Path
from webtoolbox import Settings, WebToolbox, EmployerContext


async def find_original_posting(worker_web: WebToolbox, application: dict) -> dict:
    # The caller owns the WebToolbox lifetime and its durable job IDs.
    verified = application.get("verified_employer_domain")
    context = (EmployerContext(company=application["company"], domain=verified,
                status="confirmed", evidence_source="application_confirmation") if verified else None)

    # The requested title and contract remain unchanged during final matching.
    return await worker_web.discover_job(
        company=application["company"],
        title=application["title"],
        search_title=application.get("short_search_title"),
        location=application.get("location") or "",
        contract_type=application.get("contract_type") or "",
        reference=application.get("posting_reference") or "",
        seed_urls=tuple(filter(None, [application.get("original_job_url")])),
        employer_context=context,
        keyword_profile=Path("config/jobs.json"),
        keyword_mode="rank", pages=6, max_tokens=7000,
    )


async def app_lifespan_example():
    # Use the host application's existing shutdown routine to close this instance.
    async with WebToolbox(Settings(max_job_discovery_pages=6)) as worker_web:
        result = await find_original_posting(worker_web, {
            "company": "Example Corp", "title": "Développeur C# en alternance",
            "short_search_title": "Développeur C#", "location": "Paris",
            "contract_type": "alternance", "original_job_url": None,
        })
        return result
