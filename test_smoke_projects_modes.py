"""Post-deploy smoke for GET /projects?mode= across Upload Canvas modes.

The 2026-09 production incident: GET /projects?mode=fdsGen 500'd (missing
`projects.mode` column). The browser reported CORS because the 500 body had no
ACAO headers. We only smoked fdsGen, so empty/broken timeEq, radiation, and efs
lists went unnoticed. This gate hits all four modes.

Tests mock the live HTTP surface of the smoke helpers (httpx.MockTransport) —
no Railway, no Entra. Empty arrays must pass; 500 / non-JSON / missing CORS
must fail. Password mint is used when configured so CI never drives SSO.
"""
from __future__ import annotations

import json

import httpx
import pytest

from ops.projects_smoke import (
    CANVAS_MODES,
    CANVAS_ORIGIN,
    DEFAULT_BASE_URL,
    SmokeConfig,
    load_config,
    run_smoke,
)


TOKEN = "session.jwt.token"
BASE = "https://backendfornextapp-production.up.railway.app"


def _cors(origin: str | None = CANVAS_ORIGIN, star: bool = False) -> dict[str, str]:
    value = "*" if star else (origin or CANVAS_ORIGIN)
    return {"access-control-allow-origin": value}


def _json(body, status=200, headers=None) -> httpx.Response:
    return httpx.Response(
        status,
        json=body,
        headers=headers or _cors(),
    )


def _config(**overrides) -> SmokeConfig:
    defaults = dict(
        base_url=BASE,
        email=None,
        password=None,
        require_auth=False,
        readonly=True,
        origin=CANVAS_ORIGIN,
        timeout=5.0,
    )
    defaults.update(overrides)
    return SmokeConfig(**defaults)


def _client_for(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=BASE,
        timeout=5.0,
    )


def _healthy_handler(
    *,
    lists: dict[str, list] | None = None,
    fail_modes: dict[str, httpx.Response] | None = None,
    health_body=None,
    health_status=200,
    health_headers=None,
    password_response: httpx.Response | None = None,
    create_response: httpx.Response | None = None,
    delete_status=204,
    seen: list | None = None,
):
    lists = lists if lists is not None else {mode: [{"id": mode}] for mode in CANVAS_MODES}
    fail_modes = fail_modes or {}
    health_body = {"status": "healthy"} if health_body is None else health_body
    seen = seen if seen is not None else []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        mode = request.url.params.get("mode")

        if path.rstrip("/") == "/health":
            if isinstance(health_body, str):
                return httpx.Response(
                    health_status,
                    text=health_body,
                    headers=health_headers or _cors(),
                )
            return httpx.Response(
                health_status,
                json=health_body,
                headers=health_headers or _cors(),
            )

        if path == "/auth/password" and request.method == "POST":
            if password_response is not None:
                return password_response
            return httpx.Response(503, json={"detail": "Password sign-in is not enabled."})

        if path == "/projects" and request.method == "POST":
            if create_response is not None:
                return create_response
            return _json({"id": "00000000-0000-0000-0000-000000000001", "name": "smoke", "mode": "fdsGen"}, status=201)

        if path.startswith("/projects/") and request.method == "DELETE":
            return httpx.Response(delete_status)

        if path == "/projects" and request.method == "GET":
            if mode in fail_modes:
                return fail_modes[mode]
            if mode not in lists:
                return httpx.Response(404, text="missing mock for mode")
            return _json(lists[mode])

        return httpx.Response(404, text=f"unhandled {request.method} {path}")

    return handler, seen


def _run(handler, config=None, seen=None):
    cfg = config or _config()
    with _client_for(handler) as client:
        return run_smoke(cfg, client=client)


# --------------------------------------------------------------------------
# All four canvas modes
# --------------------------------------------------------------------------


class TestAllModesPolled:
    def test_gets_every_upload_canvas_mode(self):
        handler, seen = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})
        result = _run(handler)
        assert result.ok is True

        listed = [
            req.url.params.get("mode")
            for req in seen
            if req.method == "GET" and req.url.path == "/projects"
        ]
        assert listed == list(CANVAS_MODES)

    def test_sends_upload_canvas_origin(self):
        handler, seen = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})
        _run(handler)
        project_gets = [
            req for req in seen if req.method == "GET" and req.url.path == "/projects"
        ]
        assert project_gets
        assert all(req.headers.get("origin") == CANVAS_ORIGIN for req in project_gets)

    def test_summary_line_per_mode(self, capsys):
        handler, _ = _healthy_handler(
            lists={
                "fdsGen": [{"id": "1"}, {"id": "2"}],
                "timeEq": [],
                "radiation": [{"id": "r"}],
                "efs": [{"id": "e1"}, {"id": "e2"}, {"id": "e3"}],
            }
        )
        _run(handler)
        out = capsys.readouterr().out
        assert "mode=fdsGen status=200 count=2" in out
        assert "mode=timeEq status=200 count=0" in out
        assert "mode=radiation status=200 count=1" in out
        assert "mode=efs status=200 count=3" in out


