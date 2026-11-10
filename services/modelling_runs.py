"""Pure helpers for the phase-1 modelling-runs dashboard.

CloudHPC stays off. There is no client and no API key for it here.
"""

from datetime import datetime, timezone

# Phase 2 turns this on. Nothing in phase 1 calls CloudHPC.
CLOUDHPC_ENABLED = False


class CloudHpcDisabled(RuntimeError):
    """Raised by pull_csv while CLOUDHPC_ENABLED is off."""


def pull_csv(run) -> None:
    """Fetch *_hrr.csv and *_devc.csv for a CloudHPC run.

    The adapter is not built. While CLOUDHPC_ENABLED is off this raises
    CloudHpcDisabled and does not call the network. Two facts are still
    unknown, and the adapter should not be written until they are:

    - whether *_hrr.csv and *_devc.csv appear mid-run via sync/storage,
      or only after the job finishes
    - whether the fetch is GET /storage/view-url/{id} (mediaLink) or
      GET /storage/download/{id}
    """
    if not CLOUDHPC_ENABLED:
        raise CloudHpcDisabled("CloudHPC is disabled")
    raise NotImplementedError("CloudHPC CSV adapter is not built")

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
