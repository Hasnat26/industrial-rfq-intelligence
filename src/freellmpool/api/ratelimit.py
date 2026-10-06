"""In-process sliding-window failure rate limiting for authentication.

This module deliberately introduces no infrastructure dependency: the
application runs as a single process, so a thread-safe in-process
window is sufficient to blunt credential brute force and password
spraying at the source. Deployments that run multiple workers or
replicas need a shared store (e.g. Redis) at the edge instead; that
boundary is documented in ``docs/SAAS_AUTH_AND_TENANCY.md`` rather
than faked here.

Keys are opaque strings chosen by the caller (``login:email:...``,
``login:ip:...``). Only *failures* are recorded; a successful
authentication clears the caller's key. Limits and the window are
read from the environment on each check so operators can tune them
without code changes and tests can shrink them safely.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

_LOCK = threading.Lock()
_EVENTS: dict[str, deque[float]] = {}

DEFAULT_EMAIL_MAX_FAILURES = "5"
DEFAULT_IP_MAX_FAILURES = "25"
DEFAULT_WINDOW_SECONDS = "300"


def _positive_int(env: str, default: str) -> int:
    raw = os.getenv(env, default)
    try:
        value = int(raw)
    except ValueError:
        return int(default)
    return value if value > 0 else int(default)


def window_seconds() -> float:
    """Failure window length in seconds (env-tunable, default 300)."""
    raw = os.getenv("INDUSTRIAL_RFQ_RATE_LIMIT_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS)
    try:
        value = float(raw)
    except ValueError:
        return float(DEFAULT_WINDOW_SECONDS)
    return value if value >= 0 else float(DEFAULT_WINDOW_SECONDS)


def email_max_failures() -> int:
    return _positive_int(
        "INDUSTRIAL_RFQ_LOGIN_EMAIL_MAX_FAILURES", DEFAULT_EMAIL_MAX_FAILURES
    )


def ip_max_failures() -> int:
    return _positive_int(
        "INDUSTRIAL_RFQ_LOGIN_IP_MAX_FAILURES", DEFAULT_IP_MAX_FAILURES
    )


def _prune(events: deque[float], now: float, window: float) -> None:
    while events and now - events[0] >= window:
        events.popleft()


def record_failure(key: str) -> None:
    """Record one failed attempt against ``key`` (bounded bookkeeping)."""
    now = time.monotonic()
    window = window_seconds()
    with _LOCK:
        events = _EVENTS.setdefault(key, deque())
        _prune(events, now, window)
        events.append(now)
        # Bound memory: a key cannot accumulate more events than the
        # largest configurable budget plus one.
        max_events = max(ip_max_failures(), email_max_failures()) + 1
        while len(events) > max_events:
            events.popleft()


def is_blocked(key: str, max_failures: int | None = None) -> bool:
    """True when ``key`` exhausted its failure budget inside the window."""
    now = time.monotonic()
    window = window_seconds()
    with _LOCK:
        events = _EVENTS.get(key)
        if not events:
            return False
        _prune(events, now, window)
        if not events:
            return False
        budget = email_max_failures() if max_failures is None else max_failures
        return len(events) >= budget


def clear(key: str | None = None) -> None:
    """Reset one key, or all state (test isolation)."""
    with _LOCK:
        if key is None:
            _EVENTS.clear()
        else:
            _EVENTS.pop(key, None)
