"""Python/browser interoperable gzip + AES-256-GCM envelope, bounded decoding."""
import base64
import gzip
import hashlib
import hmac
import json
import secrets
import zlib
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.sync.schemas import Batch

MAX_PLAINTEXT = 64 * 1024 * 1024
MAX_ENCRYPTED = MAX_PLAINTEXT + 1024 * 1024


def encode_key(key: bytes) -> str:
    return base64.urlsafe_b64encode(key).decode().rstrip('=')


def decode_key(value: str) -> bytes:
    try:
        key = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
        if len(key) != 32:
            raise ValueError
        return key
    except Exception:
        raise ValueError('A valid 256-bit recovery key is required') from None


def pairing_export(workspace_id: str, key: bytes, subject: str) -> str:
    # Bind pairing to the verified Google subject without publishing it in
    # Drive metadata or deriving the encryption key from an account identifier.
    binding = hmac.new(key, ('tracker-sync-account-v1:' + workspace_id + ':' + subject).encode(), hashlib.sha256).digest()
    return f'ats1.{workspace_id}.{encode_key(key)}.{encode_key(binding)}'


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def seal(batch: Batch, key: bytes) -> bytes:
    raw = canonical(batch.model_dump(mode='json'))
    if len(raw) > MAX_PLAINTEXT:
        raise ValueError('Sync payload exceeds the decoded size limit')
    header = {'version': 1, 'workspace_id': str(batch.workspace_id), 'batch_id': str(batch.batch_id),
              'sha256': hashlib.sha256(raw).hexdigest()}
    aad = canonical(header)
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce, gzip.compress(raw, mtime=0), aad)
    return canonical({'header': header, 'nonce': encode_key(nonce), 'ciphertext': encode_key(encrypted)})


def open_envelope(data: bytes, key: bytes, workspace_id: str) -> Batch:
    try:
        if len(data) > MAX_ENCRYPTED * 2:
            raise ValueError
        envelope = json.loads(data)
        if set(envelope) != {'header', 'nonce', 'ciphertext'}:
            raise ValueError
        header = envelope['header']
        if set(header) != {'version', 'workspace_id', 'batch_id', 'sha256'} or header['version'] != 1 or header['workspace_id'] != workspace_id:
            raise ValueError
        UUID(header['batch_id'])
        def decode(value):
            return base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
        compressed = AESGCM(key).decrypt(decode(envelope['nonce']), decode(envelope['ciphertext']), canonical(header))
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(compressed, MAX_PLAINTEXT + 1)
        if len(raw) > MAX_PLAINTEXT or not decoder.eof or decoder.unused_data:
            raise ValueError
        if hashlib.sha256(raw).hexdigest() != header['sha256']:
            raise ValueError
        batch = Batch.model_validate_json(raw)
        if str(batch.batch_id) != header['batch_id'] or str(batch.workspace_id) != workspace_id:
            raise ValueError
        return batch
    except Exception:
        raise ValueError('Sync file failed authentication, schema or size validation; no data was applied') from None
