"""Reusable bearer authorization boundary. No tracker, database or web framework imports.

The host owns credential storage/refresh and handles invalidation using the lease
generation. Requests are never automatically replayed: a failed write can have
succeeded remotely, so the transport's caller must reconcile its operation ID.
"""
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlsplit

import httpx


@dataclass(frozen=True, repr=False)
class TokenLease:
    token: str
    generation: int


class AuthorizedRequestError(ValueError):
    def __init__(self, kind: str, status: int | None = None, retry_after: int | None = None):
        self.kind, self.status, self.retry_after = kind, status, retry_after
        super().__init__({
            'authorization': 'Authorization expired or access was denied. Reconnect the provider.',
            'rate_limit': 'Provider rate limit reached. Pending changes are saved locally.',
            'storage_full': 'Provider storage is full. Free space before retrying sync.',
            'unavailable': 'Provider unavailable. Pending changes are saved locally.',
            'missing': 'Provider object is missing. Rediscover remote state.',
            'invalid_cursor': 'Provider change cursor is no longer valid. Rediscover remote state.',
            'request': 'Provider rejected the request.',
        }[kind])


def classify_response(response: httpx.Response) -> AuthorizedRequestError:
    reasons = set()
    try:
        error = response.json().get('error', {})
        if isinstance(error, dict):
            reasons = {item.get('reason') for item in error.get('errors', []) if isinstance(item, dict)}
    except (ValueError, AttributeError, TypeError):
        pass
    status = response.status_code
    if status == 429 or reasons & {'rateLimitExceeded', 'userRateLimitExceeded', 'dailyLimitExceeded'}:
        kind = 'rate_limit'
    elif reasons & {'storageQuotaExceeded', 'teamDriveFileLimitExceeded'}:
        kind = 'storage_full'
    elif status in {401, 403}:
        kind = 'authorization'
    elif status == 410:
        kind = 'invalid_cursor'
    elif status == 404:
        kind = 'missing'
    elif status >= 500:
        kind = 'unavailable'
    else:
        kind = 'request'
    retry = response.headers.get('retry-after', '')
    return AuthorizedRequestError(kind, status, min(int(retry), 3600) if retry.isdecimal() else None)


class AuthorizedApiClient:
    """Inject token acquisition, HTTP and invalidation to reuse in another project."""
    def __init__(self, base_url: str, acquire: Callable[[str], TokenLease], request: Callable,
                 rejected: Callable[[str, TokenLease, AuthorizedRequestError], None] | None = None):
        parsed = urlsplit(base_url)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('An HTTPS provider base URL is required')
        self.base_url, self.acquire, self.request, self.rejected = base_url.rstrip('/') + '/', acquire, request, rejected

    def call(self, capability: str, method: str, path: str, **kwargs):
        url = urljoin(self.base_url, path)
        if not url.startswith(self.base_url) or path.startswith(('/', '\\')) or '..' in path.split('/'):
            raise ValueError('Provider path must stay inside its configured base URL')
        if kwargs.get('follow_redirects'):
            raise ValueError('Authorized redirects are not supported')
        lease = self.acquire(capability)
        headers = {key: value for key, value in kwargs.pop('headers', {}).items() if key.lower() != 'authorization'}
        headers['Authorization'] = 'Bearer ' + lease.token
        try:
            response = self.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError:
            raise AuthorizedRequestError('unavailable') from None
        if not 200 <= response.status_code < 300:
            error = classify_response(response)
            if error.kind == 'authorization' and self.rejected:
                self.rejected(capability, lease, error)
            raise error
        return response
