"""Stable extraction interface shared by agent tools and mailbox scanners."""
from app.mail_scanners import ConfirmationDetails, UNDISCLOSED_EMPLOYER, scan_email


def extract_confirmation_details(content: str) -> ConfirmationDetails:
    return scan_email(content).details
