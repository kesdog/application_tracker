"""Narrow Drive adapter. No domain service imports or shared mutable manifest."""
import json
import secrets

from sqlalchemy.orm import Session

from app.google_connection import GoogleConnectionError, SCOPES
from app.models import ExternalConnection

PREFIX = 'tracker-sync-v1-'


class DriveTransport:
    def __init__(self, connection):
        self.connection = connection

    def identity(self):
        with Session(self.connection.engine) as session:
            account = session.get(ExternalConnection, 1)
            if not account or account.status not in {'CONNECTED', 'PARTIAL'} or SCOPES['drive'] not in account.scopes or not account.subject:
                raise GoogleConnectionError('Connect Google with Drive app data permission before syncing')
            return account.subject

    def start_cursor(self):
        return self.connection.api('drive', 'GET', 'drive/v3/changes/startPageToken').json()['startPageToken']

    def list_files(self):
        token = None
        files = []
        while True:
            params = {'spaces': 'appDataFolder', 'q': 'trashed=false', 'pageSize': 1000,
                      'fields': 'nextPageToken,files(id,name,size,quotaBytesUsed,appProperties)'}
            if token:
                params['pageToken'] = token
            page = self.connection.api('drive', 'GET', 'drive/v3/files', params=params).json()
            files.extend(item for item in page.get('files', []) if item.get('name', '').startswith(PREFIX))
            token = page.get('nextPageToken')
            if not token:
                return files

    def changes(self, cursor):
        page = self.connection.api('drive', 'GET', 'drive/v3/changes', params={
            'pageToken': cursor, 'spaces': 'appDataFolder', 'pageSize': 1000,
            'fields': 'nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,size,quotaBytesUsed))'}).json()
        files = [item['file'] for item in page.get('changes', []) if not item.get('removed') and item.get('file', {}).get('name', '').startswith(PREFIX)]
        removed = [item['fileId'] for item in page.get('changes', []) if item.get('removed')]
        return files, removed, page.get('nextPageToken') or page.get('newStartPageToken'), bool(page.get('nextPageToken'))

    def download(self, file_id):
        response = self.connection.api('drive', 'GET', f'drive/v3/files/{file_id}', params={'alt': 'media'})
        return response.content

    def upload_immutable(self, batch_id, value):
        # A retry reuses the persisted batch ID; duplicate Drive names are safe.
        # The inbox checks the authenticated internal ID/content, never its name.
        boundary = 'sync-' + secrets.token_hex(16)
        metadata = json.dumps({'name': PREFIX + batch_id, 'parents': ['appDataFolder'],
                               'appProperties': {'protocol': 'tracker-sync-v1'}}).encode()
        body = (f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode() + metadata
                + f'\r\n--{boundary}\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + value
                + f'\r\n--{boundary}--\r\n'.encode())
        return self.connection.api('drive', 'POST', 'upload/drive/v3/files', params={'uploadType': 'multipart', 'fields': 'id'},
            content=body, headers={'Content-Type': 'multipart/related; boundary=' + boundary}).json()['id']
