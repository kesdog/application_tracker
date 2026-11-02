"""Offline provider registry, independent of UI language and storage."""
from app.mail_scanners.models import ConfirmationDetails, ScanResult, UNDISCLOSED_EMPLOYER
from app.mail_scanners.providers import MailContent, LinkedInScanner, IndeedScanner, FreeWorkScanner, GenericScanner

SCANNERS = (LinkedInScanner(), IndeedScanner(), FreeWorkScanner())
FALLBACK = GenericScanner()


def scan_email(content, *, headers=None, text=None):
    message = MailContent.parse(content, headers, text)
    for scanner in SCANNERS:
        if scanner.matches(message):
            result = scanner.scan(message)
            if result.details.kind != 'UNRECOGNIZED':
                return result
            generic = FALLBACK.scan(message)
            return generic if generic.details.kind != 'UNRECOGNIZED' else result
    return FALLBACK.scan(message)
