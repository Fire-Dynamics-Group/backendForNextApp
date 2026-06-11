"""Endpoint smoke test for fee proposal generation (#4 router wiring)."""
import os

import pytest
from httpx import ASGITransport, AsyncClient

os.environ["DATABASE_URL"] = ""  # no DB -> _load_text_map falls back to constants

from models.fee_proposal_models import (  # noqa: E402
    FeeProposalRequest, ClientDetails, ProjectDetails, FeeOptions,
    DesignStagesRiba1to4, ServiceConfig, CountryEnum,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.asyncio
async def test_generate_endpoint_without_db_returns_docx():
    from main import app

    req = FeeProposalRequest(
        client=ClientDetails(first_name="Test", surname="Client", address_lines=["1 Test St"]),
        project=ProjectDetails(project_name="Test Tower", project_location="London",
                               country=CountryEnum.ENGLAND_WALES),
        fee_options=FeeOptions(engineer_name="Sam Bennett"),
        design_stages_1_4=DesignStagesRiba1to4(stage_1=ServiceConfig(included=True, fee=5000)),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/fee-proposals/generate", json=req.model_dump(mode="json"))

    assert resp.status_code == 200
    assert DOCX_MIME in resp.headers["content-type"]
    assert len(resp.content) > 1000  # a real document, not an error body
