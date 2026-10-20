"""Reusable pending OAuth state, without a provider or network dependency."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.oauth_sessions import OAuthSessionError, OAuthSessionManager


def test_binding_owner_and_active_session_checks_do_not_consume_a_valid_flow():
    sessions = OAuthSessionManager()
    state = sessions.create('browser', 'workspace-session', {'provider': 'example'})
    for binding, owner, validator in [('wrong', 'workspace-session', None), ('browser', 'wrong', None),
                                      ('browser', None, None), ('browser', None, lambda _: False)]:
        with pytest.raises(OAuthSessionError):
            sessions.consume(state, binding, owner, owner_validator=validator)
    assert sessions.consume(state, 'browser', None, owner_validator=lambda owner: owner == 'workspace-session') == {'provider': 'example'}
    with pytest.raises(OAuthSessionError):
        sessions.consume(state, 'browser', 'workspace-session')


def test_expiry_capacity_and_clear_are_owned_by_the_session_manager():
    now = [0]
    sessions = OAuthSessionManager(lifetime=10, capacity=1, clock=lambda: now[0])
    expired = sessions.create('browser', 'owner', 1)
    with pytest.raises(OAuthSessionError):
        sessions.create('browser', 'owner', 2)
    now[0] = 10
    with pytest.raises(OAuthSessionError):
        sessions.consume(expired, 'browser', 'owner')
    current = sessions.create('browser', 'owner', 3)
    sessions.clear()
    with pytest.raises(OAuthSessionError):
        sessions.consume(current, 'browser', 'owner')


def test_concurrent_callbacks_can_only_consume_once():
    sessions = OAuthSessionManager()
    state = sessions.create('browser', 'owner', 'grant')
    def consume(_):
        try:
            return sessions.consume(state, 'browser', 'owner')
        except OAuthSessionError:
            return 'rejected'
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(consume, range(4)))
    assert results.count('grant') == 1 and results.count('rejected') == 3
