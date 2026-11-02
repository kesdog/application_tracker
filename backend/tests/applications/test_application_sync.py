from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from threading import Event
import time
from types import SimpleNamespace

import pytest
import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import mailbox_import
from app.google_connection import GoogleConnectionError, GoogleMailProvider
from app.models import Application, MailImportReceipt, MailSyncBoundary, MailSyncScope, TimelineEvent


@pytest.fixture(autouse=True)
def same_origin(client):
    client.base_url = 'http://127.0.0.1:8000'
    client.headers['Origin'] = 'http://127.0.0.1:8000'


def mail(message_id, body, *, thread='aa', day=1, subject='Application Engineer at Example'):
    return {'id':message_id, 'thread_id':thread, 'headers':[{'name':'Subject','value':subject},
        {'name':'Date','value':f'{day:02d} Oct 2026 12:00:00 +0200'}], 'content':body}


class FakeMail:
    def __init__(self, pages):
        self.pages = pages
        self.messages = {item['id']:item for page in pages for item in page}
        self.reads = []
        self.searches = []
    def application_messages(self, token, *, after=None, before=None):
        self.searches.append((token, after, before))
        page = int(token or 0)
        items = [item for item in self.pages[page] if 'internal_date' not in item or (
            (after is None or int(item['internal_date']) > after * 1000)
            and (before is None or int(item['internal_date']) < before * 1000))]
        return {'messages':[{'id':item['id']} for item in items], **({'nextPageToken':str(page+1)} if page+1<len(self.pages) else {})}
    def application_message(self, message_id):
        self.reads.append(message_id)
        value = self.messages[message_id]
        if isinstance(value, Exception): raise value
        return deepcopy(value)


class FakeDrive:
    def __init__(self, initialized=True):
        self.calls = 0
        self.initialized = initialized
    def status(self): return {'initialized':self.initialized, 'running':False, 'conflicts':0}
    def run(self, **_):
        self.calls += 1
        return self.status()


def setup(client, messages):
    service = client.app.state.application_sync
    service.google = SimpleNamespace(status=lambda: {'email':'person@example.com','capabilities':{'gmail_read':True}})
    service.mail, service.drive = FakeMail(messages), FakeDrive()
    return service


def finish(client):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = client.get('/api/applications/sync/status').json()
        if value['state'] != 'RUNNING': return value
        time.sleep(.01)
    raise AssertionError('Sync did not finish')


def seed(client):
    return client.post('/api/applications',json={'company':'Example','job_title':'Engineer','date_applied':'2026-10-01','email_reference':'Original reference'}).json()


def save_mail_limit(client, limit):
    settings = client.get('/api/settings/general').json()
    revision = settings.pop('revision')
    return client.put('/api/settings/general', json={**settings, 'mail_sync_max_messages': limit, 'expected_revision': revision})


@pytest.mark.parametrize('limit', [0, 1001, 1.5, True, None])
def test_mail_limit_rejects_invalid_values_without_changing_saved_settings(client, limit):
    assert client.get('/api/settings/general').json()['mail_sync_max_messages'] == 100
    assert save_mail_limit(client, limit).status_code == 422
    assert client.get('/api/settings/general').json()['mail_sync_max_messages'] == 100


def test_mail_limit_persists_and_new_runs_continue_without_skipping_mail_or_rereading_receipts(client):
    from app.application_sync import ApplicationSync
    service = setup(client, [[mail('ca01', 'Unclear message')],
                             [mail('ca02', 'Unclear message', thread='bb'),
                              mail('ca03', 'Thank you for applying for Engineer at Example.', thread='cc')]])
    service.clock = lambda: 1800000000
    assert save_mail_limit(client, 2).status_code == 200
    client.post('/api/applications/sync'); first = finish(client)
    assert first['gmail'] == 'LIMIT_REACHED' and first['state'] == 'PARTIAL'
    assert first['checked'] == first['mail_limit'] == 2 and first['limit_reached']
    assert first['gmail_checked_through'] is None and first['review_count'] == 2
    assert service.mail.reads == ['ca01', 'ca02'] and first['drive'] == 'COMPLETED'
    restarted = ApplicationSync(service.engine, service.settings, service.google, service.mail, service.drive,
                                clock=lambda: 1800000100)
    client.app.state.application_sync = restarted
    try:
        client.post('/api/applications/sync'); second = finish(client)
        assert second['gmail'] == 'COMPLETED' and not second['limit_reached']
        assert second['mail_limit'] == 2 and second['checked'] == second['created'] == 1
        assert second['gmail_checked_through'] is not None
        assert service.mail.reads == ['ca01', 'ca02', 'ca03']
        assert len(client.get('/api/applications').json()) == 1
    finally:
        restarted.close()
        client.app.state.application_sync = service


