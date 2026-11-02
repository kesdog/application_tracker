"""Named, provider-neutral evidence extracted once from a Gmail message."""
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from email.utils import parsedate_to_datetime
import hashlib
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from app.mail_scanners import ConfirmationDetails, ScanResult, scan_email

CONFIRMATION_KINDS = frozenset({'APPLICATION_CONFIRMATION', 'CV_FORWARDED'})


def mail_boundary_timestamp(general: dict) -> int:
    day = date.fromisoformat(general['mail_sync_not_before'])
    return int(datetime.combine(day, time.min, ZoneInfo(general['timezone'])).timestamp())


def account_key(email: str) -> str:
    return hashlib.sha256(email.casefold().encode()).hexdigest()


def mail_reference(message_id: str, email: str | None = None) -> str:
    if email:
        return 'https://mail.google.com/mail/?' + urlencode({'authuser': email}) + '#all/' + message_id
    return f'https://mail.google.com/mail/u/0/#all/{message_id}'


@dataclass(frozen=True)
class MailEvidence:
    message_id: str
    thread_id: str
    headers: dict[str, str]
    current_text: str
    full_text: str
    message_at: datetime | None
    scan: ScanResult

    @property
    def details(self) -> ConfirmationDetails:
        return self.scan.details

    @property
    def posting(self) -> dict:
        return self.scan.details.posting

    @property
    def is_confirmation(self) -> bool:
        return self.details.kind in CONFIRMATION_KINDS

    @property
    def actionable(self) -> bool:
        return bool(self.scan.decision or self.is_confirmation)

    @property
    def applied_on(self) -> str | date | None:
        if self.details.date_applied:
            return self.details.date_applied
        if self.message_at is None:
            return None
        # Preserve the sender's calendar date even when UTC falls on another day.
        try:
            return parsedate_to_datetime(self.headers.get('date', '')).date()
        except (ValueError, TypeError, OverflowError):
            return self.message_at.date()


def message_date(headers: dict, internal_date) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(headers.get('date', ''))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        pass
    # Gmail's delivery time is a fallback; missing dates must never become "now".
    try:
        return datetime.fromtimestamp(int(internal_date) / 1000, timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def read_evidence(message: dict) -> MailEvidence:
    headers = {item['name'].lower(): item['value'] for item in message.get('headers', [])}
    soup = BeautifulSoup(message.get('content', '')[:120000], 'html.parser')
    full_text = soup.get_text(' ', strip=True)
    for quoted in soup.select('blockquote, .gmail_quote, .gmail_extra, .yahoo_quoted, script, style'):
        quoted.decompose()
    current_text = soup.get_text('\n', strip=True)
    current_text = re.split(r'(?im)^\s*(?:On .+ wrote:|Le .+ écrit\s*:|From:|De\s*:|>).*$', current_text, maxsplit=1)[0]
    # History may identify an application, but only current text can change status.
    scan = scan_email(str(soup) or 'Unrecognized email', headers=headers, text=current_text)
    return MailEvidence(
        message_id=message['id'], thread_id=message.get('thread_id', ''), headers=headers,
        current_text=current_text, full_text=full_text,
        message_at=message_date(headers, message.get('internal_date')), scan=scan,
    )
