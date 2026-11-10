"""Tests for fee_document_service - verifies expected end date is rendered
in both single-service and multi-service fee proposals."""
import io
import pytest
from docx import Document

from models.fee_proposal_models import (
    FeeProposalRequest,
    ClientDetails,
    ProjectDetails,
    FeeOptions,
    DesignStagesRiba1to4,
    ServiceConfig,
    CountryEnum,
)
from services.fee_document_service import generate_proposal, _safe_format


def test_safe_format_leaves_unknown_tokens_literal():
    # Backstop: a missing/typo'd token degrades to literal text instead of crashing.
    assert _safe_format("Per {legislation} and {unknown}.", legislation="Reg B") == "Per Reg B and {unknown}."


def _base_request(stages_1_4: DesignStagesRiba1to4) -> FeeProposalRequest:
    return FeeProposalRequest(
        client=ClientDetails(first_name="Test", surname="Client", address_lines=["1 Test St"]),
        project=ProjectDetails(project_name="Test Project", project_location="London", country=CountryEnum.ENGLAND_WALES),
        fee_options=FeeOptions(engineer_name="Sam Bennett", pii_limit=100000, include_hourly_rates=False),
        design_stages_1_4=stages_1_4,
    )


def _all_text(buf: io.BytesIO) -> str:
    buf.seek(0)
    doc = Document(buf)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    parts.append(p.text)
    return "\n".join(parts)


class TestExpectedEndDateRendering:
    def test_single_service_with_end_date_renders_expected_end_date(self):
        stages = DesignStagesRiba1to4(
            stage_1=ServiceConfig(included=True, fee=5000, end_date_month="March", end_date_year="2026"),
        )
        buf = generate_proposal(_base_request(stages))
        text = _all_text(buf)
        assert "(expected end date March 2026)" in text

    def test_single_service_with_end_date_appears_after_exc_vat(self):
        stages = DesignStagesRiba1to4(
            stage_1=ServiceConfig(included=True, fee=5000, end_date_month="March", end_date_year="2026"),
        )
        buf = generate_proposal(_base_request(stages))
        text = _all_text(buf)
        assert "exc. VAT (expected end date March 2026)." in text

    def test_single_service_without_end_date_unchanged(self):
        stages = DesignStagesRiba1to4(stage_1=ServiceConfig(included=True, fee=5000))
        buf = generate_proposal(_base_request(stages))
        text = _all_text(buf)
        assert "expected end date" not in text
        assert "exc. VAT." in text

    def test_multi_service_renders_expected_end_date_per_row(self):
        stages = DesignStagesRiba1to4(
            stage_1=ServiceConfig(included=True, fee=5000, end_date_month="March", end_date_year="2026"),
            stage_2=ServiceConfig(included=True, fee=7500, end_date_month="June", end_date_year="2026"),
        )
        buf = generate_proposal(_base_request(stages))
        text = _all_text(buf)
        assert "RIBA Stage 1 (expected end date March 2026)" in text
        assert "RIBA Stage 2 (expected end date June 2026)" in text

    def test_legacy_up_to_phrasing_is_gone(self):
        stages = DesignStagesRiba1to4(
            stage_1=ServiceConfig(included=True, fee=5000, end_date_month="March", end_date_year="2026"),
            stage_2=ServiceConfig(included=True, fee=7500, end_date_month="June", end_date_year="2026"),
        )
        buf = generate_proposal(_base_request(stages))
        text = _all_text(buf)
        assert "(Up to" not in text


def _country_request(country: CountryEnum, vat_applicable: bool = False,
                     include_hourly_rates: bool = True,
                     stages_1_4: DesignStagesRiba1to4 = None,
                     legislation: str = "") -> FeeProposalRequest:
    return FeeProposalRequest(
        client=ClientDetails(first_name="Test", surname="Client", address_lines=["1 Test St"]),
        project=ProjectDetails(project_name="Test Project", project_location="St Peter Port",
                               country=country, vat_applicable=vat_applicable,
                               legislation=legislation),
        fee_options=FeeOptions(engineer_name="Sam Bennett", pii_limit=100000,
                               include_hourly_rates=include_hourly_rates),
        design_stages_1_4=stages_1_4 or DesignStagesRiba1to4(
            stage_1=ServiceConfig(included=True, fee=5000),
        ),
    )


