"""Conservative role/employer evidence from confirmation message bodies.

The sender is never assumed to be the employer. A CV-forwarding message is
submission evidence, not an interview invitation or an employment offer.
"""
from dataclasses import asdict, dataclass
from datetime import datetime
import re
import unicodedata

from bs4 import BeautifulSoup

from app.confirmation_links import _decoded, extract_confirmation_link

UNDISCLOSED_EMPLOYER = "Employer not disclosed"


@dataclass(frozen=True)
class ConfirmationDetails:
    job_title: str | None
    company: str | None
    intermediary: str | None
    kind: str
    matched_text: str | None
    date_applied: str | None
    posting: dict
    reason: str

    def model_dump(self) -> dict:
        return asdict(self)


def extract_confirmation_details(content: str) -> ConfirmationDetails:
    posting = extract_confirmation_link(content).model_dump()
    soup = BeautifulSoup(_decoded(content), "html.parser")
    raw_text = soup.get_text(" ")
    text = re.sub(r"\s+", " ", "".join(c for c in raw_text if unicodedata.category(c) != "Cf")).strip()
    title = company = intermediary = matched = applied = None
    kind = "UNRECOGNIZED"
    reason = "No unambiguous role/employer confirmation pattern found; review the message body"
    # Preserve explicit application dates instead of substituting the import date.
    date_match = re.search(r"Applied on ([A-Za-z]+ \d{1,2}, \d{4})", text, re.I)
    if date_match:
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                applied = datetime.strptime(date_match[1], fmt).date().isoformat()
                break
            except ValueError:
                continue
    forwarding = re.search(r"votre CV a été envoyé à l[’']entreprise (.+?) qui recherche", text, re.I)
    if forwarding and re.search(r"\bISCOD\b", text, re.I):
        company = re.sub(r"\s*-\s*IT$", "", forwarding[1]).strip()
        intermediary, kind, matched = "ISCOD", "CV_FORWARDED", forwarding[0]
        reason = "ISCOD forwarded the CV to the named partner employer; no offer or interview is implied"
    else:
        patterns = (
            r"(?:thank(?:s| you)(?: very much)? for applying|thank you for your application) (?:for|to)(?: the (?:position|role) of)?\s+(.+?)\s+(?:at|with)\s+(.+?)(?:[.!](?=\s|Unfortunately|$)|$)",
            r"(?:merci (?:d['’]avoir postulé|pour votre candidature)|nous vous remercions (?:d['’]avoir postulé|pour votre candidature)) (?:pour|au)(?: (?:le )?poste(?: de)?)?\s+(.+?)\s+(?:chez|au sein de)\s+(.+?)(?:[.!](?=\s|Malheureusement|$)|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                title, company, matched, kind = match[1].strip(), match[2].strip(), match[0], "APPLICATION_CONFIRMATION"
                break
        # Indeed explicitly names the advertiser, which can be an intermediary.
        advertiser = re.search(r"(?:Les éléments suivants ont été envoyés à (.+?)\. Bonne chance|The following items were sent to (.+?)\. Good luck)", text, re.I)
        if advertiser:
            company = advertiser[1] or advertiser[2]
            match = re.search(r"(?:Candidature envoyée|Application submitted) (.+?)\s+" + re.escape(company) + r"\s+-\s+.+?\s+(?:Les éléments suivants|The following items)", text, re.I)
            if match:
                title, matched, kind = match[1].strip(), match[0], "APPLICATION_CONFIRMATION"
        linkedin_body = text.rsplit("Your application was sent to ", 1)[-1]
        linkedin = re.search(r"^(.+?)\s+(.+?)\s+\1\s*·", linkedin_body, re.I) if "Your application was sent to " in text else None
        if linkedin:
            company, title, matched, kind = linkedin[1].strip(), linkedin[2].strip(), linkedin[0], "APPLICATION_CONFIRMATION"
            # The employer's display name can differ from its full heading name.
            # Match the role anchor to the recovered job ID, ignoring suggestions.
            job_url = posting.get("job_url")
            job_id = re.search(r"/jobs/view/(\d+)", job_url or "")
            if job_id:
                labels = [a.get_text(" ", strip=True) for a in soup.find_all("a", href=True)
                          if re.search(r"/jobs/view/(?:[^/]*-)?" + job_id[1] + r"(?:/|[?#]|$)", str(a["href"]))]
                role_labels = [label for label in labels if label and "·" not in label]
                if role_labels:
                    title = min(role_labels, key=len)
                    heading = next((h.get_text(" ", strip=True) for h in soup.find_all(("h1", "h2"))
                                    if h.get_text(" ", strip=True).startswith("Your application was sent to ")), None)
                    if heading:
                        company = heading.removeprefix("Your application was sent to ").strip()
        if kind == "APPLICATION_CONFIRMATION":
            reason = "Role and employer extracted from the confirmation body, not the sender"
            if re.search(r"candidature n['’]a pas été retenue|unfortunately|not (?:been )?selected", text, re.I):
                kind = "APPLICATION_UPDATE"
                reason = "The body names a role/employer but contains an application update, not a new submission"
        if company and company.casefold() in {"iscod", "l'iscod", "l’iscod", "iscod, la formation en alternance"}:
            company, intermediary = None, "ISCOD"
            reason = "ISCOD is the intermediary; this confirmation does not disclose the partner employer"
    # Never accept a whole paragraph or template/footer as a role or company.
    if title and len(title) > 300:
        title = None
    if company and len(company) > 300:
        company = None
    if company and company.casefold() in {"notre entreprise", "our company", "l'entreprise", "l’entreprise"}:
        company = None
    return ConfirmationDetails(title, company, intermediary, kind, matched, applied, posting, reason)
