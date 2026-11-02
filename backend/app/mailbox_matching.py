"""Match mailbox evidence from strongest identity to weakest textual evidence."""
import re
from typing import NamedTuple
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mailbox_evidence import MailEvidence
from app.models import Application, MailImportReceipt

GMAIL_REFERENCE = re.compile(r'(?:\[?Gmail:\s*|/#all/|#all/)([a-f0-9]+)', re.I)


class ApplicationMatch(NamedTuple):
    application: Application | None
    ambiguous: bool = False


def normalized(value):
    value = ''.join(' ' if unicodedata.category(char).startswith('P') else char for char in (value or ''))
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def canonical(value):
    parsed = urlsplit(value or '')
    query = [(key, value) for key, value in parse_qsl(parsed.query)
             if not key.lower().startswith('utm_') and key.lower() not in ('trk', 'trackingid')]
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip('/'), urlencode(sorted(query)), ''))


def _has_reference(app: Application, evidence: MailEvidence) -> bool:
    reference = app.email_reference or ''
    gmail_ids = [value.lower() for value in GMAIL_REFERENCE.findall(reference)]
    internet_id = evidence.headers.get('message-id', '')
    return evidence.message_id.lower() in gmail_ids or bool(internet_id and internet_id in reference.splitlines())


def _compatible_vacancy(app: Application, evidence: MailEvidence) -> bool:
    # Recruitment boards can group unrelated vacancies into one Gmail thread.
    return (not evidence.details.company or normalized(app.company) == normalized(evidence.details.company)) and (
        not evidence.details.job_title or normalized(app.job_title) == normalized(evidence.details.job_title))


def match_application(session: Session, account: str, evidence: MailEvidence, *, not_before=None) -> ApplicationMatch:
    query = select(Application)
    if not_before is not None:
        # Out-of-scope history must not block a new application for the same
        # employer/role. Tombstones inside the current scope still prevent revival.
        query = query.where(Application.date_applied >= not_before)
    records = list(session.scalars(query))
    candidates = [app for app in records if _has_reference(app, evidence)]
    if not candidates and evidence.thread_id:
        prior = set(session.scalars(select(MailImportReceipt.application_id).where(
            MailImportReceipt.account == account, MailImportReceipt.thread_id == evidence.thread_id,
            MailImportReceipt.application_id.is_not(None))))
        candidates = [app for app in records if app.id in prior and _compatible_vacancy(app, evidence)]
    if not candidates and evidence.posting.get('job_url'):
        posting = canonical(evidence.posting['job_url'])
        candidates = [app for app in records if app.job_url and canonical(app.job_url) == posting]
    if not candidates and evidence.details.company and evidence.details.job_title:
        candidates = [app for app in records if normalized(app.company) == normalized(evidence.details.company)
                      and normalized(app.job_title) == normalized(evidence.details.job_title)]
    if not candidates:
        text = ' ' + normalized(evidence.headers.get('subject', '') + ' ' + evidence.full_text) + ' '
        candidates = [app for app in records if (' ' + normalized(app.company) + ' ') in text
                      and (' ' + normalized(app.job_title) + ' ') in text]

    # A weaker match must never break a tie between stronger candidates.
    # Keep tombstones as matches so a later confirmation cannot recreate them.
    active = [app for app in candidates if not app.deleted_at]
    candidates = active or candidates
    if len(candidates) != 1:
        return ApplicationMatch(None, ambiguous=bool(candidates))
    return ApplicationMatch(candidates[0])
