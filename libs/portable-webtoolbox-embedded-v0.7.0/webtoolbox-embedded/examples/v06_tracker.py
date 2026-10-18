"""Application Tracker adapter example; not durable queue or email-sending code."""
from pathlib import Path

from webtoolbox import EmployerContext, Settings, WebToolbox


async def inspect_vacancy() -> dict:
    # The host app should keep one shared WebToolbox instance during its lifespan.
    settings = Settings(
        cache_path=Path("data/webtoolbox-cache.sqlite3"),
        keyword_profile=Path("libs/webtoolbox/profiles/alternance_it.example.json"),
    )

    # Accept confirmed status only after obtaining real application or user evidence.
    # A domain substring match by itself must not confirm an employer's identity.
    employer = EmployerContext(
        company="Atos",
        domain="atos.net",
        status="confirmed",
        evidence_source="user_confirmed",
        aliases=("Atos SE",),
        ats_domains=(),  # Add a specific ATS host only if it is linked to this employer.
    )

    async with WebToolbox(settings) as web:
        # Results are evidence-backed leads, not a permission to send outreach.
        leads = await web.research_contacts(
            employer.company,
            employer_context=employer,
            role="alternance développeur",
            target_region="France",
            pages=3,
            max_tokens=10000,
        )

        # The checker never treats authentication blocks as proof of closure.
        status = await web.check_job_status(
            "https://example.org/jobs/example12345", max_tokens=1400,
        )
        return {"leads": leads, "posting_status": status}
