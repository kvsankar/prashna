"""In-process token-bucket rate limiting.

Single-process only — like the WebSocket hub (`app/ws.py`) and the
first-run setup lock (`app/main.py`). No external store, no new deps.

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
