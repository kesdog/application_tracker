from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import create_database, migrate_database
from app.models import RecipientDiscovery, RecipientQueueControl


def test_recipient_control_upgrade_preserves_existing_queue_and_persists_pause(tmp_path, legacy_database):
    with legacy_database('0029_followup_message_versions') as connection:
        connection.execute(text("INSERT INTO applications(id,company,job_title,date_applied,status,email_reference) VALUES ('app','Example','Engineer','2026-10-01','SUBMITTED','message')"))
        connection.execute(text("INSERT INTO recipient_discovery(id,application_id,state,context,requested_at,attempts,warnings,page_limit,refresh_pages,page_counts) VALUES ('job','app','QUEUED','{}',CURRENT_TIMESTAMP,0,'[]',6,0,'{}')"))
    engine = create_database(tmp_path)
    try:
        migrate_database(engine)
        with Session(engine) as session:
            assert session.get(RecipientDiscovery, 'job').priority == 0
            session.add(RecipientQueueControl(id=1, paused=True)); session.commit()
        migrate_database(engine)
        with Session(engine) as session:
            assert session.get(RecipientQueueControl, 1).paused
    finally:
        engine.dispose()
