from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import create_database, migrate_database
from app.models import Application, ExternalConnection, MailImportReceipt
from app.sync.models import SyncWorkspace
from uuid import uuid4
import json


def test_mail_receipts_upgrade_preserves_existing_applications(legacy_database,tmp_path):
    with legacy_database('0024_sync_work_queue') as connection:
        connection.execute(text("INSERT INTO applications(id,job_title,company,date_applied,email_reference) VALUES ('before-mail-sync','Engineer','Example','2026-10-20','original source')"))
    engine=create_database(tmp_path)
    try:
        migrate_database(engine)
        with Session(engine) as session:
            assert session.get(Application,'before-mail-sync').email_reference=='original source'
            session.add(MailImportReceipt(account='account',message_id='abc',thread_id='aa',state='REVIEW',subject='Original email',reason='Needs review'))
            session.commit()
        migrate_database(engine)
        with Session(engine) as session:
            assert session.get(MailImportReceipt,('account','abc')).subject=='Original email'
    finally:
        engine.dispose()


def test_populated_google_database_upgrades_without_enrolling_or_changing_credentials(legacy_database, tmp_path):
    with legacy_database('0022_shared_google_agent') as connection:
        connection.execute(text("INSERT INTO applications(id,job_title,company,date_applied,email_reference,description) VALUES ('legacy','Engineer','Example','2026-10-20','email reference','local private text')"))
        connection.execute(text("INSERT INTO external_connections(id,issuer,subject,email,scopes,status,secret_reference,generation,updated_at) VALUES (1,'https://accounts.google.com','subject','example@example.test','[]','CONNECTED','native-ref',4,CURRENT_TIMESTAMP)"))
    engine = create_database(tmp_path)
    try:
        migrate_database(engine)
        with Session(engine) as session:
            assert session.get(SyncWorkspace, 1) is None
            assert session.get(Application, 'legacy').description == 'local private text'
            assert session.get(ExternalConnection, 1).secret_reference == 'native-ref'
            assert session.get(ExternalConnection, 1).generation == 4
    finally:
        engine.dispose()


def test_existing_sync_history_is_queued_once_when_incremental_indexes_are_added(legacy_database, tmp_path):
    entity_id, event_id, workspace_id, device_id = (str(uuid4()) for _ in range(4))
    with legacy_database('0023_compact_sync') as connection:
        connection.execute(text("INSERT INTO sync_mutations(event_id,workspace_id,device_id,device_seq,entity,entity_id,payload,applied) VALUES (:event,:workspace,:device,1,'application',:entity,:payload,1)"),
            dict(event=event_id, workspace=workspace_id, device=device_id, entity=entity_id, payload=json.dumps({'event_id': event_id})))
    engine = create_database(tmp_path)
    try:
        migrate_database(engine)
        with engine.connect() as connection:
            assert connection.execute(text('SELECT key FROM sync_dirty')).scalars().all() == ['application:' + entity_id]
            assert connection.execute(text('SELECT event_id FROM sync_mutations')).scalar_one() == event_id
        migrate_database(engine)
        with engine.connect() as connection:
            assert connection.execute(text('SELECT count(*) FROM sync_dirty')).scalar_one() == 1
    finally:
        engine.dispose()
