"""The reusable auth client works with a host unrelated to the tracker."""
import httpx
import pytest

from app.authorized_api import AuthorizedApiClient, AuthorizedRequestError, TokenLease


@pytest.mark.parametrize(('status', 'reason', 'kind', 'invalidated'), [
    (401, '', 'authorization', True), (403, 'insufficientPermissions', 'authorization', True),
    (403, 'userRateLimitExceeded', 'rate_limit', False), (429, '', 'rate_limit', False),
    (403, 'storageQuotaExceeded', 'storage_full', False), (503, '', 'unavailable', False),
    (410, '', 'invalid_cursor', False), (404, '', 'missing', False),
])
def test_typed_failures_only_invalidate_actual_authorization(status, reason, kind, invalidated):
    rejected, calls = [], []
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return httpx.Response(status, json={'error': {'errors': [{'reason': reason}], 'message': 'private provider data'}},
                              headers={'Retry-After': '30'})
    client = AuthorizedApiClient('https://provider.example/api/', lambda capability: TokenLease('secret', 7), request,
        lambda capability, lease, error: rejected.append((capability, lease.generation)))
    with pytest.raises(AuthorizedRequestError) as caught:
        client.call('storage', 'POST', 'objects', headers={'authorization': 'untrusted'}, json={'id': 'operation'})
    assert caught.value.kind == kind and caught.value.retry_after == 30
    assert bool(rejected) == invalidated
    assert len(calls) == 1  # uncertain writes are never blindly replayed
    assert calls[0][2]['headers'] == {'Authorization': 'Bearer secret'}
    assert 'private' not in str(caught.value) and 'secret' not in repr(TokenLease('secret', 7))


def test_destination_is_validated_before_acquiring_a_credential():
    def unexpected(*args, **kwargs):
        raise AssertionError('must not acquire credentials or call HTTP')
    client = AuthorizedApiClient('https://provider.example/api/', unexpected, unexpected)
    for path in ('https://evil.example/steal', '//evil.example/steal', '../steal', '/outside'):
        with pytest.raises(ValueError):
            client.call('storage', 'GET', path)
    with pytest.raises(ValueError):
        client.call('storage', 'GET', 'objects', follow_redirects=True)


def test_network_failure_does_not_leak_provider_or_token():
    def request(*args, **kwargs):
        raise httpx.ConnectError('secret URL and credential details')
    client = AuthorizedApiClient('https://provider.example/', lambda _: TokenLease('secret', 1), request)
    with pytest.raises(AuthorizedRequestError, match='Provider unavailable'):
        client.call('storage', 'GET', 'objects')
