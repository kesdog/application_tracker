"""Encrypted server credential storage; master key is a separately mounted secret."""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptedFileSecretStore:
    def __init__(self, workspace: Path, key_file: Path):
        self.workspace = workspace.resolve()
        self.key_file = key_file.resolve()
        if self.key_file.is_relative_to(self.workspace):
            raise ValueError('The credential master key must be outside the workspace data directory')
        self.folder = self.workspace / 'credentials'

    def cipher(self):
        from app.google_connection import GoogleConnectionError
        try:
            if os.name != 'nt' and self.key_file.stat().st_mode & 0o077:
                raise ValueError('Master key permissions must be 0600 or stricter')
            key = base64.urlsafe_b64decode(self.key_file.read_bytes().strip())
            if len(key) != 32:
                raise ValueError()
            return AESGCM(key)
        except Exception:
            raise GoogleConnectionError('The server credential key is missing, invalid or not private. Check APP_CREDENTIAL_KEY_FILE.') from None

    def path(self, reference):
        return self.folder / (hashlib.sha256(reference.encode()).hexdigest() + '.aes')

    def binding(self, reference):
        return ('tracker-credentials-v1:' + str(self.workspace) + ':' + reference).encode()

    def get(self, reference):
        from app.google_connection import GoogleConnectionError
        path = self.path(reference)
        try:
            if not path.exists():
                return None
            value = path.read_bytes()
            return json.loads(self.cipher().decrypt(value[:12], value[12:], self.binding(reference)))
        except GoogleConnectionError:
            raise
        except Exception:
            raise GoogleConnectionError('Stored credentials could not be unlocked. Restore the original credential key or reconnect Google.') from None

    def put(self, reference, value):
        from app.google_connection import GoogleConnectionError
        temporary = None
        try:
            cipher = self.cipher()
            self.folder.mkdir(mode=0o700, parents=True, exist_ok=True)
            nonce = secrets.token_bytes(12)
            encoded = nonce + cipher.encrypt(nonce, json.dumps(value).encode(), self.binding(reference))
            temporary = self.folder / (secrets.token_hex(16) + '.tmp')
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, self.path(reference))
        except GoogleConnectionError:
            raise
        except Exception:
            raise GoogleConnectionError('Credentials could not be stored safely. Check server disk space and permissions.') from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def delete(self, reference):
        if reference:
            self.path(reference).unlink(missing_ok=True)


def create_key(output: Path):
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(base64.urlsafe_b64encode(secrets.token_bytes(32)) + b'\n')


def run():
    import argparse
    parser = argparse.ArgumentParser(description='Create a server credential master key; back it up separately and never commit it.')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        create_key(args.output)
    except OSError:
        parser.error('Choose a new output path with private writable permissions.')
    print('Credential master key created. Keep it outside the workspace and mount it read-only.')


if __name__ == '__main__':
    run()
