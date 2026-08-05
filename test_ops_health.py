"""Tests for ops/health.py - reading a service's own health verdict.

uptime.classify answers "is something serving". That is not enough for the
services that own data: a FastAPI app happily returns 200 on /docs while its
Postgres or MinIO is dead. The mobile app's S3 bucket went down in exactly this
way - the API stayed green, uploads failed, and the outage was found by hand.

So for services that publish a /health payload we read the payload, not just
the status line. Pure function, no network.
"""
import json

import pytest

from ops.health import classify_health
from ops.uptime import Verdict

HEALTHY = json.dumps({"status": "healthy", "database": True, "storage": True, "errors": []})
STORAGE_DOWN = json.dumps(
    {
        "status": "degraded",
        "database": True,
        "storage": False,
        "errors": ["Storage (MinIO) unreachable or bucket missing - uploads will fail"],
    }
)
DB_DOWN = json.dumps(
    {"status": "unhealthy", "database": False, "errors": ["Database error: timeout"]}
)


class TestHealthyPayload:
    def test_healthy_is_up(self):
        result = classify_health(status=200, body=HEALTHY, error=None)
        assert result.verdict is Verdict.UP


class TestSelfReportedProblemsAreDown:
    """The whole point: a 200 that says "I am broken" must not read as green."""

    def test_degraded_is_down(self):
        result = classify_health(status=200, body=STORAGE_DOWN, error=None)
        assert result.verdict is Verdict.DOWN

    def test_degraded_reason_names_the_broken_dependency(self):
        """The daily log is the first thing read during an incident - it should
        say "storage", not just "degraded"."""
        result = classify_health(status=200, body=STORAGE_DOWN, error=None)
        assert "storage" in result.reason.lower()

    def test_unhealthy_is_down(self):
        result = classify_health(status=200, body=DB_DOWN, error=None)
        assert result.verdict is Verdict.DOWN
        assert "database" in result.reason.lower()


class TestTransportFailuresDeferToUptime:
    """Transport-level judgements keep uptime.py's semantics exactly."""

    def test_unreachable_is_down(self):
        result = classify_health(status=None, body="", error="connection refused")
        assert result.verdict is Verdict.DOWN

    def test_500_is_down(self):
        result = classify_health(status=500, body="", error=None)
        assert result.verdict is Verdict.DOWN

    def test_tunnel_auth_is_unknown_not_down(self):
        result = classify_health(
            status=401, body='{"message":"Authentication required."}', error=None
        )
        assert result.verdict is Verdict.UNKNOWN


class TestUnreadablePayloadIsUnknown:
    """"Served something we cannot parse" is a failure to *ask*, not proof of
    breakage - same reasoning that gives uptime.py its third verdict."""

    def test_html_instead_of_json_is_unknown(self):
        result = classify_health(
            status=200, body="<html><body>hello</body></html>", error=None
        )
        assert result.verdict is Verdict.UNKNOWN

    def test_json_without_status_field_is_unknown(self):
        result = classify_health(status=200, body='{"database": true}', error=None)
        assert result.verdict is Verdict.UNKNOWN

    def test_unrecognised_status_value_is_unknown(self):
        result = classify_health(status=200, body='{"status": "banana"}', error=None)
        assert result.verdict is Verdict.UNKNOWN


class TestReasonIsAlwaysUseful:
    @pytest.mark.parametrize(
        "status,body,error",
        [
            (200, HEALTHY, None),
            (200, STORAGE_DOWN, None),
            (200, DB_DOWN, None),
            (200, "<html>", None),
            (500, "", None),
            (None, "", "boom"),
        ],
    )
    def test_reason_is_non_empty(self, status, body, error):
        assert classify_health(status=status, body=body, error=error).reason.strip()
