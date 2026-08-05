"""Does a service say it is well? Payload-aware checks.

`uptime.classify` answers "is something serving". For the services that own
data that is not enough: a FastAPI app returns 200 on `/docs` while its
Postgres or MinIO is dead. The mobile app's S3 bucket went down in exactly that
shape - API green, uploads failing, the outage found by hand.

So a service that publishes a `/health` payload gets read, not just pinged.

Kept separate from `uptime.py` on purpose. Two different questions:
`uptime` = "did anything answer", `health` = "did it answer that it is well".
Transport-level judgements are delegated to `uptime.classify` so the tunnel
and unreachability semantics stay defined in exactly one place.
"""
from __future__ import annotations

import json

from ops.uptime import CheckResult, Verdict, classify

# What a service may call itself, and whether that counts as working.
# "degraded" is DOWN, not UP: it means a real dependency is broken (storage,
# a missing table) even though the process still answers. Reporting it green
# is how the S3 outage stayed invisible.
_OK = "healthy"
_BROKEN = {"degraded", "unhealthy"}


def _describe_errors(payload: dict) -> str:
    """Pull the service's own error strings into the one-line reason.

    The daily log is the first thing read during an incident, so it should say
    *what* broke rather than just "degraded".
    """
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return "; ".join(str(e) for e in errors[:3])

    # No error list - name the dependency flags that are False instead.
    failed = [
        key
        for key, value in payload.items()
        if value is False and key not in ("status",)
    ]
    if failed:
        return f"failing: {', '.join(sorted(failed))}"

    return "no detail given"


def classify_health(*, status: int | None, body: str, error: str | None) -> CheckResult:
    """Turn one /health response into a verdict. Pure.

    Transport problems defer to `uptime.classify`. Only once something
    genuinely answered do we read what it said about itself.
    """
    transport = classify(status=status, body=body, error=error)
    if transport.verdict is not Verdict.UP:
        return transport

    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return CheckResult(
            Verdict.UNKNOWN,
            f"answered {status} but the body is not JSON - cannot read its health",
        )

    if not isinstance(payload, dict) or "status" not in payload:
        return CheckResult(
            Verdict.UNKNOWN,
            f"answered {status} with JSON but no 'status' field - cannot read its health",
        )

    reported = str(payload["status"]).lower()

    if reported == _OK:
        return CheckResult(Verdict.UP, f"reports healthy ({status})")

    if reported in _BROKEN:
        return CheckResult(Verdict.DOWN, f"reports {reported}: {_describe_errors(payload)}")

    # An unrecognised value is a contract change, not evidence of breakage.
    return CheckResult(
        Verdict.UNKNOWN, f"reported unrecognised status {payload['status']!r}"
    )
