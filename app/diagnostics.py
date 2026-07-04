"""Shared diagnostic logging helpers."""
from __future__ import annotations

import logging

logger = logging.getLogger("prashna")


def _unsafe_diag_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in ("password", "secret", "token", "key", "cookie")
    )


def log_diagnostic(event: str, **fields) -> None:
    """Emit a best-effort, secret-safe structured diagnostic event."""
    extra = {"diag_event": event}
    for key, value in fields.items():
        if _unsafe_diag_key(key):
            continue
        if isinstance(value, str):
            safe_value = value[:120]
        elif isinstance(value, (bool, int, float)) or value is None:
            safe_value = value
        else:
            continue
        extra[f"diag_{key}"] = safe_value
    try:
        logger.info("diagnostic_event", extra=extra)
    except Exception:
        pass
