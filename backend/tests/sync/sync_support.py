"""Reusable simulated transport/storage adapters for offline tests and profiling."""
from uuid import uuid4
from datetime import date

from sqlalchemy.orm import Session

from app.models import Application
from app.sync.models import SyncRecord

from tests.support import MemorySecrets


class ObjectStore:
    def __init__(self):
        self.files, self.feed = {}, []
        self.account = 'verified-google-sub'
        self.failure = None
        self.lose_upload_response = False
        self.downloads = 0
    def identity(self):
        return self.account
    def start_cursor(self):
        return str(len(self.feed))
    def list_files(self):
        return [{'id': key, 'name': 'tracker-sync-v1-' + name, 'size': str(len(value))} for key, (name, value) in self.files.items()]
    def download(self, file_id):
        self.downloads += 1
        return self.files[file_id][1]
    def upload_immutable(self, batch_id, value):
        if self.failure:
            raise self.failure
        key = str(uuid4())
        self.files[key] = (batch_id, value)
        self.feed.append(key)
        if self.lose_upload_response:
            self.lose_upload_response = False
            raise OSError('response lost after successful upload')
        return key
    def changes(self, cursor):
        if self.failure:
            raise self.failure
        ids = self.feed[int(cursor):]
        return ([{'id': key, 'name': 'tracker-sync-v1-' + self.files[key][0], 'size': str(len(self.files[key][1]))} for key in ids],
                [], str(len(self.feed)), False)


def create_application(replica, company='Company', **extra):
    with Session(replica.engine) as session:
        item = Application(company=company, job_title='Engineer', date_applied=date(2026, 10, 20),
            job_url='https://example.com/job', **extra)
        session.add(item)
        session.commit()
        return item.id


def update(replica, entity_id, **changes):
    with Session(replica.engine) as session:
        item = session.get(Application, entity_id)
        for key, value in changes.items():
            setattr(item, key, value)
        session.commit()


def state(replica, entity_id):
    with Session(replica.engine) as session:
        record = session.get(SyncRecord, 'application:' + entity_id)
        return dict(record.state)


def paired(replicas):
    factory, store = replicas
    desktop, second = factory('desktop'), factory('second')
    export = desktop.initialize('Desktop')['recovery_export']
    entity_id = create_application(desktop)
    assert desktop.run()['error'] is None
    second.initialize('Second', export)
    assert second.run()['error'] is None
    return desktop, second, entity_id, store


def converge(*replicas):
    for _ in range(2):
        for replica in replicas:
            result = replica.run(manual=True)
            assert result['error'] is None, result
