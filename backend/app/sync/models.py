"""Replica persistence, kept separate from tracker domain models."""
from datetime import datetime

from sqlalchemy import JSON, String, Text, LargeBinary, UniqueConstraint, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, utc_now


class SyncWorkspace(Base):
    __tablename__ = 'sync_workspace'
    __table_args__ = (CheckConstraint('id = 1', name='single_sync_workspace'),)
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    workspace_id: Mapped[str] = mapped_column(String(36))
    device_id: Mapped[str] = mapped_column(String(36))
    label: Mapped[str] = mapped_column(String(100))
    subject: Mapped[str] = mapped_column(String(255))
    secret_reference: Mapped[str | None] = mapped_column(String(100))
    next_seq: Mapped[int] = mapped_column(default=1)
    cursor: Mapped[str | None] = mapped_column(Text)
    last_success: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(String(500))
    retry_at: Mapped[datetime | None]
    failures: Mapped[int] = mapped_column(default=0)
    remote_bytes: Mapped[int] = mapped_column(default=0)
    remote_objects: Mapped[int] = mapped_column(default=0)
    restored: Mapped[bool] = mapped_column(default=False)


class SyncMutation(Base):
    __tablename__ = 'sync_mutations'
    __table_args__ = (UniqueConstraint('device_id', 'device_seq', name='sync_device_sequence'),
        Index('ix_sync_mutations_record', 'entity', 'entity_id'),
        Index('ix_sync_mutations_applied_device', 'applied', 'device_id', 'device_seq'))
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(36))
    device_id: Mapped[str] = mapped_column(String(36))
    device_seq: Mapped[int]
    entity: Mapped[str] = mapped_column(String(20), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    applied: Mapped[bool] = mapped_column(default=False)


class SyncRecord(Base):
    __tablename__ = 'sync_records'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    heads: Mapped[list] = mapped_column(JSON, default=list)
    applied_heads: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    imported: Mapped[bool] = mapped_column(default=False)


class SyncDirty(Base):
    __tablename__ = 'sync_dirty'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)


class SyncOutbox(Base):
    __tablename__ = 'sync_outbox'
    __table_args__ = (Index('ix_sync_outbox_pending', 'uploaded', 'batch_id'),
                      Index('ix_sync_outbox_unbatched', 'batch_id', 'event_id'))
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), index=True)
    uploaded: Mapped[bool] = mapped_column(default=False)


class SyncInbox(Base):
    __tablename__ = 'sync_inbox'
    __table_args__ = (Index('ix_sync_inbox_batch', 'batch_id'),)
    file_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(String(36))
    quota_bytes: Mapped[int] = mapped_column(default=0)


class SyncBatch(Base):
    __tablename__ = 'sync_batches'
    __table_args__ = (Index('ix_sync_batches_pending', 'uploaded', 'batch_id'),)
    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded: Mapped[bool] = mapped_column(default=False)


class SyncConflict(Base):
    __tablename__ = 'sync_conflicts'
    __table_args__ = (Index('ix_sync_conflicts_open_record', 'resolved', 'record_key'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    record_key: Mapped[str] = mapped_column(String(80), index=True)
    heads: Mapped[list] = mapped_column(JSON)
    variants: Mapped[list] = mapped_column(JSON)
    base: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(100))
    resolved: Mapped[bool] = mapped_column(default=False)


class SyncDevice(Base):
    __tablename__ = 'sync_devices'
    device_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    acknowledgments: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen: Mapped[datetime] = mapped_column(default=utc_now)


class SyncCheckpoint(Base):
    __tablename__ = 'sync_checkpoints'
    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    event_count: Mapped[int]
    uploaded: Mapped[bool] = mapped_column(default=False)