def test_exact_mail_limit_completes_and_existing_boundary_is_not_advanced_by_a_later_capped_run(client):
    service = setup(client, [[mail('ca04', 'Unclear message')]])
    service.clock = lambda: 1800000000
    save_mail_limit(client, 1)
    client.post('/api/applications/sync'); first = finish(client)
    assert first['gmail'] == 'COMPLETED' and first['checked'] == 1
    assert not first['limit_reached']
    service.clock = lambda: 1800000100
    service.mail = FakeMail([[mail('ca04', 'Unclear message'), mail('ca05', 'Unclear message'),
                              mail('ca06', 'Unclear message')]])
    client.post('/api/applications/sync'); capped = finish(client)
    assert capped['gmail'] == 'LIMIT_REACHED' and capped['checked'] == 1
    assert capped['gmail_checked_through'] == first['gmail_checked_through']
    assert service.mail.reads == ['ca05']
    client.post('/api/applications/sync'); final = finish(client)
    assert final['gmail'] == 'COMPLETED' and final['checked'] == 1
    assert final['gmail_checked_through'] != first['gmail_checked_through']
    assert service.mail.reads == ['ca05', 'ca06']


def test_settings_changes_during_a_running_sync_apply_only_to_the_next_run(client):
    service = setup(client, [[mail('ca07', 'Unclear message'), mail('ca08', 'Unclear message')]])
    save_mail_limit(client, 1)
    gate, started = Event(), Event()
    original = service.mail.application_messages
    def blocked(token, **bounds):
        started.set(); gate.wait(3); return original(token, **bounds)
    service.mail.application_messages = blocked
    try:
        client.post('/api/applications/sync')
        assert started.wait(2)
        assert save_mail_limit(client, 5).status_code == 200
    finally:
        gate.set()
    first = finish(client)
    assert first['checked'] == first['mail_limit'] == 1 and first['limit_reached']
    client.post('/api/applications/sync'); second = finish(client)
    assert second['mail_limit'] == 5 and second['checked'] == 1 and second['gmail'] == 'COMPLETED'


def test_capped_batch_applies_clear_updates_but_keeps_unmatched_older_evidence_for_review(client):
    app = seed(client)
    service = setup(client, [[mail('ca09', 'Engineer at Example. Votre candidature n’a pas été retenue.'),
                             mail('ca10', 'We invite you to an interview.', thread='missing', subject='Interview with Another'),
                             mail('ca11', 'Thank you for applying for Developer at Another.', thread='missing', subject='Application Developer at Another')]])
    save_mail_limit(client, 2)
    client.post('/api/applications/sync'); first = finish(client)
    assert first['checked'] == 2 and first['updated'] == 1 and first['limit_reached']
    assert client.get('/api/applications/' + app['id']).json()['outcome'] == 'UNSUCCESSFUL'
    client.post('/api/applications/sync'); second = finish(client)
    assert second['checked'] == second['created'] == 1 and second['gmail'] == 'COMPLETED'
    assert second['review_count'] == 1 and second['reviews'][0]['message_id'] == 'ca10'
    assert service.mail.reads == ['ca09', 'ca10', 'ca11']


def test_sync_paginates_new_and_existing_mail_then_drive_and_retries_without_duplicates(client):
    confirmation=mail('abc1','Thank you for applying for Engineer at Example.',day=1)
    rejection=mail('abc2',"Votre candidature n’a pas été retenue.",day=8)
    service=setup(client,[[rejection],[confirmation]])
    assert client.post('/api/applications/sync').status_code == 200
    result=finish(client)
    assert result['state']=='COMPLETED' and result['gmail']==result['drive']=='COMPLETED'
    assert result['created']==1 and result['updated']==0 and result['checked']==2 and result['review_count']==0
    apps=client.get('/api/applications').json()
    assert len(apps)==1 and apps[0]['company']=='Example' and apps[0]['date_applied']=='2026-10-01'
    assert apps[0]['status']=='CLOSED' and apps[0]['outcome']=='UNSUCCESSFUL'
    assert 'abc1' in apps[0]['email_reference'] and 'abc2' in apps[0]['email_reference']
    assert service.drive.calls==2
    assert sorted(service.mail.reads) == ['abc1', 'abc2']  # the matching pass reuses its payloads
    old_reads=len(service.mail.reads)
    client.post('/api/applications/sync'); repeated=finish(client)
    assert repeated['created']==repeated['updated']==0 and len(service.mail.reads)==old_reads
    assert len(client.get('/api/applications').json())==1
    assert client.get('/api/applications/sync/status',headers={'Authorization':'Bearer agent'}).status_code==403


