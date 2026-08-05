"""What this backend says about itself.

Every FD tool posts to this service and it owns both Postgres and the MinIO
bucket, so "is the process serving" is the wrong question - `/docs` answers 200
regardless of whether the database is reachable. The daily sweep
(`ops/daily.py`) reads the payload this builds.

`build_health` is pure: probing is done by the caller, every status rule is
decided here and unit-tested without a database.
"""
from __future__ import annotations

from typing import Mapping

# The tables the API needs to serve its main routes. Missing ones mean the
# migrations have not been run against this environment.
REQUIRED_TABLES = (
    "projects",
    "floors",
    "elements",
    "cfd_simulations",
    "cfd_runner_state",
)

HEALTHY = "healthy"
DEGRADED = "degraded"
UNHEALTHY = "unhealthy"

# Worst wins, so a broken database is never masked by a milder storage fault.
_SEVERITY = {HEALTHY: 0, DEGRADED: 1, UNHEALTHY: 2}


def _worse(current: str, candidate: str) -> str:
    return candidate if _SEVERITY[candidate] > _SEVERITY[current] else current


def build_health(
    *,
    database: bool,
    tables: Mapping[str, bool],
    storage: bool,
    database_error: str | None = None,
    storage_error: str | None = None,
) -> dict:
    """Aggregate probe outcomes into the /health payload. Pure.

    Severity rules:
      - database unreachable -> unhealthy. Nothing meaningful works without it.
      - missing tables       -> degraded. The app runs; some routes will 500.
      - storage unreachable  -> degraded. Reads work, uploads fail.
    """
    status = HEALTHY
    errors: list[str] = []

    if database:
        missing = [name for name in REQUIRED_TABLES if not tables.get(name, False)]
        if missing:
            status = _worse(status, DEGRADED)
            errors.append(
                f"Missing tables: {missing}. Run: alembic upgrade head"
            )
    else:
        status = _worse(status, UNHEALTHY)
        detail = f": {database_error}" if database_error else ""
        errors.append(f"Database unreachable{detail}")

    if not storage:
        status = _worse(status, DEGRADED)
        detail = f": {storage_error}" if storage_error else ""
        errors.append(
            f"Storage (S3/MinIO) unreachable or bucket missing{detail} - "
            "uploads will fail"
        )

    return {
        "status": status,
        "api": True,
        "database": database,
        "storage": storage,
        "tables": dict(tables),
        "errors": errors,
    }
