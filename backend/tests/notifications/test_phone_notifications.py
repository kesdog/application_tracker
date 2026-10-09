import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import push
from app.backup import backup_workspace, restore_workspace
from app.config import Settings
from app.database import create_database
from app.human_auth import hash_password
from app.main import create_app
from app.models import FollowUp, FollowUpNotice, PushDelivery, PushDevice

NOW = datetime(2026, 10, 9, 10)
ORIGIN = 'https://tracker.example.test'
PASSWORD = 'test phone workspace password'


@pytest.fixture(scope='module')
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture
def context(tmp_path, password_hash):
    path = tmp_path / 'vapid.pem'
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    config = Settings(_env_file=None, app_mode='hosted', app_public_url=ORIGIN, app_password_hash=password_hash,
        app_data_dir=tmp_path / 'data', app_push_vapid_key_file=path, app_push_contact='mailto:admin@example.com')
    # Service tests control the clock and network sender explicitly; the local app worker is disabled.
    with TestClient(create_app(Settings(_env_file=None, app_data_dir=config.app_data_dir))) as client:
        values = client.get('/api/settings/general').json()
        values.pop('revision')
        client.put('/api/settings/general', json={**values,'daily_digest':False})
        yield client, client.app.state.engine, config


def subscription(index=1):
    key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    encode = lambda value: base64.urlsafe_b64encode(value).decode().rstrip('=')
    return push.SubscriptionInput(endpoint=f'https://fcm.googleapis.com/fcm/send/device-{index}', keys={'p256dh':encode(key),'auth':encode(bytes(range(16)))}, label=f'Phone {index}')


def add_device(engine, config, index=1):
    with Session(engine) as session:
        return push.subscribe(session, config, subscription(index))['id']


def application(client, name='Private Employer'):
    item = client.post('/api/applications',json={'company':name,'job_title':'Private role','date_applied':'2026-10-01','email_reference':'Ref'}).json()
    followup = client.get(f"/api/applications/{item['id']}/work").json()['followups'][0]
    return item, followup


def deliveries(engine):
    with Session(engine) as session:
        return session.scalars(select(PushDelivery).order_by(PushDelivery.created_at,PushDelivery.id)).all()


def preferences(client, **changes):
    values = client.get('/api/settings/general').json()
    values.pop('revision')
    assert client.put('/api/settings/general',json={**values,**changes}).status_code == 200


def test_push_configuration_and_subscription_validation(context):
    _, engine, config = context
    with pytest.raises(ValueError):
        Settings(_env_file=None,app_push_vapid_key_file=config.app_push_vapid_key_file,app_push_contact='mailto:admin@example.com')
    for endpoint in ('http://fcm.googleapis.com/test','https://127.0.0.1/test','https://evil.test/test',
                     'https://fcm.googleapis.com:8080/test','https://user@fcm.googleapis.com/test','https://fcm.googleapis.com.evil.test/test'):
        with pytest.raises(ValueError):
            push.SubscriptionInput(**{**subscription().model_dump(), 'endpoint':endpoint})
    for key in ('wrong',base64.urlsafe_b64encode(bytes(65)).decode()):
        with pytest.raises(ValueError):
            push.SubscriptionInput(**{**subscription().model_dump(), 'keys':{'auth':'bad','p256dh':key}})
    first = add_device(engine,config)
    assert add_device(engine,config) == first
    with Session(engine) as session:
        status = push.status(session,config)
    serialized = json.dumps(status,default=str)
    assert len(status['devices']) == 1 and status['public_key']
    assert 'fcm.googleapis.com' not in serialized and 'p256dh' not in serialized


def test_grouped_delivery_preserves_message_and_deduplicates_after_restart(context):
    client,engine,config = context
    add_device(engine,config)
    app,item = application(client)
    application(client,'Second private company')
    sent = []
    sender = lambda _, sub, payload: (sent.append(payload) or 201,None)
    push.PushScheduler(engine,config,sender).refresh(NOW)
    assert len(sent) == 1 and '2 follow-ups' in sent[0]['body'] and sent[0]['url'] == '/#/followups'
    assert 'Private' not in json.dumps(sent)
    restarted_engine = create_database(config.app_data_dir)
    try:
        push.PushScheduler(restarted_engine,config,sender).refresh(NOW+timedelta(minutes=1))
    finally:
        restarted_engine.dispose()
    assert len(sent) == 1 and deliveries(engine)[0].state == 'ACCEPTED'
    assert client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]['status'] == 'PREPARED'
    with Session(engine) as session:
        assert all(not notice.read_at for notice in session.scalars(select(FollowUpNotice)))