def test_latest_explicit_update_wins_without_overwriting_original_fields_or_quoted_history(client):
    app=seed(client)
    service=setup(client,[[mail('abc3','Engineer at Example. We invite you to an interview.',day=9),
        mail('abc4',"Engineer at Example. Votre candidature n’a pas été retenue.",day=8),
        mail('abc5','Engineer at Example. Thanks for your reply.<blockquote>Votre candidature n’a pas été retenue.</blockquote>',day=10)]])
    client.post('/api/applications/sync'); result=finish(client)
    saved=client.get('/api/applications/'+app['id']).json()
    assert saved['status']=='INTERVIEW' and saved['date_applied']==app['date_applied']
    assert saved['job_title']=='Engineer' and saved['email_reference'].startswith('Original reference')
    assert result['updated']==1 and result['review_count']==3
    assert {row['message_id'] for row in result['reviews']}=={'abc3','abc4','abc5'}


def test_ambiguous_or_unsupported_messages_stay_for_review_and_closed_records_are_not_reopened(client):
    first=seed(client); seed(client)
    service=setup(client,[[mail('abc6','Thank you for applying for Engineer at Example.'), mail('abc7','New job advertisements for you.',subject='Job digest',thread='bb')]])
    client.post('/api/applications/sync'); result=finish(client)
    assert result['created']==0 and result['review_count']==2
    assert len(client.get('/api/applications').json())==2
    client.patch('/api/applications/'+first['id'],json={'status':'CLOSED','outcome':'WITHDRAWN'})
    ref=mail('abc8','We invite you to an interview.',thread='cc')
    client.patch('/api/applications/'+first['id'],json={'email_reference':'[Gmail:abc8]'})
    service.mail=FakeMail([[ref]])
    client.post('/api/applications/sync'); finish(client)
    assert client.get('/api/applications/'+first['id']).json()['outcome']=='WITHDRAWN'


def test_partial_mail_failure_preserves_committed_records_and_still_runs_drive(client):
    service=setup(client,[[mail('abc9','Thank you for applying for Engineer at Example.'),mail('abca','Unused',thread='bb')]])
    service.mail.messages['abca']=GoogleConnectionError('Reconnect Gmail.')
    client.post('/api/applications/sync'); result=finish(client)
    assert result['state']=='PARTIAL' and result['created']==1 and result['drive']=='COMPLETED'
    assert service.drive.calls==2 and len(client.get('/api/applications').json())==1
    assert 'Reconnect Gmail.' in result['warnings']


def test_duplicate_presses_join_running_job_and_missing_connections_are_actionable(client):
    service=setup(client,[[mail('abcb','New jobs')]])
    gate, started=Event(),Event()
    original=service.mail.application_messages
    def blocked(token, **bounds):
        started.set(); gate.wait(3); return original(token, **bounds)
    service.mail.application_messages=blocked
    try:
        first=client.post('/api/applications/sync').json()
        assert started.wait(2)
        second=client.post('/api/applications/sync').json()
        assert first['id']==second['id']
    finally: gate.set()
    finish(client)
    service.google=SimpleNamespace(status=lambda:{'email':None,'capabilities':{'gmail_read':False}})
    service.drive=FakeDrive(False)
    client.post('/api/applications/sync'); result=finish(client)
    assert result['gmail']==result['drive']=='SETUP_REQUIRED' and result['state']=='PARTIAL'


def test_disabled_gmail_api_reports_setup_without_claiming_expired_consent(client):
    service = setup(client, [[]])
    def disabled(_token, **_bounds):
        raise GoogleConnectionError('Enable the Gmail API in your Google Cloud project, then retry.', kind='setup_required')
    service.mail.application_messages = disabled
    client.post('/api/applications/sync')
    result = finish(client)
    assert result['gmail'] == 'SETUP_REQUIRED' and result['state'] == 'PARTIAL'
    assert result['checked'] == result['created'] == result['updated'] == 0
    assert result['drive'] == 'COMPLETED'
    assert 'Enable the Gmail API' in result['warnings'][0]


@pytest.mark.parametrize('operation', ['application_messages', 'application_message'])
def test_transient_gmail_read_limit_retries_without_restarting_saved_imports(client, monkeypatch, operation):
    service = setup(client, [[mail('abcf', 'Thank you for applying for Engineer at Example.')]])
    original = getattr(service.mail, operation)
    attempts, waits = [], []
    def limited(*args, **kwargs):
        attempts.append(args)
        if len(attempts) == 1:
            raise GoogleConnectionError('Limited', kind='rate_limit', retry_after=17)
        return original(*args, **kwargs)
    setattr(service.mail, operation, limited)
    monkeypatch.setattr(service.closed, 'wait', lambda delay: waits.append(delay) or False)
    client.post('/api/applications/sync')
    result = finish(client)
    assert result['gmail'] == 'COMPLETED' and result['created'] == result['checked'] == 1
    assert len(attempts) == 2 and waits == [17]
    assert len(client.get('/api/applications').json()) == 1


