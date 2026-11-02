import json
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.database import create_database, migrate_database
from app.models import FollowUp, FollowUpMessageVersion


def test_existing_language_and_audited_messages_survive_upgrade_and_restart(legacy_database, tmp_path):
    with legacy_database('0028_mail_sync_scope') as connection:
        connection.execute(text("INSERT INTO applications(id,job_title,company,date_applied,email_reference) VALUES ('legacy','Engineer','Example','2026-10-01','original source')"))
        connection.execute(text("INSERT INTO followups(id,application_id,sequence_number,due_at,status,subject,body,customization,variable_snapshot,revision) VALUES ('message','legacy',1,'2026-10-08','PREPARED','Objet français','Texte français',:custom,:variables,3)"),
            {'custom': json.dumps({'language': 'French'}), 'variables': json.dumps({'language': 'French'})})
        previous = {'subject': 'English subject', 'body': 'Edited English message', 'customization': {}, 'variable_snapshot': {'language': 'English'}, 'revision': 2}
        connection.execute(text("INSERT INTO audit_entries(id,application_id,entity_type,entity_id,action,previous_value,new_value,actor_type,created_at,reversible) VALUES ('audit','legacy','FOLLOWUP','message','UPDATE',:previous,:new,'HUMAN',CURRENT_TIMESTAMP,1)"),
            {'previous': json.dumps(previous), 'new': json.dumps({'subject': 'Objet français', 'body': 'Texte français', 'customization': {'language': 'French'}, 'variable_snapshot': {'language': 'French'}, 'revision': 3})})
    engine = create_database(tmp_path)
    try:
        migrate_database(engine)
        with Session(engine) as session:
            item = session.get(FollowUp, 'message')
            assert item.message_language == 'fr' and item.body == 'Texte français' and item.revision == 3
            versions = session.scalars(select(FollowUpMessageVersion)).all()
            assert {(v.language, v.subject, v.body) for v in versions} == {
                ('en', 'English subject', 'Edited English message'), ('fr', 'Objet français', 'Texte français')}
        migrate_database(engine)
        with Session(engine) as session:
            assert len(session.scalars(select(FollowUpMessageVersion)).all()) == 2
    finally:
        engine.dispose()
