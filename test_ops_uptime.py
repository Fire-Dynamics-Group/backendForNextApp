"""Tests for ops/uptime.py - uptime classification for FD services.

The classifier is deliberately pure (status code + body snippet + error in,
verdict out) so the interesting decisions are testable without any network.
"""
import pytest

from ops.uptime import Verdict, classify

TUNNEL_AUTH_BODY = '{"message":"Authentication required."}'
INTERSTITIAL_BODY = (
    '<html><head><meta name="twitter:card" content="summary">'
    "<title>Tunnel notice</title></head><body>continue</body></html>"
)
APP_LOGIN_BODY = '<html><body><form action="/api/login">password</form></body></html>'


class TestReachableAndServing:
    def test_200_from_app_is_up(self):
        result = classify(status=200, body=APP_LOGIN_BODY, error=None)
        assert result.verdict is Verdict.UP

    def test_redirect_to_login_is_up(self):
        """Prod `/` 307s to /login when the password gate is active. The gate
        answering at all proves Next is serving."""
        result = classify(status=307, body="", error=None)
        assert result.verdict is Verdict.UP


class TestDown:
    def test_connection_error_is_down(self):
        result = classify(status=None, body="", error="connection refused")
        assert result.verdict is Verdict.DOWN
        assert "connection refused" in result.reason

    def test_timeout_is_down(self):
        result = classify(status=None, body="", error="timed out after 20s")
        assert result.verdict is Verdict.DOWN

    def test_500_is_down(self):
        result = classify(status=500, body="Internal Server Error", error=None)
        assert result.verdict is Verdict.DOWN

    def test_502_bad_gateway_is_down(self):
        """The tunnel is up but nothing is listening behind it - this is
        exactly the 'needs a restart' failure mode."""
        result = classify(status=502, body="", error=None)
        assert result.verdict is Verdict.DOWN


class TestUnknownNotDown:
    """The false-alarm guards. A monitor that cries wolf gets switched off, so
    'the tunnel would not let us ask' must never be reported as 'server down'."""

    def test_tunnel_auth_challenge_is_unknown(self):
        result = classify(status=401, body=TUNNEL_AUTH_BODY, error=None)
        assert result.verdict is Verdict.UNKNOWN
        assert "tunnel" in result.reason.lower()

    def test_403_is_unknown(self):
        result = classify(status=403, body="", error=None)
        assert result.verdict is Verdict.UNKNOWN

    def test_interstitial_page_is_unknown_despite_200(self):
        """A 200 carrying the devtunnel anti-phishing interstitial is not our
        app answering - same fingerprint verify-dev.ps1 checks for."""
        result = classify(status=200, body=INTERSTITIAL_BODY, error=None)
        assert result.verdict is Verdict.UNKNOWN
        assert "interstitial" in result.reason.lower()


class TestProbeRequestShape:
    """Regression guard. Dropping any of these three header choices makes the
    devtunnel answer with a challenge page instead of the app - which the
    classifier then reports as UNKNOWN forever, i.e. a monitor that never
    reports anything. Cost real debugging to find; keep it pinned."""

    def _captured_request(self):
        import httpx

        from ops import uptime

        seen = {}

        def handler(request):
            seen["headers"] = request.headers
            return httpx.Response(200, text="<html>Email Search</html>")

        real_client = httpx.Client

        def fake_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        original = httpx.Client
        httpx.Client = fake_client
        try:
            result = uptime.probe("https://example.invalid/login")
        finally:
            httpx.Client = original
        return seen["headers"], result

    def test_sends_antiphishing_skip_header(self):
        headers, _ = self._captured_request()
        assert headers.get("x-tunnel-skip-antiphishing-page") == "true"

    def test_accept_is_not_navigation_shaped(self):
        """Accept: text/html triggers the interstitial; */* does not."""
        headers, _ = self._captured_request()
        assert "text/html" not in headers.get("accept", "")

    def test_sends_browser_user_agent(self):
        headers, _ = self._captured_request()
        assert "Mozilla/5.0" in headers.get("user-agent", "")

    def test_probe_returns_up_for_healthy_response(self):
        _, result = self._captured_request()
        assert result.verdict is Verdict.UP


class TestReasonIsAlwaysUseful:
    @pytest.mark.parametrize(
        "status,body,error",
        [
            (200, APP_LOGIN_BODY, None),
            (307, "", None),
            (500, "", None),
            (401, TUNNEL_AUTH_BODY, None),
            (None, "", "boom"),
        ],
    )
    def test_reason_is_non_empty(self, status, body, error):
        assert classify(status=status, body=body, error=error).reason.strip()