@pytest.mark.parametrize(('retry_after', 'waits'), [(None, [5, 10, 20]), (120, [])])
def test_persistent_gmail_limit_has_bounded_retries_and_honors_long_retry_after(client, monkeypatch, retry_after, waits):
    service = setup(client, [[]])
    delays, attempts = [], []
    def limited(_token, **_bounds):
        attempts.append(1)
        raise GoogleConnectionError('Provider rate limit reached.', kind='rate_limit', retry_after=retry_after)
    service.mail.application_messages = limited
    monkeypatch.setattr(service.closed, 'wait', lambda delay: delays.append(delay) or False)
    client.post('/api/applications/sync')
    result = finish(client)
    assert result['gmail'] == 'FAILED' and result['drive'] == 'COMPLETED'
    assert delays == waits and len(attempts) == len(waits) + 1


def test_gmail_retry_rechecks_the_account_after_waiting(client, monkeypatch):
    service = setup(client, [[]])
    attempts = []
    def limited(_token, **_bounds):
        attempts.append(1)
        raise GoogleConnectionError('Limited', kind='rate_limit')
    def switch_account(_delay):
        service.google = SimpleNamespace(status=lambda: {'email': 'other@example.com', 'capabilities': {'gmail_read': True}})
        return False
    service.mail.application_messages = limited
    monkeypatch.setattr(service.closed, 'wait', switch_account)
    client.post('/api/applications/sync')
    result = finish(client)
    assert result['gmail'] == 'FAILED' and len(attempts) == 1
    assert not client.get('/api/applications').json()


def test_receipt_and_application_writes_are_atomic_and_dates_are_not_invented(client,monkeypatch):
    message=mail('abcc','Thank you for applying for Engineer at Example.')
    def fail(*_args,**_kwargs): raise RuntimeError('Simulated event failure')
    monkeypatch.setattr(mailbox_import,'record_event',fail)
    with pytest.raises(RuntimeError):
        mailbox_import.reconcile(client.app.state.engine,client.app.state.settings,'account',message)
    with Session(client.app.state.engine) as session:
        assert session.scalar(select(func.count()).select_from(Application))==0
        assert session.scalar(select(func.count()).select_from(MailImportReceipt))==0
    monkeypatch.undo()
    message['headers']=[{'name':'Subject','value':'Application'}]
    mailbox_import.reconcile(client.app.state.engine,client.app.state.settings,'account',message)
    assert not client.get('/api/applications').json()


def test_changed_google_identity_cannot_apply_mail_read_from_another_account(client):
    service=setup(client,[[mail('abcd','Thank you for applying for Engineer at Example.')]])
    original=service.mail.application_message
    def switch(message_id):
        value=original(message_id)
        service.google=SimpleNamespace(status=lambda:{'email':'other@example.com','capabilities':{'gmail_read':True}})
        return value
    service.mail.application_message=switch
    client.post('/api/applications/sync'); result=finish(client)
    assert result['state']=='PARTIAL' and not client.get('/api/applications').json()


def test_completed_boundary_survives_service_restart_and_only_reads_new_mail(client):
    from app.application_sync import ApplicationSync
    start = 1800000000
    old = {**mail('ab10', 'Unknown message'), 'internal_date': str((start - 10) * 1000)}
    edge = {**mail('ab11', 'Another unknown message', thread='bb'), 'internal_date': str(start * 1000)}
    service = setup(client, [[old, edge]])
    service.clock = lambda: start
    client.post('/api/applications/sync'); first = finish(client)
    assert first['checked'] == first['review_count'] == 1
    assert service.mail.reads == ['ab10']  # current-second arrival is left for the next window
    restarted = ApplicationSync(service.engine, service.settings, service.google, service.mail, service.drive,
                                clock=lambda: start + 10)
    client.app.state.application_sync = restarted
    try:
        assert restarted.status()['gmail_checked_through'] == first['gmail_checked_through']
        client.post('/api/applications/sync'); second = finish(client)
        assert second['checked'] == 1 and second['review_count'] == 2
        assert service.mail.reads == ['ab10', 'ab11']
        assert service.mail.searches[-1][1:] == (start - 300, start + 10)
        restarted.clock = lambda: start + 5  # a backwards clock must not move the checkpoint back
        client.post('/api/applications/sync'); repeated = finish(client)
        assert repeated['checked'] == 0 and repeated['review_count'] == 2
        assert repeated['gmail_checked_through'] == second['gmail_checked_through']
        assert service.mail.reads == ['ab10', 'ab11']
    finally:
        restarted.close()
        client.app.state.application_sync = service


