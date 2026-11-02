"""Human-triggered cross-client checks using disposable, empty encrypted batches.

No tracker records, workspace recovery keys or OAuth tokens cross this boundary.
The phone authorizes independently and must discover/decrypt each test object.
"""
import secrets
import threading
import time
from uuid import uuid4

from app.sync.crypto import encode_key, open_envelope, seal
from app.sync.schemas import Batch


class LiveSyncProbe:
    def __init__(self, transport, client_id, *, clock=time.monotonic, wait=time.sleep, retry_delays=(0.25, 0.5, 1, 2, 4, 8)):
        self.transport, self.client_id, self.clock = transport, client_id, clock
        self.wait, self.retry_delays = wait, tuple(retry_delays)
        self.pending, self.lock = {}, threading.RLock()

    def start(self, phone_client_id):
        desktop_client = self.client_id()
        if not desktop_client or desktop_client == phone_client_id:
            raise ValueError('Use separate desktop and phone Web OAuth clients in the same Google Cloud project.')
        subject = self.transport.identity()
        with self.lock:
            # Keep unfinished probe receipts so their exact test objects remain
            # eligible for authenticated cleanup. Never delete by filename alone.
            if len(self.pending) >= 4:
                raise ValueError('Finish or clean up the existing live probes before starting another.')
            workspace, key = str(uuid4()), secrets.token_bytes(32)
            batch = Batch(workspace_id=workspace, device_id=uuid4(), batch_id=uuid4(), kind='ack')
            file_id = self.transport.upload_immutable(str(batch.batch_id), seal(batch, key))
            reference, phone_batch_id = secrets.token_urlsafe(32), str(uuid4())
            self.pending[reference] = dict(workspace=workspace, key=key, subject=subject, desktop_client=desktop_client,
                phone_client=phone_client_id, phone_batch_id=phone_batch_id, batch_id=str(batch.batch_id), file_id=file_id, created=self.clock(), phone_files={}, cleanup_files={file_id: str(batch.batch_id)})
            return dict(probe_id=reference, workspace_id=workspace, test_key=encode_key(key), subject=subject,
                desktop_client_id=desktop_client, desktop_file_id=file_id, desktop_batch_id=str(batch.batch_id), phone_batch_id=phone_batch_id)

    def verify(self, reference, phone_file_id, phone_batch_id):
        with self.lock:
            probe = self.pending.get(reference)
            if not probe or self.clock() - probe['created'] > 600:
                raise ValueError('Live probe expired. Clean it up and start again.')
            if self.transport.identity() != probe['subject'] or self.client_id() != probe['desktop_client']:
                raise ValueError('The desktop Google connection changed during the live probe.')
            batch = open_envelope(self.transport.download(phone_file_id), probe['key'], probe['workspace'])
            if batch.kind != 'ack' or batch.mutations or str(batch.batch_id) != phone_batch_id or phone_batch_id != probe['phone_batch_id']:
                raise ValueError('The phone did not return the expected independent encrypted probe.')
            probe['phone_files'][phone_file_id] = phone_batch_id
            probe['cleanup_files'][phone_file_id] = phone_batch_id
            # Google can acknowledge the upload before listing/feed visibility.
            # Both evidence checks share a bounded read-only polling budget.
            delays = iter(self.retry_delays)
            def wait_until(check, message):
                while not check():
                    delay = next(delays, None)
                    if delay is None:
                        raise ValueError(message)
                    self.wait(delay)

            wait_until(lambda: phone_file_id in {item['id'] for item in self.transport.list_files()},
                'The desktop cannot discover the phone object.')
            cursor = probe.get('cursor')
            if cursor is None:
                raise ValueError('The desktop change-feed cursor was not recorded.')
            def observed_in_feed():
                # Always start before the upload, including after an empty page.
                next_cursor, observed, seen = cursor, set(), set()
                while True:
                    files, _, next_cursor, more = self.transport.changes(next_cursor)
                    observed.update(item['id'] for item in files)
                    if not more:
                        return phone_file_id in observed
                    if next_cursor in seen:
                        raise ValueError('Drive returned a repeated change page.')
                    seen.add(next_cursor)
            wait_until(observed_in_feed, 'The desktop change feed did not observe the phone object. Retry verification.')
            return {'verified': True, 'desktop_to_phone': True, 'phone_to_desktop': True,
                'phone_client_id': probe['phone_client'], 'desktop_client_id': probe['desktop_client']}

    def begin(self, phone_client_id):
        # The cursor must precede both writes; app-data listing alone is not proof
        # that catch-up through the changes feed works in each client.
        cursor = self.transport.start_cursor()
        value = self.start(phone_client_id)
        self.pending[value['probe_id']]['cursor'] = cursor
        return value

    def cleanup(self, reference):
        with self.lock:
            probe = self.pending.get(reference)
            if not probe:
                return {'cleaned': True}
            if self.transport.identity() != probe['subject']:
                raise ValueError('Reconnect the original Google account before cleaning up its probe.')
            # Reconcile a phone upload whose response was lost. A random batch
            # name is only a candidate; remove_probe authenticates its contents.
            for file in self.transport.list_files():
                if file.get('name') == 'tracker-sync-v1-' + probe['phone_batch_id']:
                    probe['cleanup_files'][file['id']] = probe['phone_batch_id']
            for file_id, batch_id in list(probe['cleanup_files'].items()):
                self.transport.remove_probe(file_id, probe['workspace'], probe['key'], batch_id)
                del probe['cleanup_files'][file_id]
            del self.pending[reference]
            return {'cleaned': True}
