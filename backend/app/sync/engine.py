"""Durable encrypted synchronization with an injected immutable-object transport."""
import hashlib
import hmac
import secrets
import threading
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import delete, func, insert, select, text, tuple_
from sqlalchemy.orm import Session, load_only

from app.models import Application, FollowUp, Interview, Task, utc_now
from app.sync.crypto import canonical, decode_key, encode_key, open_envelope, pairing_export, seal
from app.sync.domain import DomainBlocked, materialize
from app.sync.journal import DOMAIN, append_local, json_value, projection, record_key
from app.sync.merge import merge_events
from app.sync.models import (SyncBatch, SyncCheckpoint, SyncConflict, SyncDevice, SyncDirty, SyncInbox,
                             SyncMutation, SyncOutbox, SyncRecord, SyncWorkspace)
from app.sync.schemas import Batch, STATES
from app.sync.queue import chunks, mark_dirty
from app.sync.checkpoints import checkpoint_batches


class SyncError(ValueError):
    pass


class SyncEngine:
    """Storage and transport adapters stay outside protocol/authorization logic."""
    def __init__(self, engine, transport, secrets_store):
        self.engine, self.transport, self.secrets = engine, transport, secrets_store
        self.lock = threading.Lock()

    def status(self):
        with Session(self.engine) as session:
            workspace = session.get(SyncWorkspace, 1)
            if workspace is None:
                return {'initialized': False, 'pending_uploads': 0, 'pending_downloads': 0, 'conflicts': 0}
            count = lambda cls, *where: session.scalar(select(func.count()).select_from(cls).where(*where)) or 0
            return {'initialized': True, 'workspace_id': workspace.workspace_id, 'device_id': workspace.device_id,
                'label': workspace.label, 'last_success': json_value(workspace.last_success), 'error': workspace.last_error,
                'retry_at': json_value(workspace.retry_at), 'recovery_required': workspace.restored or not workspace.secret_reference,
                'running': self.lock.locked(),
                'pending_uploads': count(SyncOutbox, SyncOutbox.uploaded.is_(False)),
                'pending_downloads': count(SyncMutation, SyncMutation.applied.is_(False)),
                'conflicts': len({item.record_key for item in session.scalars(select(SyncConflict).where(SyncConflict.resolved.is_(False)))}),
                'remote_bytes': workspace.remote_bytes, 'remote_objects': workspace.remote_objects,
                'devices': [{'device_id': item.device_id, 'last_seen': json_value(item.last_seen),
                             'acknowledgments': item.acknowledgments} for item in session.scalars(select(SyncDevice))],
                'garbage_collection': 'disabled', 'overall_google_quota': None,
                'warnings': (['Compact sync exceeds 50 MB'] if workspace.remote_bytes > 50_000_000 else [])
                    + (['Drive object count exceeds 2,000'] if workspace.remote_objects > 2000 else [])}

    def initialize(self, label, recovery=None):
        subject = self.transport.identity()
        with self.lock, Session(self.engine) as session:
            session.info['sync_import'] = True
            existing = session.get(SyncWorkspace, 1)
            if existing and not existing.restored:
                raise SyncError('This workspace is already enrolled')
            if recovery:
                try:
                    version, workspace_id, encoded, binding = recovery.strip().split('.')
                    from uuid import UUID
                    UUID(workspace_id)
                    key = decode_key(encoded)
                    if version != 'ats1':
                        raise ValueError
                except ValueError:
                    raise SyncError('Invalid recovery export') from None
                if not hmac.compare_digest(pairing_export(workspace_id, key, subject), recovery.strip()):
                    raise SyncError('Recovery key or Google account does not match the paired workspace')
            else:
                if existing:
                    raise SyncError('Restore requires the original recovery export')
                workspace_id, key = str(uuid4()), secrets.token_bytes(32)
            if existing and (existing.workspace_id != workspace_id or existing.subject != subject):
                raise SyncError('Recovery workspace or Google account does not match')
            if recovery and not existing and any(session.scalar(select(func.count()).select_from(cls)) for cls in DOMAIN):
                raise SyncError('Pair into an empty workspace; keep a portable backup of existing local records')
            # Prove the recovery key/account against an existing authenticated
            # object before storing enrollment or touching any local domain row.
            if recovery:
                found = False
                for item in self.transport.list_files():
                    value = self.transport.download(item['id'])
                    # Multiple unrelated encrypted workspaces may share app data.
                    import json
                    if json.loads(value).get('header', {}).get('workspace_id') != workspace_id:
                        continue
                    batch = open_envelope(value, key, workspace_id)
                    if batch.kind in {'checkpoint', 'events'}:
                        found = True
                        break
                if not found:
                    raise SyncError('No authenticated sync state was found for recovery')
            session.rollback()
            session.execute(text('BEGIN IMMEDIATE'))
            current = session.get(SyncWorkspace, 1)
            if current and not current.restored:
                raise SyncError('This workspace was enrolled by another request')
            existing = current
            if recovery and existing is None and any(session.scalar(select(func.count()).select_from(cls)) for cls in DOMAIN):
                raise SyncError('Pair into an empty workspace; local records changed during enrollment')
            reference = 'sync-' + str(uuid4())
            self.secrets.put(reference, {'key': encode_key(key)})
            workspace = existing or SyncWorkspace(id=1, workspace_id=workspace_id, device_id=str(uuid4()),
                label=label, subject=subject, next_seq=1, failures=0, remote_bytes=0, remote_objects=0, restored=False)
            old_ref = workspace.secret_reference
            workspace.secret_reference, workspace.restored, workspace.label = reference, False, label
            session.add(workspace)
            try:
                session.flush()
                if not recovery:
                    for cls, entity in DOMAIN.items():
                        fields = [getattr(cls, name) for name in STATES[entity].model_fields if name != 'deleted']
                        if entity == 'application':
                            fields.append(cls.deleted_at)
                        queued = []
                        # Do not load private descriptions/message bodies just to
                        # construct their compact allowlisted projection.
                        with session.no_autoflush:
                            for item in session.scalars(select(cls).options(load_only(cls.id, *fields)).execution_options(yield_per=200)):
                                append_local(session, workspace, entity, item.id, projection(item), enqueue=False)
                                queued.append(record_key(entity, item.id))
                                if len(queued) == 200:
                                    mark_dirty(session, queued)
                                    session.flush()
                                    queued = []
                            mark_dirty(session, queued)
                            session.flush()
                session.commit()
            except Exception:
                self.secrets.delete(reference)
                raise
            if old_ref:
                self.secrets.delete(old_ref)
        # Return the newly generated recovery secret once, only from the explicit
        # local-human initialize action. Never include it in status or errors.
        return {'workspace_id': workspace_id, 'recovery_export': pairing_export(workspace_id, key, subject)}

    def _key(self, workspace):
        if workspace.restored or not workspace.secret_reference:
            raise SyncError('Re-enroll this restored device using its recovery export')
        value = self.secrets.get(workspace.secret_reference)
        if not value:
            raise SyncError('Sync key is unavailable. Unlock the native credential store')
        return decode_key(value['key'])

    def _vectors(self, session):
        vectors = {}
        rows = session.execute(select(SyncMutation.device_id, SyncMutation.device_seq)
            .where(SyncMutation.applied.is_(True)).order_by(SyncMutation.device_id, SyncMutation.device_seq)
            .execution_options(yield_per=1000))
        for device_id, sequence in rows:
            if sequence == vectors.get(device_id, 0) + 1:
                vectors[device_id] = sequence
        return vectors

    def _apply(self, session, *, revisit=True):
        session.flush()
        queued = list(session.scalars(select(SyncDirty.key)))
        keys = {tuple(key.split(':', 1)) for key in queued}
        if not keys:
            return
        # A newly available/changed application or follow-up sequence can unblock
        # children staged earlier. Inspect only pending roots for those parents.
        parents = {entity_id for entity, entity_id in keys if entity == 'application'}
        parent_value = func.json_extract(SyncMutation.payload, '$.changes.application_id')
        for group in chunks(list(keys)):
            parents.update(value for value in session.scalars(select(parent_value).where(
                tuple_(SyncMutation.entity, SyncMutation.entity_id).in_(group), parent_value.is_not(None)).distinct()))
        for group in chunks(list(parents)):
            keys.update(session.execute(select(SyncMutation.entity, SyncMutation.entity_id).where(
                SyncMutation.applied.is_(False), parent_value.in_(group)).distinct()).all())
        keys = sorted(keys, key=lambda item: (item[0] != 'application', item))
        changed_parents = set()
        # Revisit children after parents are materialized, without network replay.
        for entity, entity_id in keys:
            rows = list(session.scalars(select(SyncMutation).where(SyncMutation.entity == entity, SyncMutation.entity_id == entity_id)))
            result = merge_events([row.payload for row in rows])
            key = record_key(entity, entity_id)
            record = session.get(SyncRecord, key)
            if record is None:
                record = SyncRecord(key=key, heads=[], applied_heads=[], state={}, imported=True)
                session.add(record)
            record.heads = result.heads
            reason = result.reason
            if not reason:
                try:
                    if record.state != result.state:
                        fresh = materialize(session, entity, entity_id, result.state)
                        changed_parents.add(entity_id if entity == 'application' else result.state['application_id'])
                        if fresh:
                            record.imported = True
                    record.state, record.applied_heads = result.state, result.heads
                    session.flush()
                except DomainBlocked as exc:
                    reason = str(exc)
            for row in rows:
                row.applied = not reason and row.event_id in result.ready
            if reason and reason not in {'missing_ancestors', 'missing_application'}:
                conflict_id = hashlib.sha256(canonical([key, result.heads, reason])).hexdigest()
                if not session.get(SyncConflict, conflict_id):
                    session.add(SyncConflict(id=conflict_id, record_key=key, heads=result.heads,
                        variants=result.variants, base=result.base, reason=reason, resolved=False))
            elif not reason:
                for conflict in session.scalars(select(SyncConflict).where(SyncConflict.record_key == key, SyncConflict.resolved.is_(False))):
                    conflict.resolved = True
        session.flush()
        for group in chunks(queued):
            session.execute(delete(SyncDirty).where(SyncDirty.key.in_(group)))
        for group in chunks(list(changed_parents)):
            waiting = session.execute(select(SyncMutation.entity, SyncMutation.entity_id).where(
                SyncMutation.applied.is_(False), parent_value.in_(group)).distinct()).all()
            mark_dirty(session, [record_key(entity, entity_id) for entity, entity_id in waiting])
        if changed_parents and revisit:
            # Resequencing can free a slot after an earlier sibling was visited.
            # One bounded second pass handles it now; any longer dependency chain
            # remains durably queued for the next run rather than spinning.
            self._apply(session, revisit=False)

    def _stage_mutations(self, session, mutations, workspace_id):
        changed = False
        for group in chunks(mutations):
            values = {}
            for mutation in group:
                data = mutation.model_dump(mode='json')
                if data['event_id'] in values and values[data['event_id']] != data:
                    raise SyncError('An event ID was reused with different contents')
                values[data['event_id']] = data
            existing = dict(session.execute(select(SyncMutation.event_id, SyncMutation.payload)
                .where(SyncMutation.event_id.in_(values))).all())
            for event_id, data in existing.items():
                if data != values[event_id]:
                    raise SyncError('An event ID was reused with different contents')
            new = [data for event_id, data in values.items() if event_id not in existing]
            sequences = {(data['device_id'], data['device_seq']) for data in new}
            if len(sequences) != len(new) or (sequences and session.scalar(select(SyncMutation.event_id).where(
                    tuple_(SyncMutation.device_id, SyncMutation.device_seq).in_(sequences)).limit(1))):
                raise SyncError('Device sequence collision. Re-enroll the cloned or restored device')
            if new:
                session.connection().execute(insert(SyncMutation.__table__), [dict(event_id=data['event_id'],
                    workspace_id=workspace_id, device_id=data['device_id'], device_seq=data['device_seq'],
                    entity=data['entity'], entity_id=data['entity_id'], payload=data, applied=False) for data in new])
                mark_dirty(session, [record_key(data['entity'], data['entity_id']) for data in new])
                changed = True
        return changed

    def _receive(self, files, key, workspace_id, cursor=None):
        with Session(self.engine) as session:
            known = set()
            for group in chunks([file['id'] for file in files]):
                known.update(session.scalars(select(SyncInbox.file_id).where(SyncInbox.file_id.in_(group))))
        changed, received = False, False
        # Authenticate/stage one file at a time. Network calls and decoding never
        # hold SQLite's write lock; a page cursor advances only after all files
        # have been durably staged and the merge work has committed.
        for file in files:
            if file['id'] in known:
                continue
            value = self.transport.download(file['id'])
            import json
            if json.loads(value).get('header', {}).get('workspace_id') != workspace_id:
                continue
            batch = open_envelope(value, key, workspace_id)
            digest = hashlib.sha256(canonical(batch.model_dump(mode='json'))).hexdigest()
            with Session(self.engine) as session:
                session.info['sync_import'] = True
                session.execute(text('BEGIN IMMEDIATE'))
                if session.get(SyncInbox, file['id']):
                    continue
                duplicate = session.scalar(select(SyncInbox.digest).where(SyncInbox.batch_id == str(batch.batch_id)).limit(1))
                if duplicate and duplicate != digest:
                    raise SyncError('A batch ID was reused with different contents')
                if not duplicate:
                    changed |= self._stage_mutations(session, batch.mutations, workspace_id)
                device = session.get(SyncDevice, str(batch.device_id))
                if not device:
                    device = SyncDevice(device_id=str(batch.device_id), acknowledgments={})
                    session.add(device)
                device.last_seen = utc_now()
                device.acknowledgments = {dev: max(seq, device.acknowledgments.get(dev, 0)) for dev, seq in
                    (device.acknowledgments | batch.acknowledgments).items()}
                session.add(SyncInbox(file_id=file['id'], batch_id=str(batch.batch_id), digest=digest,
                    quota_bytes=int(file.get('quotaBytesUsed') or file.get('size') or len(value))))
                local = session.get(SyncBatch, str(batch.batch_id))
                if local:
                    if open_envelope(local.ciphertext, key, workspace_id) != batch:
                        raise SyncError('Remote batch differs from its durable upload intent')
                    local.uploaded = True
                    session.execute(SyncOutbox.__table__.update().where(SyncOutbox.batch_id == local.batch_id).values(uploaded=True))
                    session.execute(SyncCheckpoint.__table__.update().where(SyncCheckpoint.batch_id == local.batch_id).values(uploaded=True))
                session.commit()
                received = True
            del batch, value
        with Session(self.engine) as session:
            session.info['sync_import'] = True
            session.execute(text('BEGIN IMMEDIATE'))
            changed |= session.scalar(select(SyncDirty.key).limit(1)) is not None
            self._apply(session)
            workspace = session.get(SyncWorkspace, 1)
            if cursor is not None:
                workspace.cursor = cursor
            if received:
                workspace.remote_bytes = session.scalar(select(func.sum(SyncInbox.quota_bytes))) or 0
                workspace.remote_objects = session.scalar(select(func.count()).select_from(SyncInbox)) or 0
            session.commit()
        return changed

    def _prepare(self, key, *, acknowledgment=False, checkpoint=False):
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            workspace = session.get(SyncWorkspace, 1)
            workspace_id, device_id = workspace.workspace_id, workspace.device_id
            pending = session.scalar(select(SyncOutbox.event_id).where(SyncOutbox.batch_id.is_(None)).limit(1))
            if not pending and not acknowledgment and not checkpoint:
                return
            vectors = self._vectors(session) if pending or acknowledgment else {}
            had_groups = False
            while pending:
                rows = session.execute(select(SyncOutbox.event_id, SyncMutation.payload).join(SyncMutation,
                    SyncOutbox.event_id == SyncMutation.event_id).where(SyncOutbox.batch_id.is_(None))
                    .order_by(SyncOutbox.event_id).limit(100)).all()
                if not rows:
                    break
                groups, current, size, origin = [], [], 0, None
                for event_id, payload in rows:
                    length = len(canonical(payload))
                    if current and (size + length > 65536 or payload['device_id'] != origin):
                        groups.append(current)
                        current, size = [], 0
                    origin = payload['device_id']
                    current.append((event_id, payload))
                    size += length
                if current:
                    groups.append(current)
                for group in groups:
                    batch_id = str(uuid4())
                    batch = Batch(workspace_id=workspace_id, device_id=group[0][1]['device_id'], batch_id=batch_id,
                        mutations=[payload for _, payload in group], acknowledgments=vectors)
                    session.add(SyncBatch(batch_id=batch_id, ciphertext=seal(batch, key)))
                    session.execute(SyncOutbox.__table__.update().where(SyncOutbox.event_id.in_([event_id for event_id, _ in group])).values(batch_id=batch_id))
                session.flush()
                had_groups = True
                pending = len(rows) == 100
            if acknowledgment and not had_groups:
                batch_id = str(uuid4())
                batch = Batch(workspace_id=workspace_id, device_id=device_id, batch_id=batch_id,
                    kind='ack', acknowledgments=vectors)
                session.add(SyncBatch(batch_id=batch_id, ciphertext=seal(batch, key)))
            session.commit()
        if checkpoint:
            self._checkpoint(key, workspace_id, device_id)

    def _checkpoint(self, key, workspace_id, device_id):
        encoded = []
        # Explicit read transaction gives a consistent WAL snapshot while local
        # edits remain writable. Encoding/encryption never takes a write lease.
        with Session(self.engine) as snapshot:
            snapshot.execute(text('BEGIN'))
            total = snapshot.scalar(select(func.count()).select_from(SyncMutation)) or 0
            vectors = self._vectors(snapshot)
            payloads = snapshot.scalars(select(SyncMutation.payload).order_by(SyncMutation.device_id, SyncMutation.device_seq)
                .execution_options(yield_per=1000))
            for batch in checkpoint_batches(workspace_id, device_id, payloads, vectors):
                encoded.append((str(batch.batch_id), seal(batch, key)))
        # Publish all local checkpoint intents atomically; partial uploads are
        # replay-safe, and a crash cannot register an incomplete local generation.
        with Session(self.engine) as session:
            session.execute(text('BEGIN IMMEDIATE'))
            for batch_id, ciphertext in encoded:
                session.add(SyncBatch(batch_id=batch_id, ciphertext=ciphertext))
                session.add(SyncCheckpoint(batch_id=batch_id, event_count=total))
            session.commit()

    def run(self, *, manual=False, checkpoint=False):
        if not self.lock.acquire(blocking=False):
            return self.status()
        try:
            with Session(self.engine) as session:
                workspace = session.get(SyncWorkspace, 1)
                if workspace is None:
                    raise SyncError('Initialize sync first')
                if workspace.retry_at and workspace.retry_at > utc_now() and not manual:
                    return self.status()
                workspace_id, cursor = workspace.workspace_id, workspace.cursor
                if self.transport.identity() != workspace.subject:
                    raise SyncError('The connected Google account does not match this sync workspace')
                key = self._key(workspace)
            changed = False
            if cursor is None:
                cursor = self.transport.start_cursor()
                files = self.transport.list_files()
                changed |= self._receive(files, key, workspace_id, cursor)
            while True:
                try:
                    files, removed, next_cursor, more = self.transport.changes(cursor)
                except Exception as exc:
                    if getattr(exc, 'kind', '') == 'invalid_cursor':
                        with Session(self.engine) as session:
                            session.get(SyncWorkspace, 1).cursor = None
                            session.commit()
                        raise SyncError('Drive cursor expired. Sync again to rediscover files') from None
                    raise
                # Missing remote files never become local record deletions.
                if removed:
                    raise SyncError('Remote sync files were removed. Preserve local data and review recovery before continuing')
                if next_cursor is None:
                    raise SyncError('Drive did not return a durable change cursor')
                changed |= self._receive(files, key, workspace_id, next_cursor)
                cursor = next_cursor
                if not more:
                    break
            with Session(self.engine) as session:
                last_checkpoint = session.scalar(select(SyncCheckpoint).order_by(SyncCheckpoint.created_at.desc()).limit(1))
                event_count = session.scalar(select(func.count()).select_from(SyncMutation)) or 0
                checkpoint = checkpoint or not last_checkpoint or (event_count - last_checkpoint.event_count >= 1000) or (last_checkpoint.created_at < utc_now() - timedelta(days=30))
            self._prepare(key, acknowledgment=changed, checkpoint=checkpoint)
            with Session(self.engine) as session:
                batches = [(item.batch_id, item.ciphertext) for item in session.scalars(select(SyncBatch).where(SyncBatch.uploaded.is_(False)))]
            for batch_id, ciphertext in batches:
                self.transport.upload_immutable(batch_id, ciphertext)
                with Session(self.engine) as session:
                    session.get(SyncBatch, batch_id).uploaded = True
                    for item in session.scalars(select(SyncOutbox).where(SyncOutbox.batch_id == batch_id)):
                        item.uploaded = True
                    snapshot = session.get(SyncCheckpoint, batch_id)
                    if snapshot:
                        snapshot.uploaded = True
                    session.commit()
            with Session(self.engine) as session:
                workspace = session.get(SyncWorkspace, 1)
                workspace.last_success, workspace.last_error = utc_now(), None
                workspace.retry_at, workspace.failures = None, 0
                session.commit()
        except Exception as exc:
            # Provider bodies may contain private data; expose fixed errors only.
            from app.google_connection import GoogleConnectionError
            message = str(exc) if isinstance(exc, (SyncError, GoogleConnectionError)) else 'Sync validation or transport failed. Local data and pending edits are preserved.'
            with Session(self.engine) as session:
                workspace = session.get(SyncWorkspace, 1)
                if workspace:
                    workspace.failures += 1
                    delay = max(min(2 ** min(workspace.failures, 10), 900), getattr(exc, 'retry_after', None) or 0)
                    workspace.retry_at, workspace.last_error = utc_now() + timedelta(seconds=delay + secrets.randbelow(4)), message
                    session.commit()
        finally:
            self.lock.release()
        return self.status()

    def conflicts(self):
        with Session(self.engine) as session:
            return [{'id': item.id, 'record_key': item.record_key, 'heads': item.heads, 'reason': item.reason,
                     'base': item.base, 'variants': item.variants} for item in session.scalars(
                         select(SyncConflict).where(SyncConflict.resolved.is_(False)))
                    if item.heads == session.get(SyncRecord, item.record_key).heads]

    def resolve(self, conflict_id, state, expected_heads):
        with self.lock, Session(self.engine) as session:
            session.info['sync_import'] = True
            session.execute(text('BEGIN IMMEDIATE'))
            conflict = session.get(SyncConflict, conflict_id)
            if conflict is None or conflict.resolved:
                raise SyncError('Conflict is no longer open. Refresh before resolving')
            record = session.get(SyncRecord, conflict.record_key)
            if sorted(expected_heads) != sorted(record.heads):
                raise SyncError('Conflict changed. Refresh and review every current branch')
            entity, entity_id = conflict.record_key.split(':')
            state = STATES[entity].model_validate(state).model_dump(mode='json')
            workspace = session.get(SyncWorkspace, 1)
            try:
                materialize(session, entity, entity_id, state)
            except DomainBlocked:
                raise SyncError('This resolution violates relationships or follow-up sequence rules') from None
            append_local(session, workspace, entity, entity_id, state, actor='HUMAN', resolution=True)
            session.flush()
            self._apply(session)
            session.commit()
        return self.status()