class TestVatByCountry:
    def test_other_country_with_vat_quotes_fees_exclusive_of_vat(self):
        text = _all_text(generate_proposal(
            _country_request(CountryEnum.OTHER, vat_applicable=True)))
        assert "exc. VAT." in text
        assert "exclusive of VAT, " in text
        assert "+VAT" in text

    def test_other_country_without_vat_omits_vat(self):
        text = _all_text(generate_proposal(
            _country_request(CountryEnum.OTHER, vat_applicable=False)))
        assert "VAT" not in text

    def test_other_country_with_vat_notes_vat_under_fee_table(self):
        stages = DesignStagesRiba1to4(
            stage_1=ServiceConfig(included=True, fee=5000),
            stage_2=ServiceConfig(included=True, fee=7500),
        )
        text = _all_text(generate_proposal(
            _country_request(CountryEnum.OTHER, vat_applicable=True, stages_1_4=stages)))
        assert "All fees quoted are exclusive of VAT." in text

    def test_other_country_without_vat_omits_note_under_fee_table(self):
        stages = DesignStagesRiba1to4(
            stage_1=ServiceConfig(included=True, fee=5000),
            stage_2=ServiceConfig(included=True, fee=7500),
        )
        text = _all_text(generate_proposal(
            _country_request(CountryEnum.OTHER, vat_applicable=False, stages_1_4=stages)))
        assert "VAT" not in text

    def test_jersey_ignores_vat_applicable_flag(self):
        text = _all_text(generate_proposal(
            _country_request(CountryEnum.JERSEY, vat_applicable=True)))
        assert "VAT" not in text

    def test_england_wales_ignores_vat_applicable_flag(self):
        text = _all_text(generate_proposal(
            _country_request(CountryEnum.ENGLAND_WALES, vat_applicable=False)))
        assert "exc. VAT." in text


class TestLegislationByCountry:
    _STAGE_3 = DesignStagesRiba1to4(stage_3=ServiceConfig(included=True, fee=9000))

    def test_other_country_quotes_its_own_legislation(self):
        text = _all_text(generate_proposal(_country_request(
            CountryEnum.OTHER, legislation="Test Legislation Reference",
            stages_1_4=self._STAGE_3)))
        assert "requirements of Test Legislation Reference and will also include:" in text
        assert "Building Regulations 2010" not in text

    def test_other_country_without_custom_legislation_falls_back(self):
        text = _all_text(generate_proposal(_country_request(
            CountryEnum.OTHER, stages_1_4=self._STAGE_3)))
        assert "requirements of Building Regulations 2010 (Part B)" in text

    def test_blank_custom_legislation_falls_back(self):
        text = _all_text(generate_proposal(_country_request(
            CountryEnum.OTHER, legislation="   ", stages_1_4=self._STAGE_3)))
        assert "requirements of Building Regulations 2010 (Part B)" in text

    def test_england_wales_ignores_custom_legislation(self):
        text = _all_text(generate_proposal(_country_request(
            CountryEnum.ENGLAND_WALES, legislation="Test Legislation Reference",
            stages_1_4=self._STAGE_3)))
        assert "requirements of Building Regulations 2010 (Part B)" in text

    def test_jersey_ignores_custom_legislation(self):
        text = _all_text(generate_proposal(_country_request(
            CountryEnum.JERSEY, legislation="Test Legislation Reference",
            stages_1_4=self._STAGE_3)))
        assert "requirements of Building Bye Laws (Jersey) 2007 (Part 2)" in text