class TestEmptyArrayPasses:
    """Prod legitimately has 0 timeEq projects. Empty is not a failure."""

    def test_all_modes_empty_is_ok(self):
        handler, _ = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})
        result = _run(handler)
        assert result.ok is True
        assert all(m.count == 0 for m in result.modes)
        assert all(m.ok for m in result.modes)


class TestServerErrorFails:
    def test_500_on_one_mode_fails_the_gate(self):
        handler, _ = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            fail_modes={
                "timeEq": httpx.Response(
                    500,
                    text="WITHIN GROUP is required for ordered-set aggregate mode",
                    headers=_cors(),
                )
            },
        )
        result = _run(handler)
        assert result.ok is False
        teq = next(m for m in result.modes if m.mode == "timeEq")
        assert teq.ok is False
        assert teq.status == 500
        assert any(m.ok and m.mode == "fdsGen" for m in result.modes)

    def test_500_without_cors_is_reported_as_http_error_not_cors(self):
        """The original misdiagnosis: a 500 with no ACAO looks like CORS in
        the browser. The smoke must call it a 500."""
        handler, _ = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            fail_modes={"radiation": httpx.Response(500, text="Internal Server Error")},
        )
        result = _run(handler)
        rad = next(m for m in result.modes if m.mode == "radiation")
        assert rad.ok is False
        assert "500" in rad.reason
        assert "cors" not in rad.reason.lower()


class TestMissingCorsFails:
    def test_200_array_without_acao_fails(self):
        handler, _ = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            fail_modes={"efs": httpx.Response(200, json=[])},
        )
        result = _run(handler)
        assert result.ok is False
        efs = next(m for m in result.modes if m.mode == "efs")
        assert efs.ok is False
        assert efs.status == 200
        assert "cors" in efs.reason.lower()

    def test_star_acao_is_accepted(self):
        handler, _ = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            fail_modes={"efs": _json([], headers=_cors(star=True))},
        )
        result = _run(handler)
        assert result.ok is True

    def test_non_json_200_fails(self):
        handler, _ = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            fail_modes={
                "fdsGen": httpx.Response(
                    200, text="<html>not json</html>", headers=_cors()
                )
            },
        )
        result = _run(handler)
        assert result.ok is False
        fds = next(m for m in result.modes if m.mode == "fdsGen")
        assert "json" in fds.reason.lower()


class TestHealth:
    def test_healthy_200_passes(self, capsys):
        handler, seen = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})
        result = _run(handler)
        assert result.ok is True
        assert result.health.ok is True
        assert any(req.url.path.rstrip("/") == "/health" for req in seen)
        assert "health status=200 reported=healthy" in capsys.readouterr().out

    def test_health_500_fails(self):
        handler, _ = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            health_status=500,
            health_body="Internal Server Error",
        )
        result = _run(handler)
        assert result.ok is False
        assert result.health.ok is False
        assert result.health.status == 500


class TestPasswordMint:
    def test_posts_password_then_sends_bearer(self):
        handler, seen = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            password_response=_json({"token": TOKEN, "email": "ian@firedynamicsgroup.com"}),
        )
        result = _run(
            handler,
            config=_config(email="ian@firedynamicsgroup.com", password="secret"),
        )
        assert result.ok is True
        assert result.auth_via == "session"

        password_posts = [req for req in seen if req.url.path == "/auth/password"]
        assert len(password_posts) == 1
        body = json.loads(password_posts[0].content)
        assert body == {"email": "ian@firedynamicsgroup.com", "password": "secret"}

        project_gets = [
            req for req in seen if req.method == "GET" and req.url.path == "/projects"
        ]
        assert project_gets
        assert all(
            req.headers.get("authorization") == f"Bearer {TOKEN}" for req in project_gets
        )

    def test_503_continues_unauthenticated_with_warning(self, capsys):
        handler, seen = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})
        result = _run(
            handler,
            config=_config(email="ian@firedynamicsgroup.com", password="secret"),
        )
        assert result.ok is True
        assert result.auth_via == "none"
        err = capsys.readouterr().err
        assert "503" in err
        project_gets = [
            req for req in seen if req.method == "GET" and req.url.path == "/projects"
        ]
        assert all("authorization" not in req.headers for req in project_gets)

    def test_503_fails_when_auth_required(self):
        handler, _ = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})
        result = _run(
            handler,
            config=_config(
                email="ian@firedynamicsgroup.com",
                password="secret",
                require_auth=True,
            ),
        )
        assert result.ok is False
        assert result.auth_via == "none"

    def test_list_401_passes_unless_auth_required(self, capsys):
        """Unauthenticated CI against AUTH_MODE=enforce must not look like a
        /projects 500. Document that enforce needs SMOKE_EMAIL+SMOKE_PASSWORD."""
        unauthorized = httpx.Response(
            401, json={"detail": "Authentication required."}, headers=_cors()
        )
        handler, _ = _healthy_handler(
            lists={mode: [] for mode in CANVAS_MODES},
            fail_modes={mode: unauthorized for mode in CANVAS_MODES},
        )
        result = _run(handler)
        assert result.ok is True
        assert "401" in capsys.readouterr().err

        required = _run(handler, config=_config(require_auth=True))
        assert required.ok is False


