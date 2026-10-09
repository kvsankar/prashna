"""Shared diagnostic logging helpers."""
from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger("prashna")
logger.setLevel(logging.INFO)


def _ensure_runtime_logger() -> None:
    logger.disabled = False
    if logger.handlers:
        return
    uvicorn_logger = logging.getLogger("uvicorn.error")
    for handler in uvicorn_logger.handlers:
        logger.addHandler(handler)
    if logger.handlers:
        logger.propagate = False


def _unsafe_diag_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        marker in lowered
        for marker in ("password", "secret", "token", "key", "cookie")
    )


def log_diagnostic(event: str, **fields) -> None:
    """Emit a best-effort, secret-safe structured diagnostic event."""
    extra: dict[str, object] = {"diag_event": event}
    payload: dict[str, object] = {"event": event}
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
        payload[key] = safe_value
    message = (
        "diagnostic_event "
        + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )
    try:
        _ensure_runtime_logger()
        logger.info(message, extra=extra)
        uvicorn_logger = logging.getLogger("uvicorn.error")
        if uvicorn_logger.handlers:
            uvicorn_logger.info(message)
        print(message, file=sys.stderr, flush=True)
    except Exception:
        pass
