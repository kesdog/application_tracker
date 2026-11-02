"""One bounded Gmail scan, independent of job scheduling and Drive synchronization."""
from typing import NamedTuple

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.google_connection import GoogleConnectionError
from app.followup_templates import current_settings
from app.mailbox_evidence import MailEvidence, account_key, mail_boundary_timestamp, read_evidence
from app.mailbox_import import reconcile_evidence
from app.models import MailImportReceipt, MailSyncBoundary, MailSyncScope, utc_now

READ_ATTEMPTS = 4
MAX_RETRY_DELAY = 60
CHECKPOINT_OVERLAP = 300


class ScanWindow(NamedTuple):
    after: int | None
    before: int


class GmailScan:
    def __init__(self, *, engine, settings, mail, connection_status, email, mail_limit, closed, clock, progress):
        self.engine, self.settings, self.mail = engine, settings, mail
        self.connection_status, self.email = connection_status, email
        self.account = account_key(email)
        self.mail_limit, self.closed, self.clock, self.progress = mail_limit, closed, clock, progress
        self.checked = 0
        self.created_ids: set[str] = set()
        self.updated_ids: set[str] = set()
        self.pending_matches: dict[str, MailEvidence] = {}

    def check_account(self):
        connection = self.connection_status()
        if connection.get('email') != self.email or not connection['capabilities'].get('gmail_read'):
            raise GoogleConnectionError('The Google account or Gmail permission changed. Reconnect and sync again.')

    def read(self, operation, *args, **kwargs):
        # Retry only provider reads. A database or mailbox write must never be
        # blindly repeated after an uncertain result.
        for attempt in range(READ_ATTEMPTS):
            self.check_account()
            try:
                result = operation(*args, **kwargs)
            except GoogleConnectionError as exc:
                if exc.kind != 'rate_limit' or attempt == READ_ATTEMPTS - 1:
                    raise
                delay = exc.retry_after if exc.retry_after is not None else 5 * 2 ** attempt
                if delay > MAX_RETRY_DELAY:
                    raise
                if self.closed.wait(max(1, delay)):
                    raise GoogleConnectionError('Gmail import stopped. Completed changes are saved.', kind='unavailable') from None
            else:
                self.check_account()
                return result

    def load_window(self) -> ScanWindow:
        with Session(self.engine) as session:
            boundary = session.get(MailSyncBoundary, self.account)
            checked_through = boundary.checked_through if boundary else None
            scope = session.get(MailSyncScope, self.account)
            # Apply the absolute boundary to legacy accounts too. Gmail's after
            # operator is exclusive, so include the boundary's first second.
            floor = mail_boundary_timestamp(current_settings(session, self.settings))
            initial_after = max(scope.scan_after if scope else 0, floor)
        # Freeze the upper cutoff once. The overlap tolerates indexing delays;
        # receipts prevent repeat writes and the initial lower bound stays fixed.
        before = max(int(self.clock()), checked_through or 0)
        after = max(initial_after or 0, checked_through - CHECKPOINT_OVERLAP) if checked_through is not None else initial_after
        if after == floor:
            after -= 1
        return ScanWindow(after, before)

    def receipt_state(self, message_id: str) -> str | None:
        with Session(self.engine) as session:
            return session.scalar(select(MailImportReceipt.state).where(
                MailImportReceipt.account == self.account, MailImportReceipt.message_id == message_id))

    def process(self, message_id: str, evidence: MailEvidence | None = None):
        self.check_account()
        if evidence is None:
            evidence = read_evidence(self.read(self.mail.application_message, message_id))
        self.check_account()
        result = reconcile_evidence(self.engine, self.settings, self.account, evidence, mailbox_email=self.email)
        if result.application_id is not None:
            if result.created:
                self.created_ids.add(result.application_id)
            if result.changed:
                self.updated_ids.add(result.application_id)
        # An application created and then updated in this run counts only as new.
        self.progress(created=len(self.created_ids), updated=len(self.updated_ids - self.created_ids))
        if result.application_id is None and evidence.actionable:
            self.pending_matches.setdefault(message_id, evidence)

    def scan_pages(self, window: ScanWindow) -> bool:
        """Return true only when the limit leaves an actual unprocessed message."""
        token, seen_tokens = None, set()
        while not self.closed.is_set():
            page = self.read(self.mail.application_messages, token, after=window.after, before=window.before)
            for message in page.get('messages', []):
                if self.closed.is_set():
                    return False
                message_id = message['id']
                if self.receipt_state(message_id) is not None:
                    continue
                # Checking for another message first lets an exact-size final
                # batch complete rather than reporting an unnecessary cap.
                if self.checked >= self.mail_limit:
                    return True
                self.process(message_id)
                self.checked += 1
                self.progress(checked=self.checked)
            token = page.get('nextPageToken')
            if not token:
                return False
            if token in seen_tokens:
                raise GoogleConnectionError('Gmail pagination did not advance. Saved imports are retained; try again.')
            seen_tokens.add(token)
        return False

    def rematch_pending(self):
        if not (self.created_ids or self.updated_ids):
            return
        # A later confirmation may identify an earlier reply. Reuse parsed
        # evidence from this run; neither Gmail reads nor the allowance repeat.
        for message_id, evidence in tuple(self.pending_matches.items()):
            if self.closed.is_set():
                return
            if self.receipt_state(message_id) == 'REVIEW':
                self.process(message_id, evidence)

    def save_checkpoint(self, before: int):
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            boundary = session.get(MailSyncBoundary, self.account)
            if boundary is None:
                boundary = MailSyncBoundary(account=self.account, checked_through=before)
            else:
                boundary.checked_through = max(boundary.checked_through, before)
            boundary.updated_at = utc_now()
            session.add(boundary)
            session.commit()

    def run(self):
        window = self.load_window()
        self.progress(gmail='RUNNING')
        capped = self.scan_pages(window)
        self.rematch_pending()
        if self.closed.is_set():
            return
        self.check_account()
        if capped:
            # Saved receipts survive the cap, but advancing the checkpoint here
            # would skip the unfinished part of the scan on its next run.
            self.progress(gmail='LIMIT_REACHED', limit_reached=True)
            return
        self.save_checkpoint(window.before)
        self.progress(gmail='COMPLETED')
