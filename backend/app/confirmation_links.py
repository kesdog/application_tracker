"""Extract canonical job-board links from application confirmation emails."""
from dataclasses import asdict, dataclass
from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

from app.job_sources import infer_job_source

@dataclass(frozen=True)
class ConfirmationLink:
    job_url: str | None
    source: str | None
    confirmation_url: str | None
    reason: str

    def model_dump(self) -> dict:
        return asdict(self)


def _decoded(content: str) -> str:
    # Do not run a full quoted-printable decode: an Indeed job key can begin
    # with e.g. ``=52`` and would be corrupted as if it were mail encoding.
    content = re.sub(r"=\r?\n", "", content)
    content = re.sub(r"=3d", "=", content, flags=re.IGNORECASE)
    content = re.sub(r"=26", "&", content, flags=re.IGNORECASE)
    return unescape(content)


def _urls(content: str) -> list[str]:
    values: list[str] = []
    for raw in re.findall(r"(?i)(?:https?://)?(?:[a-z0-9-]+\.)*(?:linkedin\.com|indeed\.(?:com|fr|co\.uk|de))[^\s\"'<>]*", _decoded(content)):
        value = raw.rstrip(".,;:!?)]}")
        values.append(value if value.startswith(("http://", "https://")) else f"https://{value}")
    return values


def extract_confirmation_link(content: str) -> ConfirmationLink:
    """Return the first direct job posting in a confirmation message, if present.

    LinkedIn confirmation links are canonicalized by job ID. Indeed's company
    confirmation link is returned separately because it cannot prove a specific
    vacancy is live.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("confirmation_email must contain the confirmation email text or HTML")

    company_confirmation: str | None = None
    for value in _urls(content):
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")
        source = infer_job_source(value)
        if source == "LINKEDIN":
            match = re.search(r"/(?:comm/)?jobs/view/(\d+)(?:/|$)", path, re.IGNORECASE)
            if match:
                return ConfirmationLink(
                    job_url=f"https://www.linkedin.com/jobs/view/{match.group(1)}/",
                    source="LINKEDIN",
                    confirmation_url=value,
                    reason="Found a LinkedIn job posting link in the confirmation email",
                )
        if source == "INDEED":
            query = parse_qs(parsed.query)
            job_key = (query.get("jk") or [None])[0]
            if path.endswith("/viewjob") and job_key:
                return ConfirmationLink(
                    job_url=f"https://{host}/viewjob?jk={job_key}",
                    source="INDEED",
                    confirmation_url=value,
                    reason="Found an Indeed job posting link in the confirmation email",
                )
            if "/pagead/clk" in path and job_key:
                return ConfirmationLink(
                    job_url=f"https://{host}/viewjob?jk={job_key}",
                    source="INDEED",
                    confirmation_url=value,
                    reason="Recovered an Indeed job key from a confirmation tracking link",
                )
            if "/cmp/" in path and company_confirmation is None:
                company_confirmation = value

    if company_confirmation:
        return ConfirmationLink(
            job_url=None,
            source="INDEED",
            confirmation_url=company_confirmation,
            reason="Found an Indeed company confirmation link but no direct job posting link",
        )
    return ConfirmationLink(None, None, None, "No LinkedIn or Indeed job posting link found in the confirmation email")
