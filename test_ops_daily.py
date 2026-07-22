"""Tests for ops/daily.py - the estate registry and the run's exit code.

The exit code *is* the alert (a failed Railway run rides the platform's own
notifications), so the rule that turns a set of verdicts into 0 or 1 is the
most load-bearing logic here and is kept pure and tested.
"""
import pytest

from ops.daily import SERVICES, Service, exit_code
from ops.uptime import CheckResult, Verdict


def result(verdict: Verdict) -> CheckResult:
    return CheckResult(verdict, "reason")


class TestExitCode:
    def test_all_up_exits_zero(self):
        assert exit_code([result(Verdict.UP), result(Verdict.UP)]) == 0

    def test_any_down_exits_one(self):
        assert exit_code([result(Verdict.UP), result(Verdict.DOWN)]) == 1

    def test_unknown_alone_exits_zero(self):
        """UNKNOWN means "could not ask", not "is broken". Paging on it is how
        a monitor earns its way onto the ignore list."""
        assert exit_code([result(Verdict.UP), result(Verdict.UNKNOWN)]) == 0

    def test_down_still_wins_when_mixed_with_unknown(self):
        assert exit_code([result(Verdict.UNKNOWN), result(Verdict.DOWN)]) == 1

    def test_empty_exits_zero(self):
        assert exit_code([]) == 0


class TestEstateRegistry:
    """Guards against the registry rotting as services are added."""

    def test_registry_is_not_empty(self):
        assert SERVICES

    def test_every_service_has_a_url(self):
        for service in SERVICES:
            assert service.url.startswith("http"), service.name

    def test_names_are_unique(self):
        names = [s.name for s in SERVICES]
        assert len(names) == len(set(names))

    def test_env_vars_are_unique(self):
        """A duplicated override would silently point two checks at one URL."""
        env_vars = [s.env_var for s in SERVICES]
        assert len(env_vars) == len(set(env_vars))

    def test_env_vars_follow_convention(self):
        for service in SERVICES:
            assert service.env_var.isupper(), service.env_var
            assert service.env_var.endswith("_PROBE_URL"), service.env_var

    def test_deep_checks_point_at_a_health_path(self):
        """A deep check reads a JSON health payload - pointing one at `/` would
        always report UNKNOWN once it failed to parse the HTML."""
        for service in SERVICES:
            if service.deep:
                assert service.url.rstrip("/").endswith("/health"), service.name

    def test_the_data_owning_backends_are_checked_deeply(self):
        """These two own Postgres and MinIO. Liveness alone cannot see a dead
        database behind a serving API - the failure mode that bit us."""
        deep = {s.name for s in SERVICES if s.deep}
        assert "mobile backend" in deep
        assert "backendForNextApp (prod)" in deep


class TestServiceUrlResolution:
    def test_env_var_overrides_the_default_url(self, monkeypatch):
        service = Service(
            name="x", env_var="X_PROBE_URL", url="https://default.example"
        )
        monkeypatch.setenv("X_PROBE_URL", "https://override.example")
        assert service.resolved_url() == "https://override.example"

    def test_falls_back_to_the_pinned_default(self, monkeypatch):
        service = Service(
            name="x", env_var="X_PROBE_URL", url="https://default.example"
        )
        monkeypatch.delenv("X_PROBE_URL", raising=False)
        assert service.resolved_url() == "https://default.example"
