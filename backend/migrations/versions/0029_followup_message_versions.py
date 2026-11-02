"""Keep local follow-up language versions and explicitly label the active message."""
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = '0029_followup_message_versions'
down_revision = '0028_mail_sync_scope'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('followups', sa.Column('message_language', sa.String(80), nullable=False, server_default='en'))
    table = op.create_table('followup_message_versions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('followup_id', sa.String(36), sa.ForeignKey('followups.id', ondelete='CASCADE'), nullable=False),
        sa.Column('language', sa.String(80), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False), sa.Column('body', sa.Text(), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False), sa.Column('customization', sa.JSON(), nullable=False),
        sa.Column('template_snapshot', sa.JSON(), nullable=False), sa.Column('variable_snapshot', sa.JSON(), nullable=False),
        sa.Column('source_revision', sa.Integer(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('followup_id', 'fingerprint', name='followup_message_version_unique'))
    op.create_index('ix_followup_message_versions_followup_id', 'followup_message_versions', ['followup_id'])
    connection = op.get_bind()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    fields = ('subject', 'body', 'instructions', 'customization', 'template_snapshot', 'variable_snapshot')
    decode = lambda value: json.loads(value or '{}') if isinstance(value, str) else value or {}
    for row in connection.execute(sa.text('SELECT * FROM followups')).mappings():
        # Inherited legacy messages have a variable snapshot of their effective preferences.
        customization, template, variables = (decode(row[field]) for field in ('customization', 'template_snapshot', 'variable_snapshot'))
        label = variables.get('language') or customization.get('language') or template.get('language') or 'English'
        language = {'english': 'en', 'anglais': 'en', 'french': 'fr', 'français': 'fr'}.get(label.strip().lower(), label.strip().lower())
        connection.execute(sa.text('UPDATE followups SET message_language=:language WHERE id=:id'), dict(language=language, id=row['id']))
        seen = set()

        def save_snapshot(state, source_revision, created, *, active=False):
            if not state['subject'] and not state['body']:
                return
            value = state['variable_snapshot'].get('language') or state['customization'].get('language') or state['template_snapshot'].get('language') or 'English'
            code = {'english': 'en', 'anglais': 'en', 'french': 'fr', 'français': 'fr'}.get(value.strip().lower(), value.strip().lower())
            payload = {**state, 'language': code}
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if fingerprint in seen:
                return
            seen.add(fingerprint)
            created = datetime.fromisoformat(created) if isinstance(created, str) else created or now
            connection.execute(table.insert().values(id=str(uuid4()), followup_id=row['id'], fingerprint=fingerprint,
                source_revision=source_revision, created_at=created, last_used_at=now if active else created, **payload))

        state = dict(subject=row['subject'], body=row['body'], instructions=row['instructions'],
                     customization=customization, template_snapshot=template, variable_snapshot=variables)
        save_snapshot(state, row['revision'], row['updated_at'], active=True)
        # Recover messages replaced before version storage existed, including edits later undone.
        audits = connection.execute(sa.text("SELECT previous_value,new_value,created_at FROM audit_entries WHERE entity_type='FOLLOWUP' AND entity_id=:id ORDER BY created_at DESC,id DESC"), {'id': row['id']}).mappings()
        for audit in audits:
            previous, new = decode(audit['previous_value']), decode(audit['new_value'])
            if not any(field in previous for field in fields):
                continue
            save_snapshot({**state, **{field: new[field] for field in fields if field in new}}, new.get('revision', row['revision']), audit['created_at'])
            state = {**state, **{field: previous[field] for field in fields if field in previous}}
            save_snapshot(state, previous.get('revision', row['revision']), audit['created_at'])


def downgrade():
    op.drop_table('followup_message_versions')
    op.drop_column('followups', 'message_language')