def test_exact_message_link_and_daily_digest_catches_up_new_work(context):
    client,engine,config=context
    add_device(engine,config)
    preferences(client,daily_digest=True)
    app,item=application(client)
    sent=[]
    runner=push.PushScheduler(engine,config,lambda _,sub,payload:(sent.append(payload) or 201,None))
    runner.refresh(NOW)
    assert sent[0]['url'] == f"/#/followups/{app['id']}/{item['id']}"
    application(client,'Late import')
    runner.refresh(NOW+timedelta(minutes=1))
    assert len(sent)==1
    runner.refresh(NOW+timedelta(days=1))
    assert len(sent)==2


def test_quiet_hours_disabled_reminders_and_digest_time_defer_delivery(context):
    client,engine,config=context
    add_device(engine,config); application(client)
    sent=[]
    runner=push.PushScheduler(engine,config,lambda _,sub,payload:(sent.append(payload) or 201,None))
    runner.refresh(datetime(2026,10,9,21))
    assert not sent
    preferences(client,notifications_enabled=False)
    runner.refresh(NOW)
    assert not sent
    preferences(client,notifications_enabled=True,daily_digest=True,reminder_time='15:00')
    runner.refresh(NOW)
    assert not sent
    runner.refresh(datetime(2026,10,9,14))
    assert len(sent)==1


@pytest.mark.parametrize('change',['sent','paused','closed','snoozed','archived','dismissed','deleted'])
def test_current_job_state_suppresses_queued_delivery(context,change):
    client,engine,config=context
    add_device(engine,config)
    app,item=application(client)
    push.enqueue(engine,config,NOW)
    child=f"/api/applications/{app['id']}/followups/{item['id']}"
    if change=='sent':
        assert client.patch(child,json={'status':'SENT','expected_revision':item['revision']}).status_code==200
    elif change=='paused': client.patch(f"/api/applications/{app['id']}",json={'followup_paused':True})
    elif change=='closed': client.patch(f"/api/applications/{app['id']}",json={'status':'CLOSED'})
    elif change=='snoozed': client.patch(child,json={'snoozed_until':'2026-10-20T09:00:00Z'})
    elif change=='archived': client.patch(child,json={'archived':True})
    elif change=='deleted': client.delete(f"/api/applications/{app['id']}")
    else:
        with Session(engine) as session:
            notice=session.scalar(select(FollowUpNotice).where(FollowUpNotice.followup_id==item['id']))
            notice.read_at=NOW;session.commit()
    sent=[]
    push.PushScheduler(engine,config,lambda _,sub,payload:(sent.append(payload) or 201,None)).refresh(NOW)
    assert not sent
    assert deliveries(engine)[0].state=='CANCELLED'


def test_retry_after_network_failure_and_lease_recovery(context):
    client,engine,config=context
    add_device(engine,config);application(client)
    calls=[]
    def sender(_,sub,payload):
        calls.append(payload)
        return (429,'120') if len(calls)==1 else (201,None)
    runner=push.PushScheduler(engine,config,sender)
    runner.refresh(NOW)
    assert deliveries(engine)[0].state=='RETRY'
    runner.refresh(NOW+timedelta(seconds=60));assert len(calls)==1
    runner.refresh(NOW+timedelta(seconds=120));assert len(calls)==2
    assert calls[0]['tag']==calls[1]['tag'] and deliveries(engine)[0].state=='ACCEPTED'
    app,item=application(client,'Lease example')
    push.enqueue(engine,config,NOW+timedelta(minutes=5))
    first=push.claim(engine,config,NOW+timedelta(minutes=5))
    assert first
    assert push.claim(engine,config,NOW+timedelta(minutes=6)) is None
    reclaimed=push.claim(engine,config,NOW+timedelta(minutes=8))
    assert reclaimed['id']==first['id'] and reclaimed['lease']!=first['lease']
    push.finish(engine,first,201,None,NOW+timedelta(minutes=8))
    assert deliveries(engine)[-1].state=='INFLIGHT'
    push.finish(engine,reclaimed,201,None,NOW+timedelta(minutes=8))
    assert deliveries(engine)[-1].state=='ACCEPTED'


