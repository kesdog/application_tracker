from sqlalchemy.orm import Session

from app.models import RecipientCandidate
from app.recipient_discovery import context
from app.applications import get_application


def test_target_status_tracks_current_leads_selection_sent_history_and_phone_calls(client):
    app = client.post('/api/applications', json={
        'company': 'Example', 'job_title': 'Engineer', 'date_applied': '2026-10-01',
        'email_reference': 'Message one\nMessage two', 'phone_number': '+33612345678',
    }).json()
    app_url = f"/api/applications/{app['id']}"
    assert app['followup_target_status'] == 'UNKNOWN'
    assert not app['has_potential_recipients']
    assert client.get(app_url).json()['email_reference'] == 'Message one\nMessage two'
    item = client.get(app_url + '/work').json()['followups'][0]
    item_url = app_url + '/followups/' + item['id']

    def status(expected, potential=False):
        record = client.get(app_url).json()
        assert record['followup_target_status'] == expected
        assert record['has_potential_recipients'] == potential
        assert next(row for row in client.get('/api/applications').json() if row['id'] == app['id'])['followup_target_status'] == expected

    with Session(client.app.state.engine) as session:
        record = get_application(session, app['id'])
        session.add(RecipientCandidate(application_id=app['id'], context=context(record), value={'name': 'Hiring lead'}))
        session.commit()
    status('POTENTIAL', True)
    assert client.get('/api/followups').json()['items'][0]['application']['has_potential_recipients']
    assert client.patch(item_url, json={'recipient_email': 'jobs@example.com'}).status_code == 200
    status('CONFIRMED', True)
    assert client.patch(item_url, json={'status': 'SENT'}).status_code == 200
    assert client.patch(item_url, json={'archived': True}).status_code == 200
    status('SENT', True)
    # An archived sent email remains history; reopening it removes the sent marker.
    assert client.patch(item_url, json={'status': 'PREPARED'}).status_code == 200
    status('POTENTIAL', True)
    client.patch(app_url, json={'job_title': 'Changed role'})
    status('UNKNOWN')
    with Session(client.app.state.engine) as session:
        record = get_application(session, app['id'])
        session.add(RecipientCandidate(application_id=app['id'], context=context(record), value={'email': 'privacy@example.com', 'excluded': True}))
        session.commit()
    status('UNKNOWN')
    phone = client.post(app_url + '/followups', json={'channel': 'PHONE'}).json()
    assert client.patch(app_url + '/followups/' + phone['id'], json={'status': 'SENT'}).status_code == 200
    status('UNKNOWN')
    client.patch(app_url, json={'contact_email': 'known@example.com'})
    status('CONFIRMED')