def test_failed_scan_keeps_boundary_and_retry_skips_already_read_reviews(client):
    start = 1800000000
    old = mail('ab12', 'Needs review')
    pending = mail('ab13', 'Thank you for applying for Engineer at Example.', thread='bb')
    service = setup(client, [[old, pending]])
    service.clock = lambda: start
    service.mail.messages['ab13'] = GoogleConnectionError('Read unavailable', kind='unavailable')
    client.post('/api/applications/sync'); failed = finish(client)
    assert failed['gmail'] == 'FAILED' and failed['gmail_checked_through'] is None
    assert failed['checked'] == failed['review_count'] == 1
    service.mail.messages['ab13'] = pending
    service.mail.reads.clear()
    client.post('/api/applications/sync'); resumed = finish(client)
    assert resumed['gmail'] == 'COMPLETED' and resumed['checked'] == resumed['created'] == 1
    assert service.mail.reads == ['ab13'] and resumed['review_count'] == 1
    boundary = resumed['gmail_checked_through']
    service.clock = lambda: start + 100
    service.mail.application_messages = lambda *args, **kwargs: (_ for _ in ()).throw(GoogleConnectionError('Unavailable'))
    client.post('/api/applications/sync'); failed_again = finish(client)
    assert failed_again['gmail_checked_through'] == boundary


def test_boundary_uses_scan_start_not_finish_or_sender_date_and_is_per_account(client):
    start = 1800000000
    old = mail('ab14', 'Unknown message')
    old['headers'][1]['value'] = '01 Oct 2099 12:00:00 +0200'
    during = {**mail('ab15', 'Newly arrived unknown message', thread='bb'), 'internal_date': str((start + 1) * 1000)}
    service = setup(client, [[old]])
    service.clock = lambda: start
    original = service.mail.application_message
    def receive_during_scan(message_id):
        result = original(message_id)
        service.clock = lambda: start + 100
        service.mail.pages[0].append(during)
        service.mail.messages[during['id']] = during
        return result
    service.mail.application_message = receive_during_scan
    client.post('/api/applications/sync'); first = finish(client)
    account = hashlib.sha256(b'person@example.com').hexdigest()
    with Session(service.engine) as session:
        assert session.get(MailSyncBoundary, account).checked_through == start
    service.mail.application_message = original
    client.post('/api/applications/sync'); second = finish(client)
    assert second['checked'] == 1 and service.mail.reads == ['ab14', 'ab15']
    service.google = SimpleNamespace(status=lambda: {'email': 'other@example.com', 'capabilities': {'gmail_read': True}})
    assert service.status()['gmail_checked_through'] is None
    service.mail = FakeMail([[mail('ab14', 'Unknown message')]])
    client.post('/api/applications/sync'); other = finish(client)
    assert other['checked'] == 1 and isinstance(service.mail.searches[-1][1], int)
    assert other['gmail_scan_from'] is not None


def test_boundary_overlap_picks_up_late_visibility_without_rereading_known_mail(client):
    start = 1800000000
    known = {**mail('ab16', 'Unknown message'), 'internal_date': str((start - 10) * 1000)}
    late = {**mail('ab17', 'Later visible message', thread='bb'), 'internal_date': str((start - 120) * 1000)}
    service = setup(client, [[known]])
    service.clock = lambda: start
    client.post('/api/applications/sync'); finish(client)
    service.mail.pages[0].append(late)
    service.mail.messages[late['id']] = late
    service.clock = lambda: start + 10
    client.post('/api/applications/sync'); result = finish(client)
    assert result['checked'] == 1 and result['review_count'] == 2
    assert service.mail.reads == ['ab16', 'ab17']


def test_gmail_sync_adapter_reads_paginated_html_without_attachments_or_mailbox_writes():
    import base64
    calls=[]
    def api(capability,method,path,**kwargs):
        calls.append((capability,method,path,kwargs))
        value={'messages':[{'id':'abcd'}],'nextPageToken':'next'} if path.endswith('/messages') else {
            'id':'abcd','threadId':'aa','internalDate':'1790850000000','payload':{'parts':[
                {'mimeType':'text/html','body':{'data':base64.urlsafe_b64encode(b'<p>Confirmation</p>').decode()}},
                {'mimeType':'text/plain','filename':'private.txt','body':{'data':base64.urlsafe_b64encode(b'attachment').decode()}}]}}
        return httpx.Response(200, json=value)
    provider=GoogleMailProvider(SimpleNamespace(api=api))
    assert provider.application_messages('previous', after=1790000000, before=1791000000)['nextPageToken']=='next'
    message=provider.application_message('abcd')
    assert '<p>Confirmation</p>' in message['content'] and 'attachment' not in message['content']
    assert calls[0][3]['params']['pageToken']=='previous'
    assert calls[0][3]['params']['q'].endswith(' after:1790000000 before:1791000000')
    assert all(call[:2]==('gmail_read','GET') for call in calls)