class TestReadonlySkipsMutations:
    def test_readonly_does_not_post_or_delete(self):
        handler, seen = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})
        result = _run(handler, config=_config(readonly=True))
        assert result.ok is True
        assert not any(req.method == "POST" and req.url.path == "/projects" for req in seen)
        assert not any(req.method == "DELETE" for req in seen)

    def test_create_then_delete_per_mode_when_not_readonly(self):
        created = []

        def create_response_for(request):
            body = json.loads(request.content)
            pid = f"11111111-1111-1111-1111-{body['mode'][:12].ljust(12, '0')}"
            created.append((body["mode"], pid, body["name"]))
            return _json({"id": pid, "name": body["name"], "mode": body["mode"]}, status=201)

        handler, seen = _healthy_handler(lists={mode: [] for mode in CANVAS_MODES})

        def wrapping(request: httpx.Request) -> httpx.Response:
            if request.method == "POST" and request.url.path == "/projects":
                return create_response_for(request)
            return handler(request)

        result = _run(wrapping, config=_config(readonly=False))
        assert result.ok is True
        assert {mode for mode, _, _ in created} == set(CANVAS_MODES)
        assert all("[smoke]" in name for _, _, name in created)

        deleted = [
            req.url.path
            for req in seen
            if req.method == "DELETE"
        ]
        # the wrapper handles POST, so DELETE still hits the original handler via wrapping...
        # actually wrapping only special-cases POST; DELETE goes to handler which records in `seen`.
        assert len([req for req in seen if req.method == "DELETE"]) == len(CANVAS_MODES)


class TestConfigFromEnv:
    def test_defaults_to_production_url(self, monkeypatch):
        monkeypatch.delenv("SMOKE_BASE_URL", raising=False)
        monkeypatch.delenv("API_BASE", raising=False)
        cfg = load_config()
        assert cfg.base_url == DEFAULT_BASE_URL
        assert cfg.readonly is False

    def test_api_base_override(self, monkeypatch):
        monkeypatch.setenv("API_BASE", "https://backendfornextapp-dev.up.railway.app")
        monkeypatch.delenv("SMOKE_BASE_URL", raising=False)
        cfg = load_config()
        assert cfg.base_url == "https://backendfornextapp-dev.up.railway.app"

    def test_smoke_base_url_wins_over_api_base(self, monkeypatch):
        monkeypatch.setenv("API_BASE", "https://dev.example")
        monkeypatch.setenv("SMOKE_BASE_URL", "https://prod.example")
        cfg = load_config()
        assert cfg.base_url == "https://prod.example"

    def test_password_falls_back_to_app_password(self, monkeypatch):
        monkeypatch.setenv("SMOKE_EMAIL", "ian@firedynamicsgroup.com")
        monkeypatch.delenv("SMOKE_PASSWORD", raising=False)
        monkeypatch.setenv("APP_PASSWORD", "from-railway")
        cfg = load_config()
        assert cfg.email == "ian@firedynamicsgroup.com"
        assert cfg.password == "from-railway"

    def test_readonly_flag(self, monkeypatch):
        monkeypatch.setenv("SMOKE_READONLY", "1")
        assert load_config().readonly is True


class TestCliHelp:
    def test_help_mentions_ian_run_command(self):
        from ops.projects_smoke import build_parser

        help_text = build_parser().format_help()
        assert "SMOKE_BASE_URL" in help_text
        assert "SMOKE_EMAIL" in help_text
        assert "SMOKE_PASSWORD" in help_text
        assert "python scripts/smoke_projects_modes.py" in help_text
        assert "empty" in help_text.lower()