def test_expired_devices_and_retry_exhaustion_do_not_remove_in_app_notices(context):
    client,engine,config=context
    first=add_device(engine,config);second=add_device(engine,config,2);application(client)
    def sender(_,sub,payload):
        if sub['endpoint'].endswith('device-1'):return 410,None
        raise RuntimeError('sensitive endpoint or secret must not be persisted')
    runner=push.PushScheduler(engine,config,sender)
    runner.refresh(NOW)
    for offset in (2,6,15,30,60):runner.refresh(NOW+timedelta(minutes=offset))
    with Session(engine) as session:
        assert not session.get(PushDevice,first).active and session.get(PushDevice,second).active
        assert all(item.state=='FAILED' for item in session.scalars(select(PushDelivery)))
        assert 'sensitive' not in json.dumps(push.status(session,config),default=str)
        assert followups_available(session,NOW)


def followups_available(session,now):
    push.followup_reminders.synchronize(session,now)
    return push.followup_reminders.notices(session)


def test_enqueue_and_claim_are_transactional_between_workers(context):
    client,engine,config=context
    add_device(engine,config);application(client)
    with ThreadPoolExecutor(max_workers=2) as workers:
        list(workers.map(lambda _:push.enqueue(engine,config,NOW),range(2)))
        claims=list(workers.map(lambda _:push.claim(engine,config,NOW),range(2)))
    assert len(deliveries(engine))==1 and sum(bool(item) for item in claims)==1


def test_device_limit_and_vapid_rotation_require_fresh_opt_in(context,tmp_path):
    _,engine,config=context
    for index in range(20):add_device(engine,config,index)
    with Session(engine) as session:
        with pytest.raises(Exception) as limited:
            push.subscribe(session,config,subscription(21))
        assert limited.value.status_code==409
    assert add_device(engine,config,0)
    replacement=tmp_path/'replacement-vapid.pem'
    replacement.write_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    changed=config.model_copy(update={'app_push_vapid_key_file':replacement})
    with Session(engine) as session:
        state=push.status(session,changed)
        assert all(not item['active'] and 'key changed' in item['reason'] for item in state['devices'])


def test_push_crypto_sends_encrypted_payload_without_redirects(context,monkeypatch):
    import requests
    _,_,config=context
    captured=[]
    def request(self,method,url,**kwargs):
        captured.append((method,url,kwargs))
        response=requests.Response();response.status_code=201;response._content=b''
        return response
    monkeypatch.setattr(requests.Session,'request',request)
    data=subscription().model_dump()
    assert push.send(config,{'endpoint':data['endpoint'],'keys':data['keys']},{'tag':'tracker-test','body':'private reminder'})==(201,None)
    options=captured[0][2]
    assert options['allow_redirects'] is False and options['timeout']==10
    assert b'private reminder' not in options['data'] and 'Authorization' in options['headers']


def test_notification_routes_require_human_auth_and_test_requests_are_limited(context):
    _,_,config=context
    with TestClient(create_app(config,push_sender=lambda *args:(201,None)),base_url=ORIGIN) as client:
        assert client.get('/api/settings/notifications').status_code==401
        assert client.post('/api/settings/notifications/devices',json=subscription().model_dump()).status_code==401
        client.post('/api/auth/login',json={'password':PASSWORD},headers={'Origin':ORIGIN})
        headers={'Origin':ORIGIN,'X-CSRF-Token':client.get('/api/auth/session').json()['csrf_token']}
        assert client.post('/api/settings/notifications/devices',json=subscription().model_dump()).status_code==403
        device=client.post('/api/settings/notifications/devices',json=subscription().model_dump(),headers=headers).json()
        test=f"/api/settings/notifications/devices/{device['id']}/test"
        assert client.post(test,headers=headers).status_code==202
        assert client.post(test,headers=headers).status_code==429
        assert client.delete(f"/api/settings/notifications/devices/{device['id']}",headers=headers).status_code==204


def test_calendar_fallback_and_restore_require_new_device_opt_in(context,tmp_path):
    client,engine,config=context
    add_device(engine,config)
    app,item=application(client,'Comma, Newline\nCompany')
    url=f"/api/applications/{app['id']}/followups/{item['id']}/calendar.ics"
    calendar=client.get(url)
    assert calendar.status_code==200 and 'BEGIN:VALARM' in calendar.text
    unfolded = calendar.text.replace('\r\n ', '')
    assert 'Comma\\, Newline\\nCompany' in unfolded and f"/#/followups/{app['id']}/{item['id']}" in unfolded
    assert client.get(f"/api/applications/{app['id']}/work").json()['followups'][0]['status']=='PREPARED'
    backup=tmp_path/'full-backup';target=tmp_path/'restored'
    backup_workspace(config.app_data_dir,backup);restore_workspace(backup,target)
    with Session(create_database(target)) as session:
        assert session.scalars(select(PushDevice)).all()==[]
        assert session.scalars(select(FollowUp)).all()