def test_empty_gmail_projection_is_no_new_mail_and_malformed_results_are_not_success():
    params = []
    def empty(*args, **kwargs):
        params.append(kwargs['params'])
        return httpx.Response(204)
    provider = GoogleMailProvider(SimpleNamespace(api=empty))
    assert provider.application_messages(after=1790000000, before=1791000000) == {}
    assert 'resultSizeEstimate' in params[0]['fields']
    for response in (httpx.Response(200, content=b''), httpx.Response(200, json=None)):
        provider = GoogleMailProvider(SimpleNamespace(api=lambda *args, **kwargs: response))
        with pytest.raises(GoogleConnectionError, match='unreadable search result'):
            provider.application_messages()


@pytest.mark.parametrize('label,created',[('Alternance Engineer',True),("Voir l’offre d’emploi",False)])
def test_iscod_import_uses_a_named_role_never_a_generic_link_label(client,label,created):
    body=f"<p>Votre CV a été envoyé à l’entreprise Example - IT qui recherche un alternant ! Équipe ISCOD.</p><a href='https://www.iscod.fr/offres-emploi-en-alternance/engineer-123'>{label}</a>"
    message=mail('abce',body)
    message['headers'][1]['value']='01 Oct 2026 23:30:00 -0400'
    account=hashlib.sha256(b'person@example.com').hexdigest()
    first=mailbox_import.reconcile(client.app.state.engine,client.app.state.settings,account,message)
    assert first[1] is created
    records=client.get('/api/applications').json()
    if created:
        assert records[0]['job_title']==label and records[0]['date_applied']=='2026-10-01'
        assert records[0]['status']=='SUBMITTED'
    else:
        assert not records


@pytest.mark.parametrize('months', [0, 121, 1.5, True, None])
def test_initial_scan_months_are_validated_before_any_work_is_started(client, months):
    service = setup(client, [[]])
    response = client.post('/api/applications/sync', json={'lookback_months': months})
    assert response.status_code == 422
    assert service.mail.searches == []
    with Session(service.engine) as session:
        assert session.scalar(select(func.count()).select_from(MailSyncScope)) == 0


def test_first_scan_defaults_to_three_calendar_months_and_excludes_older_mail(client):
    from app.application_sync import months_before
    start = int(datetime(2026, 10, 28, 12, tzinfo=timezone.utc).timestamp())
    floor = months_before(start, 3, 'Europe/Paris')
    older = {**mail('fa01', 'Too old'), 'internal_date': str((floor - 1) * 1000)}
    recent = {**mail('fa02', 'Recent unknown message'), 'internal_date': str((floor + 1) * 1000)}
    service = setup(client, [[recent, older]])
    service.clock = lambda: start
    assert service.status()['initial_scan_required']
    client.post('/api/applications/sync'); value = finish(client)
    assert value['checked'] == 1 and service.mail.reads == ['fa02']
    assert service.mail.searches[0][1:] == (floor, start)
    assert value['lookback_months'] == 3 and not value['initial_scan_required']
    assert datetime.fromisoformat(value['gmail_scan_from'].replace('Z', '+00:00')).timestamp() == floor


def test_first_scan_choice_survives_caps_restart_and_a_later_different_option(client):
    from app.application_sync import ApplicationSync, months_before
    start = int(datetime(2026, 10, 28, 12, tzinfo=timezone.utc).timestamp())
    service = setup(client, [[mail('fa03', 'Unknown message'), mail('fa04', 'Another message')]])
    service.clock = lambda: start
    save_mail_limit(client, 1)
    client.post('/api/applications/sync', json={'lookback_months': 1}); first = finish(client)
    assert first['limit_reached'] and first['gmail_checked_through'] is None
    assert not first['initial_scan_required'] and first['lookback_months'] == 1
    restarted = ApplicationSync(service.engine, service.settings, service.google, service.mail, service.drive,
                                clock=lambda: start + 86400 * 30)
    client.app.state.application_sync = restarted
    try:
        assert restarted.status()['gmail_scan_from'] == first['gmail_scan_from']
        client.post('/api/applications/sync', json={'lookback_months': 12}); second = finish(client)
        assert second['gmail'] == 'COMPLETED' and second['lookback_months'] == 1
        assert service.mail.searches[-1][1] == months_before(start, 1, 'Europe/Paris')
        assert service.mail.reads == ['fa03', 'fa04']
    finally:
        restarted.close()
        client.app.state.application_sync = service


