"""One explicit human action: reconcile Gmail, then synchronize compact Drive records."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from threading import Event, RLock
import time
from uuid import uuid4
from urllib.parse import urlencode

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.google_connection import GoogleConnectionError
from app.mailbox_import import reconcile
from app.models import MailImportReceipt, utc_now


class ApplicationSync:
    def __init__(self, engine, settings, google, mail, drive):
        self.engine, self.settings, self.google, self.mail, self.drive = engine, settings, google, mail, drive
        self.lock, self.closed = RLock(), Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='application-sync')
        self.account = None
        self.value = {'id': None, 'state': 'IDLE', 'phase': None, 'checked': 0, 'created': 0, 'updated': 0,
                      'review_count': 0, 'gmail': 'NOT_RUN', 'drive': 'NOT_RUN', 'warnings': [], 'finished_at': None}

    def change(self, **changes):
        with self.lock:
            self.value.update(changes)

    def status(self):
        with self.lock:
            value, account = deepcopy(self.value), self.account
        value['reviews'] = []
        email = self.google.status().get('email')
        account = hashlib.sha256(email.casefold().encode()).hexdigest() if email else None
        if account:
            with Session(self.engine) as session:
                query = select(MailImportReceipt).where(MailImportReceipt.account == account, MailImportReceipt.state == 'REVIEW')
                value['review_count'] = session.scalar(select(func.count()).select_from(query.subquery())) or 0
                value['reviews'] = [{'message_id': row.message_id, 'subject': row.subject, 'reason': row.reason,
                    'url': 'https://mail.google.com/mail/?' + urlencode({'authuser': email}) + '#all/' + row.message_id}
                    for row in session.scalars(query.order_by(MailImportReceipt.message_at.desc()).limit(20))]
        return value

    def start(self):
        with self.lock:
            if self.value['state'] == 'RUNNING':
                return deepcopy(self.value)
            if self.closed.is_set():
                raise ValueError('The application is shutting down. Restart it before syncing.')
            self.value = {'id': str(uuid4()), 'state': 'RUNNING', 'phase': 'GMAIL', 'checked': 0, 'created': 0,
                'updated': 0, 'review_count': 0, 'gmail': 'NOT_RUN', 'drive': 'NOT_RUN', 'warnings': [], 'finished_at': None}
            self.executor.submit(self.run)
            return deepcopy(self.value)

    def close(self):
        self.closed.set()
        self.executor.shutdown(wait=True, cancel_futures=True)

    def warning(self, message):
        with self.lock:
            self.value['warnings'].append(message)

    def check_account(self, email):
        status = self.google.status()
        if status.get('email') != email or not status['capabilities'].get('gmail_read'):
            raise GoogleConnectionError('The Google account or Gmail permission changed. Reconnect and sync again.')

    def gmail(self):
        connection = self.google.status()
        email = connection.get('email')
        if not connection['capabilities'].get('gmail_read') or not email:
            self.change(gmail='SETUP_REQUIRED')
            self.warning('Connect Google with Gmail read permission in Settings to import application emails.')
            return
        self.account = hashlib.sha256(email.casefold().encode()).hexdigest()
        self.change(gmail='RUNNING')
        created, updated, revisit = set(), set(), set()
        token, seen_tokens = None, set()

        def process(message_id):
            self.check_account(email)
            message = self.mail.application_message(message_id)
            self.check_account(email)
            app_id, new, changed = reconcile(self.engine, self.settings, self.account, message, mailbox_email=email)
            if new:
                created.add(app_id)
            if changed:
                updated.add(app_id)
            self.change(created=len(created), updated=len(updated - created))

        while not self.closed.is_set():
            self.check_account(email)
            page = self.mail.application_messages(token)
            self.check_account(email)
            for message in page.get('messages', []):
                if self.closed.is_set():
                    return
                message_id = message['id']
                with Session(self.engine) as session:
                    receipt = session.get(MailImportReceipt, (self.account, message_id))
                    applied = receipt is not None and receipt.state != 'REVIEW'
                if not applied:
                    process(message_id)
                    revisit.add(message_id)
                with self.lock:
                    self.value['checked'] += 1
            token = page.get('nextPageToken')
            if not token:
                break
            if token in seen_tokens:
                raise GoogleConnectionError('Gmail pagination did not advance. Saved imports are retained; try again.')
            seen_tokens.add(token)
        # Gmail lists newest first: retry unmatched updates after older confirmations establish their thread/record.
        if created or updated:
            for message_id in revisit:
                if self.closed.is_set():
                    return
                with Session(self.engine) as session:
                    receipt = session.get(MailImportReceipt, (self.account, message_id))
                    review = receipt and receipt.state == 'REVIEW'
                if review:
                    process(message_id)
        self.change(gmail='COMPLETED')

    def run_drive(self):
        deadline = time.monotonic() + 120
        while True:
            result = self.drive.run(manual=True)
            if not result.get('running'):
                return result
            if self.closed.wait(1) or time.monotonic() > deadline:
                raise ValueError('Drive is busy')

    def run(self):
        try:
            # Learn existing records from other devices before importing confirmations.
            self.change(phase='DRIVE')
            try:
                ready = self.drive.status()
                if ready['initialized'] and not ready.get('recovery_required'):
                    preflight = self.run_drive()
                    if preflight.get('error'):
                        self.warning('Drive changes could not be loaded before Gmail import. Local records are preserved; check Settings.')
            except Exception:
                self.warning('Drive changes could not be loaded before Gmail import. Local records are preserved; check Settings.')
            self.change(phase='GMAIL')
            try:
                self.gmail()
            except Exception as exc:
                self.change(gmail='FAILED')
                self.warning(str(exc) if isinstance(exc, GoogleConnectionError) else 'Gmail import stopped. Completed changes are saved; try again.')
            if self.closed.is_set():
                return
            self.change(phase='DRIVE')
            try:
                drive = self.drive.status()
                if not drive['initialized'] or drive.get('recovery_required'):
                    self.change(drive='SETUP_REQUIRED')
                    self.warning('Set up or recover encrypted Drive sync in Settings to synchronize devices.')
                else:
                    drive = self.run_drive()
                    if drive.get('error'):
                        raise GoogleConnectionError(drive['error'])
                    self.change(drive='COMPLETED')
                    if drive.get('conflicts'):
                        self.warning(f"{drive['conflicts']} Drive record conflicts need review in Settings.")
            except Exception as exc:
                self.change(drive='FAILED')
                self.warning(str(exc) if isinstance(exc, GoogleConnectionError) else 'Drive sync could not finish. Local changes are saved; try again or check Settings.')
        finally:
            with self.lock:
                success = self.value['gmail'] == 'COMPLETED' and self.value['drive'] == 'COMPLETED'
            self.change(state='COMPLETED' if success else 'PARTIAL', phase=None, finished_at=utc_now().isoformat() + 'Z')
