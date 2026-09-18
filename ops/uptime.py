"""Is a service actually serving? Probe + verdict.

Split deliberately: `classify` is pure so every judgement call is unit-tested
without a network, and `probe` is the thin impure edge that fetches.

Three verdicts, not two. UNKNOWN exists because the most common way a naive
uptime check fails is reporting DOWN when it merely could not *ask* - a tunnel
auth challenge or an anti-phishing interstitial. Paging on those trains you to
ignore the monitor, which is worse than having none.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# The devtunnel anti-phishing interstitial fingerprint. A 200 carrying this is
# the relay talking, not our app. (Same check as email-search's verify-dev.ps1.)
INTERSTITIAL_FINGERPRINT = "twitter:card"

# The devtunnel relay's own auth challenge body.
TUNNEL_AUTH_FINGERPRINT = "authentication required"

# How much of the response body to keep. Big enough that a /health JSON payload
# is never truncated (truncation would make it unparseable), small enough that
# a multi-MB error page never reaches the logs.
MAX_BODY_CHARS = 8192

# Getting a devtunnel to hand back the *app* rather than a challenge page needs
# all three of these, learned by probing prod:
#   - no/odd User-Agent            -> relay answers 401 "Authentication required"
#   - browser UA + Accept text/html -> relay answers 200 with the anti-phishing
#                                      interstitial (looks green, isn't our app)
#   - browser UA + the skip header  -> the real app
# Accept is deliberately */* rather than text/html: the interstitial keys off
# navigation-shaped requests. The skip header is the documented bypass; both
# together make it deterministic instead of a heuristic race.
PROBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "X-Tunnel-Skip-AntiPhishing-Page": "true",
}


class Verdict(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CheckResult:
    verdict: Verdict
    reason: str


def classify(*, status: int | None, body: str, error: str | None) -> CheckResult:
    """Turn one HTTP outcome into a verdict. Pure."""
    if error:
        return CheckResult(Verdict.DOWN, f"unreachable: {error}")

    if status is None:
        return CheckResult(Verdict.DOWN, "unreachable: no response")

    haystack = (body or "").lower()

    # Ask-blocked before anything else: these say nothing about the app.
    if status in (401, 403):
        if TUNNEL_AUTH_FINGERPRINT in haystack:
            return CheckResult(
                Verdict.UNKNOWN,
                f"tunnel demanded auth ({status}) - cannot reach the app to judge it",
            )
        return CheckResult(
            Verdict.UNKNOWN,
            f"tunnel or gateway refused the probe ({status}) - app health unknown",
        )

    if INTERSTITIAL_FINGERPRINT in haystack:
        return CheckResult(
            Verdict.UNKNOWN,
            f"tunnel interstitial page ({status}), not our app - health unknown",
        )

    if status >= 500:
        return CheckResult(Verdict.DOWN, f"server error ({status})")

    # 2xx and 3xx both prove something is serving. A 3xx matters as much as a
    # 200 here: prod `/` redirects to /login when the password gate is active,
    # and the gate answering at all means Next is alive.
    if 200 <= status < 400:
        return CheckResult(Verdict.UP, f"serving ({status})")

    return CheckResult(Verdict.DOWN, f"unexpected response ({status})")


def probe(
    url: str,
    *,
    timeout: float = 20.0,
    force_ipv4: bool = True,
    classifier=None,
) -> CheckResult:
    """Fetch `url` once and classify the outcome.

    force_ipv4 defaults on: dual-stack Microsoft hosts (devtunnels.ms among
    them) make httpx hang for minutes from IPv6-first networks with no
    Happy-Eyeballs fallback. Binding the local address to 0.0.0.0 pins IPv4.
    On Railway it is a harmless no-op.

    `classifier` swaps the verdict rule while keeping this request shape - the
    headers here are hard-won (see the trap table in ops/README.md) and must
    not be duplicated. ops/health.classify_health uses it to read a /health
    payload instead of just the status line.
    """
    import httpx

    verdict_for = classifier or classify
    headers = PROBE_HEADERS
    transport = httpx.HTTPTransport(local_address="0.0.0.0") if force_ipv4 else None

    try:
        with httpx.Client(
            timeout=timeout, follow_redirects=False, transport=transport
        ) as client:
            response = client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001 - any failure to ask is "unreachable"
        return verdict_for(status=None, body="", error=f"{type(exc).__name__}: {exc}")

    # Only the head of the body is needed, and the cap keeps a stray multi-MB
    # error page out of the logs. It has to stay well clear of a real /health
    # payload though: a truncated body is invalid JSON, which classify_health
    # would read as UNKNOWN forever - a monitor that never reports anything.
    return verdict_for(
        status=response.status_code, body=response.text[:MAX_BODY_CHARS], error=None
    )
