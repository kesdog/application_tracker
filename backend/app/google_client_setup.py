"""Owner-managed Google client registration, stored in the workspace credential vault."""
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy.orm import Session

from app.google_connection import GoogleConnectionError
from app.models import ExternalConnection

REFERENCE = 'google-oauth-client-registration'


class GoogleClientRegistration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_id: str = Field(pattern=r'^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$', max_length=256)
    client_secret: SecretStr | None = Field(default=None, max_length=4096)
    login_subjects: str | None = Field(default=None, max_length=4096)


class GoogleClientSetup:
    def __init__(self, google):
        self.google = google

    def status(self):
        settings = self.google.settings
        origin = settings.app_public_url if settings.app_mode == 'hosted' else f'http://{settings.app_host}:{settings.app_port}'
        return {'configured': self.google.configured, 'origin': origin,
                'redirect_uri': origin + '/api/connections/google/callback',
                'hosted': settings.app_mode == 'hosted'}

    def _apply(self, registration):
        settings = self.google.settings
        settings.google_client_id = registration.client_id
        settings.google_client_secret = registration.client_secret
        settings.google_redirect_uri = self.status()['redirect_uri']
        if registration.login_subjects is not None:
            settings.google_login_subjects = registration.login_subjects

    def restore(self):
        # Environment configuration remains supported and takes precedence.
        if self.google.settings.google_client_id or not (self.google.settings.app_data_dir / '.google-client-registered').exists():
            return
        try:
            stored = self.google.store.get(REFERENCE)
            if stored:
                self._apply(GoogleClientRegistration.model_validate(stored))
        except (GoogleConnectionError, ValueError, TypeError):
            # A locked vault must never prevent local tracking or password login.
            return

    def save(self, registration):
        if self.google.settings.google_client_id and self.google.settings.google_client_id != registration.client_id:
            with Session(self.google.engine) as session:
                connection = session.get(ExternalConnection, 1)
                if connection and connection.secret_reference:
                    raise GoogleConnectionError('Disconnect your current Google account before using a different Google app registration.')
        value = {'client_id': registration.client_id,
                 'client_secret': registration.client_secret.get_secret_value() if registration.client_secret else None,
                 'login_subjects': registration.login_subjects if registration.login_subjects is not None else self.google.settings.google_login_subjects}
        self.google.store.put(REFERENCE, value)
        # Only a presence marker is stored with workspace files; credentials stay in the vault.
        try:
            (self.google.settings.app_data_dir / '.google-client-registered').write_text('vault\n', encoding='utf-8')
        except OSError:
            raise GoogleConnectionError('Google setup could not be saved. Check that this installation can write to its workspace folder, then try again.') from None
        self.google.login.sessions.clear()
        self._apply(registration)
        return self.status()
