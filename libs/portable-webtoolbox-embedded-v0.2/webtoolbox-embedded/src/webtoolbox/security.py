"""Restrict addresses before connecting; never assume a user-provided URL is safe."""

import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode


class UnsafeURLError(ValueError):
    """URL is invalid, unsafe or outside the configured scope."""


def normalized_url(url: str) -> str:
    # Strip fragments and common tracking parameters, retaining functional query values.
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in {"https", "http"} or not parts.hostname:
        raise UnsafeURLError("Only absolute HTTP(S) URLs are supported")
    if parts.username or parts.password:
        raise UnsafeURLError("Credential-bearing URLs are unsupported")
    host = parts.hostname.lower()
    if host.endswith("."):
        host = host[:-1]
    if not host or any(ord(c) < 33 for c in host):
        raise UnsafeURLError("Invalid hostname")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeURLError("Invalid port") from exc
    netloc = f"[{host}]" if ":" in host else host
    if port and not ((parts.scheme == "https" and port == 443) or (parts.scheme == "http" and port == 80)):
        netloc += f":{port}"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}))
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", query, ""))


def _public_ip(ip: str) -> bool:
    # is_global also rejects link-local, documentation, multicast and reserved ranges.
    return ipaddress.ip_address(ip).is_global


def validate_url(url: str, *, allow_private: bool = False, allowed_hosts: tuple[str, ...] = ()) -> str:
    """Validate the target before each request, including each HTTP redirect."""
    canonical = normalized_url(url)
    parts = urlsplit(canonical)
    hostname = (parts.hostname or "").lower()
    if allowed_hosts and not any(hostname == h or hostname.endswith("." + h) for h in allowed_hosts):
        raise UnsafeURLError(f"Host {hostname} is not in WT_ALLOWED_HOSTS")
    if allow_private:
        return canonical
    try:
        # Resolve all reported records; any non-public endpoint rejects the request.
        ips = {record[4][0] for record in socket.getaddrinfo(hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    except (OSError, ValueError) as exc:
        raise UnsafeURLError(f"DNS resolution failed for {hostname}") from exc
    if not ips or not all(_public_ip(ip) for ip in ips):
        raise UnsafeURLError(f"Private or non-global destination blocked: {hostname}")
    return canonical
