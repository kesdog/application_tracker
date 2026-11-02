"""One explicit human action: reconcile Gmail, then synchronize compact Drive records."""
from concurrent.futures import ThreadPoolExecutor
from calendar import monthrange
from copy import deepcopy
from datetime import datetime, timezone
from threading import Event, RLock
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.followup_templates import current_settings
from app.google_connection import GoogleConnectionError
from app.mailbox_evidence import account_key, mail_boundary_timestamp, mail_reference
from app.mailbox_scan import GmailScan
from app.models import MailImportReceipt, MailSyncBoundary, MailSyncScope, utc_now


class ApplicationSyncInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    lookback_months: int = Field(default=3, ge=1, le=120, strict=True)


def months_before(timestamp, months, timezone_name):
    """Calendar-month subtraction, clamped at month end, in workspace time."""
    local = datetime.fromtimestamp(timestamp, ZoneInfo(timezone_name))
    year, month = divmod(local.year * 12 + local.month - 1 - months, 12)
    month += 1
    return int(local.replace(year=year, month=month, day=min(local.day, monthrange(year, month)[1])).timestamp())


def _new_progress():
    return {'id': None, 'state': 'IDLE', 'phase': None, 'checked': 0, 'created': 0, 'updated': 0,
            'review_count': 0, 'gmail': 'NOT_RUN', 'drive': 'NOT_RUN', 'warnings': [], 'finished_at': None,
            'mail_limit': None, 'limit_reached': False}


