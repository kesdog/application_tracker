from copy import deepcopy
from datetime import datetime
import hashlib
from threading import Event
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import mailbox_import
from app.google_connection import GoogleConnectionError, GoogleMailProvider
from app.models import Application, MailImportReceipt


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
    def application_messages(self, token):
        page = int(token or 0)
        return {'messages':[{'id':item['id']} for item in self.pages[page]], **({'nextPageToken':str(page+1)} if page+1<len(self.pages) else {})}
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
    def blocked(token):
        started.set(); gate.wait(3); return original(token)
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


def test_gmail_sync_adapter_reads_paginated_html_without_attachments_or_mailbox_writes():
    import base64
    calls=[]
    def api(capability,method,path,**kwargs):
        calls.append((capability,method,path,kwargs))
        value={'messages':[{'id':'abcd'}],'nextPageToken':'next'} if path.endswith('/messages') else {
            'id':'abcd','threadId':'aa','internalDate':'1790850000000','payload':{'parts':[
                {'mimeType':'text/html','body':{'data':base64.urlsafe_b64encode(b'<p>Confirmation</p>').decode()}},
                {'mimeType':'text/plain','filename':'private.txt','body':{'data':base64.urlsafe_b64encode(b'attachment').decode()}}]}}
        return SimpleNamespace(json=lambda:value)
    provider=GoogleMailProvider(SimpleNamespace(api=api))
    assert provider.application_messages('previous')['nextPageToken']=='next'
    message=provider.application_message('abcd')
    assert '<p>Confirmation</p>' in message['content'] and 'attachment' not in message['content']
    assert calls[0][3]['params']['pageToken']=='previous'
    assert all(call[:2]==('gmail_read','GET') for call in calls)


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
