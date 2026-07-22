"""Daily uptime sweep. Entrypoint for the Railway cron service.

    python -m ops.daily

Exits 0 when nothing is DOWN, 1 otherwise, which marks the run failed in the
Railway UI. That is *not* the alert: Railway does not notify on a cron service
exiting non-zero, it only records the failed run. The alert is the Telegram
message sent from ops/notify.py. Do not remove it and rely on the exit code.

UNKNOWN never fails the run: "the tunnel would not let us ask" is not evidence
the service is down, and paging on it is how monitors earn their way onto the
ignore list.

Two depths of check, because they answer different questions:

  liveness - "is something serving this URL". Right for the frontends: a Vercel
             app that renders is a Vercel app that works.
  deep     - "does the service report itself well". Required for anything that
             owns data. backendForNextApp and the mobile backend both return
             200 on /docs while their Postgres or MinIO is dead - which is how
             the mobile S3 outage stayed invisible until users hit it.

IMPORTANT: this process must exit. Railway will not start the next scheduled
run while the previous one is still alive.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Iterable

from ops.health import classify_health
from ops.notify import format_alert, send_telegram
from ops.uptime import CheckResult, Verdict, probe


@dataclass(frozen=True)
class Service:
    """One thing worth knowing is alive.

    `url` is only the pinned default - every service is overridable by env var
    so a tunnel hostname or a renamed Railway app can be repointed without a
    code deploy.
    """

    name: str
    env_var: str
    url: str
    deep: bool = False

    def resolved_url(self) -> str:
        return os.environ.get(self.env_var, self.url)


# The estate. Frontends get liveness; anything owning a database or a bucket
# gets a deep check.
#
# Probe-path notes, each one learned the hard way:
#   - email-search probes /login, not /health: /health is ungated in the
#     ui/proxy.ts source but the *deployed* prod build still gates it, so it
#     answers 401 forever. Do not "fix" this to /health.
#   - backendForNextApp has no root route (GET / is a genuine 404), so its
#     liveness fallback would have to be /docs. It gets a deep check instead.
SERVICES: list[Service] = [
    # --- backends that own data -------------------------------------------
    Service(
        name="backendForNextApp (prod)",
        env_var="BACKEND_PROBE_URL",
        url="https://backendfornextapp-production.up.railway.app/health",
        deep=True,
    ),
    Service(
        name="mobile backend",
        env_var="MOBILE_BACKEND_PROBE_URL",
        url="https://web-production-44b8.up.railway.app/health",
        deep=True,
    ),
    # --- storage ------------------------------------------------------------
    # MinIO's own liveness probe. Checked directly as well as through the
    # backends' /health so an outage is attributable: if this is DOWN too, the
    # bucket is the fault, not the app that depends on it.
    Service(
        name="MinIO bucket",
        env_var="MINIO_PROBE_URL",
        url="https://bucket-production-a0e4.up.railway.app/minio/health/live",
    ),
    # --- frontends ----------------------------------------------------------
    Service(
        name="fd-toolstation",
        env_var="TOOLSTATION_PROBE_URL",
        url="https://fd-toolstation.vercel.app",
    ),
    Service(
        name="upload-canvas",
        env_var="UPLOAD_CANVAS_PROBE_URL",
        url="https://upload-canvas.vercel.app",
    ),
    Service(
        name="upload-canvas-next",
        env_var="UPLOAD_CANVAS_NEXT_PROBE_URL",
        url="https://upload-canvas-next.vercel.app",
    ),
    Service(
        name="site-right-report-gen",
        env_var="SITE_RIGHT_PROBE_URL",
        url="https://site-right-report-gen.vercel.app",
    ),
    Service(
        name="sprinklers-web-app",
        env_var="SPRINKLERS_PROBE_URL",
        url="https://sprinklers-web-app.vercel.app",
    ),
    # --- self-hosted --------------------------------------------------------
    Service(
        name="email-search (TinyBot)",
        env_var="EMAIL_SEARCH_PROBE_URL",
        url="https://s56p2ggh-3000.uks1.devtunnels.ms/login",
    ),
]

SYMBOL = {Verdict.UP: "UP  ", Verdict.DOWN: "DOWN", Verdict.UNKNOWN: "????"}


def check(service: Service) -> CheckResult:
    """Probe one service at the depth it warrants."""
    return probe(
        service.resolved_url(),
        classifier=classify_health if service.deep else None,
    )


def exit_code(results: Iterable[CheckResult]) -> int:
    """0 unless something is actually DOWN. Pure - this rule is the alert."""
    return 1 if any(r.verdict is Verdict.DOWN for r in results) else 0


def run() -> int:
    results: list[CheckResult] = []
    down: list[str] = []

    for service in SERVICES:
        url = service.resolved_url()
        result = check(service)
        results.append(result)
        depth = "deep" if service.deep else "live"
        print(
            f"{SYMBOL[result.verdict]}  [{depth}]  {service.name}  "
            f"{result.reason}  <{url}>",
            flush=True,
        )
        if result.verdict is Verdict.DOWN:
            down.append(f"{service.name}: {result.reason}")

    if down:
        print(f"\n{len(down)} service(s) DOWN:", flush=True)
        for line in down:
            print(f"  - {line}", flush=True)

        # Railway does not alert on a cron service exiting non-zero, so the
        # exit code alone would fail silently in the logs. This is the alert.
        if send_telegram(format_alert(down, total_checked=len(SERVICES))):
            print("Alert sent to Telegram.", flush=True)
    else:
        print("\nNothing down.", flush=True)

    return exit_code(results)


if __name__ == "__main__":
    sys.exit(run())
