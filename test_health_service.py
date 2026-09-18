"""Tests for services/health_service.py - what this backend says about itself.

Every FD tool (toolstation, upload-canvas, time-eq, warehouse) posts to this
one backend, and it owns both Postgres and the MinIO bucket. Until now it had
no health endpoint at all: /docs returns 200 whether or not the database is
reachable, so a DB or bucket outage was invisible to monitoring and surfaced as
users reporting breakage.

The aggregation is pure so every status rule is tested without a database.
"""
import pytest

from services.health_service import REQUIRED_TABLES, build_health

ALL_TABLES = {name: True for name in REQUIRED_TABLES}


class TestHealthy:
    def test_everything_up_is_healthy(self):
        payload = build_health(database=True, tables=ALL_TABLES, storage=True)

        assert payload["status"] == "healthy"
        assert payload["database"] is True
        assert payload["storage"] is True
        assert payload["errors"] == []

    def test_reports_the_api_is_answering(self):
        """Trivially true - it is the fact that the payload exists at all."""
        payload = build_health(database=True, tables=ALL_TABLES, storage=True)
        assert payload["api"] is True


class TestDatabaseFailures:
    def test_database_down_is_unhealthy(self):
        payload = build_health(
            database=False, tables={}, storage=True, database_error="timeout"
        )

        assert payload["status"] == "unhealthy"
        assert any("database" in e.lower() for e in payload["errors"])

    def test_database_error_detail_is_surfaced(self):
        payload = build_health(
            database=False, tables={}, storage=True, database_error="password auth failed"
        )
        assert any("password auth failed" in e for e in payload["errors"])

    def test_missing_tables_degrade_and_name_the_tables(self):
        tables = dict(ALL_TABLES)
        tables["elements"] = False

        payload = build_health(database=True, tables=tables, storage=True)

        assert payload["status"] == "degraded"
        assert any("elements" in e for e in payload["errors"])


class TestStorageFailures:
    """The mobile app's bucket went down while its API stayed green. This
    backend uses the same MinIO, so it must be able to report the same fault."""

    def test_storage_down_degrades(self):
        payload = build_health(
            database=True, tables=ALL_TABLES, storage=False, storage_error="connect timeout"
        )

        assert payload["status"] == "degraded"
        assert payload["storage"] is False
        assert any("storage" in e.lower() for e in payload["errors"])

    def test_storage_down_is_never_reported_healthy(self):
        payload = build_health(database=True, tables=ALL_TABLES, storage=False)
        assert payload["status"] != "healthy"


class TestWorstFailureWins:
    def test_database_down_outranks_storage_down(self):
        """A dead database is unhealthy even if storage is also broken -
        the more severe verdict must not be overwritten by the milder one."""
        payload = build_health(
            database=False, tables={}, storage=False, database_error="gone"
        )
        assert payload["status"] == "unhealthy"


class TestPayloadContract:
    """ops/health.classify_health keys off `status`; the daily sweep breaks
    silently if these fields ever go missing."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(database=True, tables=ALL_TABLES, storage=True),
            dict(database=False, tables={}, storage=False),
            dict(database=True, tables={}, storage=True),
        ],
    )
    def test_required_fields_always_present(self, kwargs):
        payload = build_health(**kwargs)
        for field in ("status", "api", "database", "storage", "tables", "errors"):
            assert field in payload

    def test_status_is_one_of_the_three_known_values(self):
        payload = build_health(database=True, tables=ALL_TABLES, storage=True)
        assert payload["status"] in {"healthy", "degraded", "unhealthy"}
