"""Tests for fee proposal generation audit logging (inputs, Synergy gaps, and actor)."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import database
from database import Base
from models.db_models import FeeProposalGeneration


def _base_payload(company_name="Amazon UK", project_location="Dunstable"):
    return {
        "client": {
            "first_name": "Jane",
            "surname": "Doe",
            "company_name": company_name,
            "address_lines": ["1 High St", "Dunstable"],
        },
        "project": {
            "project_name": "Amazon Dunstable",
            "project_location": project_location,
            "country": "EW",
            "vat_applicable": True,
            "legislation": "",
        },
        "fee_options": {
            "engineer_name": "Sam Bennett",
            "pii_limit": 100000,
            "include_hourly_rates": False,
        },
        "design_stages_1_4": {
            "stage_1": {"included": True, "fee": 2500},
        },
    }


@pytest.mark.asyncio
async def test_render_stores_inputs_synergy_gaps_and_filters_ian_tests(monkeypatch, tmp_path):
    from main import app
    from routers import word_fee

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[FeeProposalGeneration.__table__])
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "async_session", session_factory)
    monkeypatch.setattr(word_fee, "LOCAL_WORD_STORE", tmp_path / "word-text.json")

    colleague_payload = {
        **_base_payload(),
        "generation_context": {
            "user_email": "sam@firedynamicsgroup.com",
            "user_name": "Sam Bennett",
            "synergy_project_ref": "synergy:5466:2665297",
            "synergy_project_label": "0400 Amazon Dunstable",
            "prefill_statuses": {
                "client_lookup": "done",
                "client_status": "no_client_role",
                "company_contacts_lookup": "not_applicable",
                "site_address_present": False,
                "fields": {
                    "projectName": "from_synergy",
                    "projectCountry": "missing",
                    "clientFirstName": "no_client_role",
                    "clientSurname": "no_client_role",
                    "clientCompanyName": "no_client_role",
                    "clientAddressLines": "no_client_role",
                },
            },
            "provenance": {
                "company": None,
                "names": None,
                "address": None,
                "projectName": {"kind": "synergy"},
                "country": None,
                "engineer": {"kind": "microsoft"},
            },
            "client_role_notice": "No Client role is assigned in Total Synergy for this project.",
        },
    }

    ian_payload = {
        **_base_payload(company_name="", project_location=""),
        "generation_context": {
            "user_email": "ian@firedynamicsgroup.com",
            "user_name": "Ian Shaw",
            "synergy_project_ref": "synergy:5466:2694397",
            "synergy_project_label": "0406 Test",
            "prefill_statuses": {
                "client_lookup": "done",
                "client_status": "found",
                "company_contacts_lookup": "done",
                "site_address_present": True,
                "fields": {
                    "projectName": "from_synergy",
                    "projectCountry": "from_synergy",
                    "clientFirstName": "from_synergy",
                    "clientSurname": "from_synergy",
                    "clientCompanyName": "from_synergy",
                    "clientAddressLines": "from_synergy",
                },
            },
        },
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/word/fee-proposal/render", json=colleague_payload)
        assert r1.status_code == 200

        r2 = await client.post("/word/fee-proposal/render", json=ian_payload)
        assert r2.status_code == 200

        # Default: Ian's test runs are excluded
        res_default = await client.get("/word/fee-proposal/generations")
        assert res_default.status_code == 200
        rows = res_default.json()
        assert len(rows) == 1
        row = rows[0]
        assert row["user_email"] == "sam@firedynamicsgroup.com"
        assert row["is_test"] is False
        assert row["synergy_project_ref"] == "synergy:5466:2665297"
        assert row["has_missing_or_edited"] is True
        assert "client_role:no_client_role" in row["missing_from_synergy"]
        assert "site_address" in row["missing_from_synergy"]
        assert "projectCountry:missing" in row["missing_from_synergy"]
        assert set(row["user_filled_missing"]) >= {
            "client_first_name",
            "client_surname",
            "client_company_name",
            "client_address_lines",
            "project_country",
            "project_location",
        }
        assert row["inputs"]["client"]["company_name"] == "Amazon UK"
        assert row["inputs"]["design_stages_1_4"]["stage_1"]["fee"] == 2500

        # include_tests=true returns both
        res_all = await client.get("/word/fee-proposal/generations", params={"include_tests": "true"})
        assert res_all.status_code == 200
        all_rows = res_all.json()
        assert len(all_rows) == 2
        ian_row = next(r for r in all_rows if r["user_email"] == "ian@firedynamicsgroup.com")
        assert ian_row["is_test"] is True
        assert ian_row["has_missing_or_edited"] is False

    await engine.dispose()


@pytest.mark.asyncio
async def test_render_succeeds_even_if_audit_db_fails(monkeypatch, tmp_path):
    from main import app
    from routers import word_fee
    from services import fee_generation_log

    monkeypatch.setattr(database, "async_session", None)
    monkeypatch.setattr(word_fee, "LOCAL_WORD_STORE", tmp_path / "word-text.json")

    async def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(fee_generation_log, "FeeProposalGeneration", boom)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.post("/word/fee-proposal/render", json=_base_payload())
        assert r.status_code == 200
