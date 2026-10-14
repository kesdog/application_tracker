"""No surprise private-network access or overly permissive URL parsing."""

import socket
import pytest
from webtoolbox.security import UnsafeURLError, normalized_url, validate_url


def test_tracking_params_normalized():
    assert normalized_url("https://EXAMPLE.org/a?utm_source=bot&b=2&a=1#top") == "https://example.org/a?a=1&b=2"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://user:secret@example.org", "javascript:alert(1)"])
def test_reject_invalid_url(url):
    with pytest.raises(UnsafeURLError):
        validate_url(url)


def test_block_private_dns(monkeypatch):
    # Model a hostname that resolves into the private network after validation.
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [(socket.AF_INET, 0, 0, "", ("127.0.0.1", 80))])
    with pytest.raises(UnsafeURLError, match="Private"):
        validate_url("http://evil.test/metadata")


def test_allowed_hosts(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [(socket.AF_INET, 0, 0, "", ("8.8.8.8", 80))])
    assert validate_url("https://docs.example.org/a", allowed_hosts=("example.org",))
    with pytest.raises(UnsafeURLError, match="not in"):
        validate_url("https://fakeexample.org", allowed_hosts=("example.org",))
