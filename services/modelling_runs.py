"""Pure helpers for the phase-1 modelling-runs dashboard.

CloudHPC stays off. There is no client and no API key for it here.
"""

from datetime import datetime, timezone

# Phase 2 turns this on. Nothing in phase 1 calls CloudHPC.
CLOUDHPC_ENABLED = False

# The runner heartbeats about every 15s. Quiet for longer than this means offline.
HEARTBEAT_OFFLINE_SECONDS = 90


def as_utc(value):
    """SQLite returns strings; Postgres returns datetimes. Both may be naive."""
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def effective_machine_status(stored: str, last_heartbeat, now=None) -> str:
    """Offline wins once the last heartbeat is older than 90 seconds."""
    now = now or datetime.now(timezone.utc)
    heartbeat = as_utc(last_heartbeat)
    if heartbeat is None:
        return "offline"
    if (now - heartbeat).total_seconds() > HEARTBEAT_OFFLINE_SECONDS:
        return "offline"
    return stored
