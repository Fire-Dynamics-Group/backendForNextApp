"""The addressee block of the fee letter, read back from the real .docx.

The Word add-in posts the Client-role company from the project directory as
``client.company_name`` next to the person fields. Project 0406 has a company
with no person, so both person fields arrive empty.
"""
import io
import re

import pytest
from docx import Document
from httpx import ASGITransport, AsyncClient

TAYLOR_WIMPEY_ADDRESS = [
    "The Dock,",
    "Station road, Kings Langley",
    "Hertfordshire",
    "WD4 8LZ",
    "United Kingdom",
]
BLANK = ("Standard_Text_No_Line_Spacing", "")
DATE_LINE = re.compile(r"^\d{1,2}(st|nd|rd|th) [A-Z][a-z]+, \d{4}$")


def _payload(client: dict) -> dict:
    return {
        "client": client,
        "project": {"project_name": "Test Tower", "project_location": "London", "country": "EW"},
        "fee_options": {"engineer_name": "Sam Bennett"},
        "design_stages_1_4": {"stage_1": {"included": True, "fee": 5000}},
    }


async def _render(monkeypatch, tmp_path, client: dict, route="/word/fee-proposal/render"):
    import database
    from main import app
    from routers import word_fee

    monkeypatch.setattr(database, "async_session", None)
    monkeypatch.setattr(word_fee, "LOCAL_WORD_STORE", tmp_path / "word-text.json")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(route, json=_payload(client))
    assert resp.status_code == 200, resp.text
    return Document(io.BytesIO(resp.content))


def _addressee_block(doc):
    """(style, text) of every paragraph after the date line, up to and including Dear."""
    paras = [(p.style.name, p.text) for p in doc.paragraphs]
    date_idx = next(i for i, (_, t) in enumerate(paras) if DATE_LINE.match(t))
    dear_idx = next(i for i, (_, t) in enumerate(paras) if t.startswith("Dear"))
    return paras[date_idx + 1:dear_idx + 1]


@pytest.mark.asyncio
async def test_company_only_client_prints_company_and_address_without_a_person_line(monkeypatch, tmp_path):
    doc = await _render(monkeypatch, tmp_path, {
        "company_name": "Taylor Wimpey North Thames",
        "first_name": "",
        "surname": "",
        "address_lines": TAYLOR_WIMPEY_ADDRESS + [""],
    })

    block = _addressee_block(doc)
    assert block[:-1] == [
        BLANK, BLANK,
        ("Standard_Text", "Taylor Wimpey North Thames"),
        *[("Standard_Text_No_Line_Spacing", line) for line in TAYLOR_WIMPEY_ADDRESS],
        BLANK, BLANK, BLANK,
    ]
    dear_style, dear = block[-1]
    assert dear_style == "Standard_Text"
    assert "Taylor Wimpey" not in dear


@pytest.mark.asyncio
async def test_company_with_person_prints_company_above_person_and_greets_the_person(monkeypatch, tmp_path):
    doc = await _render(monkeypatch, tmp_path, {
        "company_name": "Taylor Wimpey North Thames",
        "first_name": "Ada",
        "surname": "Lovelace",
        "address_lines": TAYLOR_WIMPEY_ADDRESS,
    })

    assert _addressee_block(doc) == [
        BLANK, BLANK,
        ("Standard_Text", "Taylor Wimpey North Thames"),
        ("Standard_Text", "Ada Lovelace"),
        *[("Standard_Text_No_Line_Spacing", line) for line in TAYLOR_WIMPEY_ADDRESS],
        BLANK, BLANK, BLANK,
        ("Standard_Text", "Dear Ada,"),
    ]


@pytest.mark.asyncio
async def test_person_only_request_without_company_field_is_unchanged(monkeypatch, tmp_path):
    doc = await _render(monkeypatch, tmp_path, {
        "first_name": "Test",
        "surname": "Client",
        "address_lines": ["1 Test St"],
    })

    assert _addressee_block(doc) == [
        BLANK, BLANK,
        ("Standard_Text", "Test Client"),
        ("Standard_Text_No_Line_Spacing", "1 Test St"),
        BLANK, BLANK, BLANK,
        ("Standard_Text", "Dear Test,"),
    ]


@pytest.mark.asyncio
async def test_typed_names_are_printed_exactly_as_sent(monkeypatch, tmp_path):
    doc = await _render(monkeypatch, tmp_path, {
        "company_name": "taylor WIMPEY (N. Thames) Ltd",
        "first_name": "ada",
        "surname": "de la Lovelace",
        "address_lines": ["1 Typed Street"],
    })

    block = _addressee_block(doc)
    assert ("Standard_Text", "taylor WIMPEY (N. Thames) Ltd") in block
    assert ("Standard_Text", "ada de la Lovelace") in block
    assert block[-1] == ("Standard_Text", "Dear ada,")


@pytest.mark.asyncio
async def test_web_generate_route_shares_the_company_line(monkeypatch, tmp_path):
    doc = await _render(monkeypatch, tmp_path, {
        "company_name": "Taylor Wimpey North Thames",
        "first_name": "Ada",
        "surname": "Lovelace",
        "address_lines": ["The Dock,"],
    }, route="/fee-proposals/generate")

    texts = [t for _, t in _addressee_block(doc)]
    assert texts.index("Taylor Wimpey North Thames") < texts.index("Ada Lovelace") < texts.index("The Dock,")