def test_existing_completed_accounts_do_not_need_a_new_first_scan_choice(client):
    service = setup(client, [[]])
    account = hashlib.sha256(b'person@example.com').hexdigest()
    with Session(service.engine) as session:
        session.add(MailSyncBoundary(account=account, checked_through=1800000000)); session.commit()
    service.clock = lambda: 1800000100
    assert not service.status()['initial_scan_required']
    client.post('/api/applications/sync', json={'lookback_months': 1}); finish(client)
    assert service.mail.searches[0][1:] == (1800000000 - 300, 1800000100)
    with Session(service.engine) as session:
        assert session.get(MailSyncScope, account) is None


@pytest.mark.parametrize(('start', 'months', 'expected'), [
    ('2026-05-31T10:00:00+02:00', 3, '2026-02-28T10:00:00+01:00'),
    ('2024-03-31T10:00:00+02:00', 1, '2024-02-29T10:00:00+01:00'),
    ('2026-01-15T10:00:00+01:00', 3, '2025-10-15T10:00:00+02:00'),
])
def test_month_lookback_uses_calendar_months_and_workspace_timezone(start, months, expected):
    from app.application_sync import months_before
    assert months_before(datetime.fromisoformat(start).timestamp(), months, 'Europe/Paris') == datetime.fromisoformat(expected).timestamp()


def test_different_provider_confirmations_sharing_a_gmail_thread_remain_distinct(client):
    first = mail('fa05', 'Application submitted Engineer Acme - Paris The following items were sent to Acme. Good luck!', thread='shared')
    second = mail('fa06', 'Application submitted Developer Other - Lyon The following items were sent to Other. Good luck!', thread='shared')
    service = setup(client, [[first, second]])
    client.post('/api/applications/sync'); value = finish(client)
    records = client.get('/api/applications').json()
    assert value['created'] == 2 and {r['company'] for r in records} == {'Acme', 'Other'}
    with Session(service.engine) as session:
        events = list(session.scalars(select(TimelineEvent).where(TimelineEvent.actor_reference == 'gmail-sync', TimelineEvent.event_type == 'MANUAL')))
        assert len(events) == 2 and all(e.event_metadata['mail_scanner'] == 'indeed' for e in events)
    client.post('/api/applications/sync'); repeated = finish(client)
    assert repeated['created'] == repeated['updated'] == repeated['checked'] == 0


def test_first_scan_lower_bound_survives_a_failed_read(client):
    start = int(datetime(2026, 10, 28, 12, tzinfo=timezone.utc).timestamp())
    message = mail('fa07', 'Unrecognized template')
    service = setup(client, [[message]])
    service.clock = lambda: start
    service.mail.messages['fa07'] = GoogleConnectionError('Temporary outage', kind='unavailable')
    client.post('/api/applications/sync', json={'lookback_months': 2}); failed = finish(client)
    assert failed['gmail'] == 'FAILED' and failed['gmail_checked_through'] is None
    assert not failed['initial_scan_required'] and failed['lookback_months'] == 2
    service.mail.messages['fa07'] = message
    service.clock = lambda: start + 86400 * 31
    client.post('/api/applications/sync', json={'lookback_months': 12}); finished = finish(client)
    assert finished['gmail'] == 'COMPLETED' and finished['gmail_scan_from'] == failed['gmail_scan_from']
    assert service.mail.searches[0][1] == service.mail.searches[-1][1]


def test_account_change_during_preflight_never_applies_the_first_account_scope_to_the_new_one(client):
    service = setup(client, [[mail('fa08', 'Unrecognized template')]])
    def switch_account(**_):
        service.google = SimpleNamespace(status=lambda: {'email': 'other@example.com', 'capabilities': {'gmail_read': True}})
        return {'running': False, 'conflicts': 0}
    service.drive.run = switch_account
    client.post('/api/applications/sync', json={'lookback_months': 6}); value = finish(client)
    assert value['gmail'] == 'FAILED' and service.mail.searches == service.mail.reads == []
    assert value['initial_scan_required'] and value['gmail_scan_from'] is None
    with Session(service.engine) as session:
        assert session.get(MailSyncScope, hashlib.sha256(b'person@example.com').hexdigest()).lookback_months == 6
        assert session.get(MailSyncScope, hashlib.sha256(b'other@example.com').hexdigest()) is None


