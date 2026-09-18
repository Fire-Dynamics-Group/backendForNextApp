"""Post-deploy smoke for Upload Canvas GET /projects?mode= across all modes.

Catches the class of bug that shipped as a `/projects` 500 (missing
`projects.mode` column) and was reported as CORS because the 500 body had no
ACAO header — and that we missed on timeEq/radiation/efs because we only
smoked fdsGen.

This is a live HTTP client, not a FastAPI TestClient: it speaks to whatever
base URL it is pointed at (prod, dev, a PR deploy). It never drives Entra.
When SMOKE_EMAIL + SMOKE_PASSWORD (or APP_PASSWORD) are set it mints a
password-fallback session via POST /auth/password; AUTH_MODE=log still allows
unauthenticated lists today, so a 503 from that route is a warning, not a
failure, unless SMOKE_REQUIRE_AUTH=1.

Empty mode lists are OK (prod has 0 timeEq). 5xx, non-JSON, and missing CORS
are not.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx

CANVAS_MODES = ("fdsGen", "timeEq", "radiation", "efs")
CANVAS_ORIGIN = "https://upload-canvas.vercel.app"
DEFAULT_BASE_URL = "https://backendfornextapp-production.up.railway.app"
SMOKE_NAME_PREFIX = "[smoke] projects-modes"


@dataclass
class SmokeConfig:
    base_url: str = DEFAULT_BASE_URL
    email: str | None = None
    password: str | None = None
    require_auth: bool = False
    readonly: bool = False
    origin: str = CANVAS_ORIGIN
    timeout: float = 30.0


@dataclass
class ModeResult:
    mode: str
    status: int | None
    count: int | None
    ok: bool
    reason: str


@dataclass
class HealthResult:
    status: int | None
    reported: str | None
    ok: bool
    reason: str


@dataclass
class SmokeReport:
    ok: bool
    modes: list[ModeResult] = field(default_factory=list)
    health: HealthResult | None = None
    auth_via: str = "none"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _strip_slash(url: str) -> str:
    return url.rstrip("/")


def load_config() -> SmokeConfig:
    base = (
        os.environ.get("SMOKE_BASE_URL")
        or os.environ.get("API_BASE")
        or DEFAULT_BASE_URL
    )
    email = os.environ.get("SMOKE_EMAIL", "").strip() or None
    password = (
        os.environ.get("SMOKE_PASSWORD", "").strip()
        or os.environ.get("APP_PASSWORD", "").strip()
        or None
    )
    origin = os.environ.get("SMOKE_ORIGIN", "").strip() or CANVAS_ORIGIN
    return SmokeConfig(
        base_url=_strip_slash(base.strip()),
        email=email,
        password=password,
        require_auth=_env_flag("SMOKE_REQUIRE_AUTH"),
        readonly=_env_flag("SMOKE_READONLY"),
        origin=origin,
    )


def cors_allows_origin(response: httpx.Response, origin: str) -> bool:
    acao = response.headers.get("access-control-allow-origin")
    if not acao:
        return False
    return acao == "*" or acao == origin


def _headers(config: SmokeConfig, token: str | None) -> dict[str, str]:
    headers = {"Origin": config.origin, "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _mint_session(
    client: httpx.Client, config: SmokeConfig
) -> tuple[str | None, str]:
    """Return (token, warning_or_empty). warning is printed by the caller."""
    if not config.email or not config.password:
        return None, ""
    try:
        response = client.post(
            "/auth/password",
            json={"email": config.email, "password": config.password},
            headers={"Accept": "application/json", "Origin": config.origin},
        )
    except httpx.HTTPError as exc:
        return None, f"POST /auth/password failed: {type(exc).__name__}: {exc}"

    if response.status_code == 503:
        return None, (
            "password fallback returned 503 (APP_PASSWORD/AUTH_SECRET unset on "
            "the API). Continuing unauthenticated — AUTH_MODE=log still allows "
            "list today; AUTH_MODE=enforce needs secrets."
        )
    if response.status_code != 200:
        return None, (
            f"POST /auth/password returned {response.status_code}: "
            f"{response.text[:200]}"
        )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None, "POST /auth/password returned non-JSON"
    token = payload.get("token") if isinstance(payload, dict) else None
    if not token or not isinstance(token, str):
        return None, "POST /auth/password JSON had no token"
    return token, ""


def _check_health(client: httpx.Client, config: SmokeConfig) -> HealthResult:
    try:
        response = client.get("/health", headers=_headers(config, None))
    except httpx.HTTPError as exc:
        return HealthResult(
            status=None,
            reported=None,
            ok=False,
            reason=f"unreachable: {type(exc).__name__}: {exc}",
        )
    if response.status_code != 200:
        return HealthResult(
            status=response.status_code,
            reported=None,
            ok=False,
            reason=f"HTTP {response.status_code}",
        )
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return HealthResult(
            status=response.status_code,
            reported=None,
            ok=False,
            reason="body is not JSON",
        )
    if not isinstance(payload, dict) or "status" not in payload:
        return HealthResult(
            status=response.status_code,
            reported=None,
            ok=False,
            reason="JSON has no status field",
        )
    reported = str(payload["status"])
    ok = reported.lower() == "healthy"
    return HealthResult(
        status=response.status_code,
        reported=reported,
        ok=ok,
        reason="ok" if ok else f"reported {reported}",
    )


def _check_mode(
    client: httpx.Client, config: SmokeConfig, mode: str, token: str | None
) -> ModeResult:
    try:
        response = client.get(
            "/projects",
            params={"mode": mode},
            headers=_headers(config, token),
        )
    except httpx.HTTPError as orig:
        return ModeResult(
            mode=mode,
            status=None,
            count=None,
            ok=False,
            reason=f"unreachable: {type(orig).__name__}: {orig}",
        )

    status = response.status_code

    if status in (401, 403):
        reason = f"HTTP {status} (auth)"
        if config.require_auth:
            return ModeResult(mode, status, None, False, reason)
        return ModeResult(mode, status, None, True, reason)

    if status != 200:
        return ModeResult(mode, status, None, False, f"HTTP {status}")

    try:
        payload = response.json()
    except json.JSONDecodeError:
        return ModeResult(mode, status, None, False, "body is not JSON")

    if not isinstance(payload, list):
        return ModeResult(
            mode, status, None, False, f"JSON is {type(payload).__name__}, not array"
        )

    if not cors_allows_origin(response, config.origin):
        acao = response.headers.get("access-control-allow-origin")
        return ModeResult(
            mode,
            status,
            len(payload),
            False,
            f"missing CORS (access-control-allow-origin={acao!r})",
        )

    return ModeResult(mode, status, len(payload), True, "ok")


def _mutate_mode(
    client: httpx.Client, config: SmokeConfig, mode: str, token: str | None
) -> str | None:
    """Create a throwaway project and delete it. Return an error string or None."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{SMOKE_NAME_PREFIX} {stamp} {mode}"
    headers = _headers(config, token)
    project_id = None
    try:
        created = client.post(
            "/projects",
            json={"name": name, "mode": mode, "settings": {"smoke": True}},
            headers=headers,
        )
    except httpx.HTTPError as exc:
        return f"create {mode} unreachable: {type(exc).__name__}: {exc}"

    if created.status_code not in (200, 201):
        return f"create {mode} HTTP {created.status_code}"
    try:
        body = created.json()
    except json.JSONDecodeError:
        return f"create {mode} returned non-JSON"
    if not isinstance(body, dict) or "id" not in body:
        return f"create {mode} JSON had no id"
    project_id = body["id"]

    try:
        deleted = client.delete(f"/projects/{project_id}", headers=headers)
    except httpx.HTTPError as exc:
        return (
            f"delete {mode} {project_id} unreachable after create "
            f"({type(exc).__name__}: {exc}) — leftover smoke project"
        )
    if deleted.status_code not in (200, 204):
        return (
            f"delete {mode} {project_id} HTTP {deleted.status_code} "
            "— leftover smoke project"
        )
    return None


