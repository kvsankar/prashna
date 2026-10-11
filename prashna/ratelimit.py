"""In-process token-bucket rate limiting.

Single-process only — like the WebSocket hub (`prashna/ws.py`) and the
first-run setup lock (`prashna/main.py`). No external store, no new deps.

Each bucket is identified by an arbitrary string key; the caller passes
the capacity (burst size) and refill rate (tokens per second) for that
bucket class. `allow()` refills lazily and tries to consume one token,
returning whether the call is permitted.

Disabled wholesale via `PRASHNA_RATELIMIT=off` (also `0` / `false` /
`no`); any other value (including unset) leaves it on.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


def enabled_from_env(value: str | None) -> bool:
    """PRASHNA_RATELIMIT=off|0|false|no disables; unset/anything else is on."""
    if value is None:
        return True
    return value.strip().lower() not in ("off", "0", "false", "no")


# Limits the admin can change while the server runs (UC-A-31); these are
# the defaults. "network_size" is how many people may share one network
# address: it is the joining burst, and each per-person action's address
# ceiling is that many people's allowance (UC-X-08).
DEFAULT_LIMITS: dict[str, int] = {
    "network_size": 300, "join_per_minute": 120,
    "ask_burst": 6, "ask_per_minute": 6,
    "vote_burst": 30, "vote_per_minute": 120,
    "submit_burst": 20, "submit_per_minute": 30,
    "feedback_burst": 10, "feedback_per_minute": 30,
}
LIMIT_MAX = 100_000


def validated_limits(current: dict[str, int], updates: dict) -> dict[str, int]:
    """Return `current` with `updates` applied, or raise ValueError with the
    message the API shows (UC-A-31)."""
    merged = dict(current)
    for name, value in updates.items():
        if name not in DEFAULT_LIMITS:
            raise ValueError(f"unknown limit: {name}")
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= LIMIT_MAX:
            raise ValueError(f"{name} must be a whole number from 1 to {LIMIT_MAX}")
        merged[name] = value
    return merged


# Buckets idle longer than this are evicted on the next opportunistic sweep,
# so memory doesn't grow with unique IPs across a long-running event.
_IDLE_EVICT_SECS = 3600.0


@dataclass
class _Bucket:
    tokens: float
    last: float


class TokenBucketLimiter:
    def __init__(self, *, enabled: bool = True, time_func=time.monotonic) -> None:
        self.enabled = enabled
        self._time = time_func
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._ops = 0

    def allow(self, key: str, capacity: int, refill_per_sec: float) -> bool:
        """Refill the bucket for `key` and try to consume one token.

        Returns True if a token was available (request permitted). A
        disabled limiter always returns True.
        """
        if not self.enabled:
            return True
        now = self._time()
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = _Bucket(tokens=float(capacity), last=now)
                self._buckets[key] = b
            else:
                elapsed = now - b.last
                if elapsed > 0:
                    b.tokens = min(float(capacity), b.tokens + elapsed * refill_per_sec)
                    b.last = now
            allowed = b.tokens >= 1.0
            if allowed:
                b.tokens -= 1.0
            self._maybe_sweep(now)
            return allowed

    def reset(self, key: str) -> None:
        """Drop one bucket — e.g. on a successful login, so the throttle
        never penalizes a legitimate user who eventually got it right."""
        with self._lock:
            self._buckets.pop(key, None)

    def clear(self) -> None:
        """Drop all buckets (used by tests for isolation)."""
        with self._lock:
            self._buckets.clear()

    def _maybe_sweep(self, now: float) -> None:
        # Called under the lock. Cheap amortized eviction of idle buckets.
        self._ops += 1
        if self._ops % 256 != 0 or len(self._buckets) < 1024:
            return
        stale = [k for k, b in self._buckets.items() if (now - b.last) > _IDLE_EVICT_SECS]
        for k in stale:
            self._buckets.pop(k, None)