class ApplicationSync:
    """Schedule the three sync stages and expose their thread-safe progress."""
    def __init__(self, engine, settings, google, mail, drive, *, clock=None):
        self.engine, self.settings, self.google, self.mail, self.drive = engine, settings, google, mail, drive
        self.lock, self.closed = RLock(), Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='application-sync')
        self.account = None
        self.run_email = None
        self.clock = clock or time.time
        self.value = _new_progress()

    def change(self, **changes):
        with self.lock:
            self.value.update(changes)

    def status(self):
        with self.lock:
            value = deepcopy(self.value)
        value['reviews'] = []
        value['gmail_checked_through'] = None
        value['gmail_scan_from'] = None
        value['initial_scan_required'] = False
        value['lookback_months'] = None
        connection = self.google.status()
        email = connection.get('email')
        value['gmail_account'] = email
        account = account_key(email) if email else None
        if account:
            with Session(self.engine) as session:
                boundary = session.get(MailSyncBoundary, account)
                scope = session.get(MailSyncScope, account)
                value['initial_scan_required'] = not boundary and not scope and bool(connection.get('capabilities', {}).get('gmail_read'))
                if scope:
                    value['gmail_scan_from'] = datetime.fromtimestamp(scope.scan_after, timezone.utc).isoformat().replace('+00:00', 'Z')
                    value['lookback_months'] = scope.lookback_months
                if boundary:
                    value['gmail_checked_through'] = datetime.fromtimestamp(boundary.checked_through, timezone.utc).isoformat().replace('+00:00', 'Z')
                query = select(MailImportReceipt).where(MailImportReceipt.account == account, MailImportReceipt.state == 'REVIEW')
                value['review_count'] = session.scalar(select(func.count()).select_from(query.subquery())) or 0
                value['reviews'] = [{'message_id': row.message_id, 'subject': row.subject, 'reason': row.reason,
                    'url': mail_reference(row.message_id, email)}
                    for row in session.scalars(query.order_by(MailImportReceipt.message_at.desc()).limit(20))]
        return value

    def start(self, lookback_months=3):
        with self.lock:
            if self.value['state'] == 'RUNNING':
                return deepcopy(self.value)
            if self.closed.is_set():
                raise ValueError('The application is shutting down. Restart it before syncing.')
            lookback_months = ApplicationSyncInput(lookback_months=lookback_months).lookback_months
            connection = self.google.status()
            self.run_email = connection.get('email') if connection['capabilities'].get('gmail_read') else None
            with Session(self.engine) as session:
                session.execute(text('BEGIN IMMEDIATE'))
                general = current_settings(session, self.settings)
                mail_limit = general['mail_sync_max_messages']
                if self.run_email:
                    account = account_key(self.run_email)
                    if session.get(MailSyncBoundary, account) is None and session.get(MailSyncScope, account) is None:
                        session.add(MailSyncScope(account=account, lookback_months=lookback_months,
                            scan_after=max(mail_boundary_timestamp(general),
                                           months_before(self.clock(), lookback_months, general['timezone']))))
                session.commit()
            self.value = {**_new_progress(), 'id': str(uuid4()), 'state': 'RUNNING',
                          'phase': 'GMAIL', 'mail_limit': mail_limit}
            self.executor.submit(self.run)
            return deepcopy(self.value)

    def close(self):
        self.closed.set()
        self.executor.shutdown(wait=True, cancel_futures=True)

    def warning(self, message):
        with self.lock:
            self.value['warnings'].append(message)

    def gmail(self):
        connection = self.google.status()
        email = connection.get('email')
        if not connection['capabilities'].get('gmail_read') or not email:
            self.change(gmail='SETUP_REQUIRED')
            self.warning('Connect Google with Gmail read permission in Settings to import application emails.')
            return
        if email != self.run_email:
            raise GoogleConnectionError('The Google account changed after this sync started. Start a new sync for the selected account.')
        self.account = account_key(email)
        scan = GmailScan(
            engine=self.engine, settings=self.settings, mail=self.mail, email=email,
            mail_limit=self.value['mail_limit'], closed=self.closed, clock=self.clock, progress=self.change,
            # Resolve live status each time; account changes must invalidate ongoing reads.
            connection_status=lambda: self.google.status(),
        )
        scan.run()

    def run_drive(self):
        deadline = time.monotonic() + 120
        while True:
            result = self.drive.run(manual=True)
            if not result.get('running'):
                return result
            if self.closed.wait(1) or time.monotonic() > deadline:
                raise ValueError('Drive is busy')

    def _pull_drive(self):
        # Load other devices' records first so a confirmation can match them.
        self.change(phase='DRIVE')
        try:
            ready = self.drive.status()
            if ready['initialized'] and not ready.get('recovery_required'):
                preflight = self.run_drive()
                if preflight.get('error'):
                    self.warning('Drive changes could not be loaded before Gmail import. Local records are preserved; check Settings.')
        except Exception:
            self.warning('Drive changes could not be loaded before Gmail import. Local records are preserved; check Settings.')

    def _import_gmail(self):
        self.change(phase='GMAIL')
        try:
            self.gmail()
        except Exception as exc:
            self.change(gmail='SETUP_REQUIRED' if isinstance(exc, GoogleConnectionError)
                        and exc.kind == 'setup_required' else 'FAILED')
            self.warning(str(exc) if isinstance(exc, GoogleConnectionError) else 'Gmail import stopped. Completed changes are saved; try again.')

    def _push_drive(self):
        self.change(phase='DRIVE')
        try:
            drive = self.drive.status()
            if not drive['initialized'] or drive.get('recovery_required'):
                self.change(drive='SETUP_REQUIRED')
                self.warning('Set up or recover encrypted Drive sync in Settings to synchronize devices.')
                return
            drive = self.run_drive()
            if drive.get('error'):
                raise GoogleConnectionError(drive['error'])
            self.change(drive='COMPLETED')
            if drive.get('conflicts'):
                self.warning(f"{drive['conflicts']} Drive record conflicts need review in Settings.")
        except Exception as exc:
            self.change(drive='FAILED')
            self.warning(str(exc) if isinstance(exc, GoogleConnectionError) else 'Drive sync could not finish. Local changes are saved; try again or check Settings.')

    def run(self):
        try:
            self._pull_drive()
            self._import_gmail()
            if self.closed.is_set():
                return
            # Publish already committed records even if a later Gmail read failed.
            self._push_drive()
        finally:
            with self.lock:
                success = self.value['gmail'] == 'COMPLETED' and self.value['drive'] == 'COMPLETED'
            self.change(state='COMPLETED' if success else 'PARTIAL', phase=None, finished_at=utc_now().isoformat() + 'Z')
