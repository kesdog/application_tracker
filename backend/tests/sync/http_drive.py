"""Synthetic Drive HTTP boundary shared by end-to-end tests and profiling.

Uses the production GoogleConnection/DriveTransport, with no network or consent.
"""
import json
from email import policy
from email.parser import BytesParser
from uuid import uuid4

import httpx


class DriveHttpStore:
    def __init__(self, page_size=2):
        self.files, self.feed = {}, []
        self.page_size = page_size
        self.offline = False
        self.rate_limit_next = False
        self.lose_upload_response = False
        self.calls = []
        self.upload_bytes = self.download_bytes = 0

    def metadata(self, file_id):
        name, content = self.files[file_id]
        return {'id': file_id, 'name': name, 'size': str(len(content)), 'quotaBytesUsed': str(len(content))}

    def request(self, request):
        path = request.url.path
        self.calls.append((request.method, path))
        if request.headers.get('authorization') not in {'Bearer test-left', 'Bearer test-right'}:
            return httpx.Response(401, json={'error': {'errors': [{'reason': 'authError'}]}})
        if self.offline:
            return httpx.Response(503, json={'error': {'errors': [{'reason': 'backendError'}]}})
        if self.rate_limit_next:
            self.rate_limit_next = False
            return httpx.Response(403, json={'error': {'errors': [{'reason': 'userRateLimitExceeded'}]}}, headers={'Retry-After': '1'})
        query = request.url.params
        if path == '/drive/v3/changes/startPageToken':
            return httpx.Response(200, json={'startPageToken': str(len(self.feed))})
        if path == '/drive/v3/files' and request.method == 'GET':
            assert query['spaces'] == 'appDataFolder'
            offset = int(query.get('pageToken', '0'))
            ids = list(self.files)[offset:offset + self.page_size]
            value = {'files': [self.metadata(file_id) for file_id in ids]}
            if offset + len(ids) < len(self.files):
                value['nextPageToken'] = str(offset + len(ids))
            return httpx.Response(200, json=value)
        if path == '/drive/v3/changes':
            assert query['spaces'] == 'appDataFolder'
            if query['pageToken'] == 'expired':
                return httpx.Response(410, json={'error': {'code': 410}})
            offset = int(query['pageToken'])
            entries = self.feed[offset:offset + self.page_size]
            value = {'changes': [{'fileId': file_id, 'removed': removed,
                **({} if removed else {'file': self.metadata(file_id)})} for file_id, removed in entries]}
            value['nextPageToken' if offset + len(entries) < len(self.feed) else 'newStartPageToken'] = str(offset + len(entries))
            return httpx.Response(200, json=value)
        if path == '/upload/drive/v3/files' and request.method == 'POST':
            assert query['uploadType'] == 'multipart'
            message = BytesParser(policy=policy.default).parsebytes(
                ('Content-Type: ' + request.headers['content-type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + request.content)
            parts = list(message.iter_parts())
            metadata, value = json.loads(parts[0].get_payload(decode=True)), parts[1].get_payload(decode=True)
            assert metadata['parents'] == ['appDataFolder']
            file_id = uuid4().hex
            self.files[file_id] = (metadata['name'], value)
            self.feed.append((file_id, False))
            self.upload_bytes += len(value)
            if self.lose_upload_response:
                self.lose_upload_response = False
                raise httpx.ReadTimeout('Synthetic response lost after commit')
            return httpx.Response(200, json={'id': file_id})
        if path.startswith('/drive/v3/files/'):
            file_id = path.rsplit('/', 1)[1]
            if file_id not in self.files:
                return httpx.Response(404, json={'error': {'code': 404}})
            if request.method == 'GET' and query.get('alt') == 'media':
                value = self.files[file_id][1]
                self.download_bytes += len(value)
                return httpx.Response(200, content=value)
        raise AssertionError('Unexpected synthetic Drive request: ' + request.method + ' ' + path)