def run_smoke(config: SmokeConfig, client: httpx.Client | None = None) -> SmokeReport:
    if client is not None:
        return _run(config, client)

    transport = httpx.HTTPTransport(local_address="0.0.0.0")
    with httpx.Client(
        base_url=config.base_url,
        timeout=config.timeout,
        transport=transport,
        follow_redirects=False,
    ) as owned:
        return _run(config, owned)


def _run(config: SmokeConfig, client: httpx.Client) -> SmokeReport:
    token, auth_warning = _mint_session(client, config)
    auth_via = "session" if token else "none"
    if auth_warning:
        print(f"warning: {auth_warning}", file=sys.stderr)
    auth_ok = True
    if config.require_auth and not token:
        auth_ok = False
        if not auth_warning:
            print(
                "warning: SMOKE_REQUIRE_AUTH=1 but no session token "
                "(set SMOKE_EMAIL and SMOKE_PASSWORD)",
                file=sys.stderr,
            )

    health = _check_health(client, config)
    reported = health.reported or "?"
    print(f"health status={health.status} reported={reported}")
    if not health.ok:
        print(f"  FAIL: {health.reason}", file=sys.stderr)

    modes: list[ModeResult] = []
    for mode in CANVAS_MODES:
        result = _check_mode(client, config, mode, token)
        modes.append(result)
        count = result.count if result.count is not None else "?"
        line = f"mode={mode} status={result.status} count={count}"
        if result.ok:
            print(line)
        else:
            print(f"{line} FAIL: {result.reason}")
        if result.status in (401, 403) and result.ok:
            print(
                f"warning: mode={mode} HTTP {result.status}; "
                "unauthenticated list is allowed only while AUTH_MODE is log. "
                "Set SMOKE_EMAIL+SMOKE_PASSWORD (and SMOKE_REQUIRE_AUTH=1 once "
                "enforce is on).",
                file=sys.stderr,
            )

    mutate_ok = True
    if not config.readonly:
        for mode in CANVAS_MODES:
            err = _mutate_mode(client, config, mode, token)
            if err:
                mutate_ok = False
                print(f"mutate {mode} FAIL: {err}", file=sys.stderr)
            else:
                print(f"mutate {mode} created+deleted ok")

    ok = auth_ok and health.ok and all(m.ok for m in modes) and mutate_ok
    print("SMOKE PASS" if ok else "SMOKE FAIL")
    return SmokeReport(ok=ok, modes=modes, health=health, auth_via=auth_via)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config()
    if getattr(args, "base_url", None):
        config.base_url = _strip_slash(args.base_url)
    if getattr(args, "email", None):
        config.email = args.email
    if getattr(args, "password", None):
        config.password = args.password
    if getattr(args, "readonly", False):
        config.readonly = True
    if getattr(args, "require_auth", False):
        config.require_auth = True
    print(f"target={config.base_url} origin={config.origin} readonly={config.readonly}")
    report = run_smoke(config)
    return 0 if report.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smoke_projects_modes.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Smoke GET /projects?mode= for every Upload Canvas mode, plus /health. "
            "Empty lists pass; HTTP 500, non-JSON bodies, and missing CORS fail."
        ),
        epilog="""
After a Railway deploy (Firebot / Ian), from the repo root:

  SMOKE_BASE_URL=https://backendfornextapp-production.up.railway.app \\
  SMOKE_EMAIL=ian@firedynamicsgroup.com SMOKE_PASSWORD=… \\
  python scripts/smoke_projects_modes.py

Dev (separate DB — do not assume the same project counts):

  SMOKE_BASE_URL=https://backendfornextapp-dev.up.railway.app \\
  python scripts/smoke_projects_modes.py

Env:
  SMOKE_BASE_URL / API_BASE   API origin (default: production)
  SMOKE_EMAIL                 FDG address for POST /auth/password
  SMOKE_PASSWORD              else APP_PASSWORD (Railway reuse)
  SMOKE_READONLY=1            skip throwaway create/delete
  SMOKE_REQUIRE_AUTH=1        fail if a session token was not minted
                              (needed once AUTH_MODE=enforce)
  SMOKE_ORIGIN                default https://upload-canvas.vercel.app

Empty mode lists are OK (prod timeEq is often 0). 500s and missing
access-control-allow-origin are not. Does not drive interactive Entra.
""".rstrip(),
    )
    parser.add_argument("--base-url", help="API origin (else SMOKE_BASE_URL / API_BASE)")
    parser.add_argument("--email", help="else SMOKE_EMAIL")
    parser.add_argument("--password", help="else SMOKE_PASSWORD / APP_PASSWORD")
    parser.add_argument(
        "--readonly",
        action="store_true",
        help="skip throwaway create/delete (SMOKE_READONLY=1)",
    )
    parser.add_argument(
        "--require-auth",
        action="store_true",
        help="fail without a minted session (SMOKE_REQUIRE_AUTH=1)",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
