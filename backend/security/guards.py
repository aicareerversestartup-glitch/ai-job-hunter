"""Small security helpers: login rate limiting, URL/SSRF validation, safe filenames."""
from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse


class RateLimiter:
    """In-process sliding-window limiter (sufficient for a single-user/self-hosted deployment)."""

    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record an event; return False if the key is over the limit."""
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] > self.window:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)


login_limiter = RateLimiter(max_events=8, window_seconds=300)


class UnsafeURLError(ValueError):
    pass


def validate_public_url(url: str, *, resolve: bool = True) -> str:
    """Allow only http(s) URLs pointing at public hosts (blocks SSRF into localhost/LAN/metadata)."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeURLError("Only http(s) URLs are allowed.")
    host = parsed.hostname
    if host in {"localhost"} or host.endswith((".local", ".internal", ".localhost")):
        raise UnsafeURLError("Local addresses are not allowed.")
    addresses: list[str] = []
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        if resolve:
            try:
                addresses = list({str(info[4][0]) for info in socket.getaddrinfo(host, None)})
            except socket.gaierror as exc:
                raise UnsafeURLError(f"Could not resolve {host}.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UnsafeURLError("Private network addresses are not allowed.")
    return url.strip()


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, default: str = "file") -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = _SAFE_NAME_RE.sub("_", base).strip("._")
    return (base or default)[:120]