def test_french_freework_confirmation_and_reply_share_reconciliation_and_audit_language(client):
    confirmation = mail('fa09', 'Votre candidature au poste Engineer chez Acme a bien été envoyée.')
    rejection = mail('fa10', 'Votre candidature n’a pas été retenue.', day=2)
    for message in (confirmation, rejection):
        message['headers'].append({'name': 'From', 'value': 'contact@free-work.com'})
    service = setup(client, [[confirmation, rejection]])
    client.post('/api/applications/sync'); value = finish(client)
    assert value['created'] == 1 and value['review_count'] == 0
    record = client.get('/api/applications').json()[0]
    assert (record['company'], record['job_title'], record['status'], record['outcome']) == ('Acme', 'Engineer', 'CLOSED', 'UNSUCCESSFUL')
    with Session(service.engine) as session:
        events = list(session.scalars(select(TimelineEvent).where(TimelineEvent.actor_reference == 'gmail-sync', TimelineEvent.event_type == 'MANUAL')))
        assert len(events) == 2
        assert all(event.event_metadata['mail_scanner'] == 'freework' and event.event_metadata['mail_language'] == 'fr' for event in events)


def test_cached_matching_reuses_one_scan_per_message_without_extra_reads(client, monkeypatch):
    from app import mailbox_evidence
    scans = []
    original = mailbox_evidence.scan_email
    def counted_scan(*args, **kwargs):
        scans.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(mailbox_evidence, 'scan_email', counted_scan)
    service = setup(client, [[mail('fb01', 'Your application was unsuccessful.', day=2),
                             mail('fb02', 'Thank you for applying for Engineer at Example.')]])
    client.post('/api/applications/sync'); value = finish(client)
    assert value['created'] == 1 and value['review_count'] == 0
    assert service.mail.reads == ['fb01', 'fb02'] and len(scans) == 2
    assert client.get('/api/applications').json()[0]['outcome'] == 'UNSUCCESSFUL'


def test_ambiguous_strong_references_cannot_be_disambiguated_by_a_weaker_role_match(client):
    first = seed(client)
    second = client.post('/api/applications', json={'company': 'Another', 'job_title': 'Developer',
        'date_applied': '2026-10-01', 'email_reference': '[Gmail:fb03]'}).json()
    client.patch('/api/applications/' + first['id'], json={'email_reference': '[Gmail:fb03]'})
    setup(client, [[mail('fb03', 'Thank you for applying for Developer at Another.')]])
    client.post('/api/applications/sync'); value = finish(client)
    assert value['created'] == value['updated'] == 0 and value['review_count'] == 1
    assert 'Several applications' in value['reviews'][0]['reason']
    assert {record['id'] for record in client.get('/api/applications').json()} == {first['id'], second['id']}


def test_recent_mail_cannot_import_an_application_dated_before_2026(client):
    old_application = mail('fc01', 'Your application was sent to Acme Engineer Acme · Paris Applied on May 1, 2022')
    service = setup(client, [[old_application]])
    client.post('/api/applications/sync'); result = finish(client)
    assert result['checked'] == 1 and result['created'] == result['updated'] == 0
    assert client.get('/api/applications').json() == []
    with Session(service.engine) as session:
        receipt = session.get(MailImportReceipt, (hashlib.sha256(b'person@example.com').hexdigest(), 'fc01'))
        assert receipt.state == 'IGNORED' and '2026-01-01' in receipt.reason


def test_legacy_completed_account_search_always_has_the_absolute_mail_boundary(client):
    from app.mailbox_evidence import mail_boundary_timestamp
    service = setup(client, [[]])
    account = hashlib.sha256(b'person@example.com').hexdigest()
    with Session(service.engine) as session:
        session.add(MailSyncBoundary(account=account, checked_through=1600000000)); session.commit()
    client.post('/api/applications/sync'); finish(client)
    floor = mail_boundary_timestamp(client.get('/api/settings/general').json())
    assert service.mail.searches[0][1] == floor - 1


@pytest.mark.parametrize('boundary', ['2025-12-31', '2026-02-30', 'bad', None])
def test_invalid_or_pre2026_mail_boundaries_are_rejected(client, boundary):
    general = client.get('/api/settings/general').json()
    revision = general.pop('revision')
    response = client.put('/api/settings/general', json={**general, 'mail_sync_not_before': boundary, 'expected_revision': revision})
    assert response.status_code == 422
    assert client.get('/api/settings/general').json()['mail_sync_not_before'] == '2026-01-01'


def test_an_older_trashed_vacancy_does_not_block_a_new_2026_application(client):
    previous = client.post('/api/applications', json={'company':'Example', 'job_title':'Engineer',
        'date_applied':'2022-01-01', 'email_reference':'Old application'}).json()
    client.delete('/api/applications/' + previous['id'])
    setup(client, [[mail('fc02', 'Thank you for applying for Engineer at Example.')]])
    client.post('/api/applications/sync'); value = finish(client)
    assert value['created'] == 1
    current = client.get('/api/applications').json()
    assert len(current) == 1 and current[0]['id'] != previous['id'] and current[0]['date_applied'] == '2026-10-01'
