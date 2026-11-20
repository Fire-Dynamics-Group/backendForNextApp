"""Tests for template-based collated Structural Fire Report (.docx) generation."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

from docx import Document

from services.structural_fire_report import build_structural_fire_report_docx

# 1x1 valid PNG (base64)
SAMPLE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _make_project(
    name: str = "Apex Logistics Hub",
    settings: dict | None = None,
):
    return SimpleNamespace(
        id="proj-1",
        name=name,
        updated_at=None,
        settings=settings or {},
    )


def _make_run():
    return SimpleNamespace(
        governing_side="B",
        critical_temp=548.5,
        section="UB 457x191x67",
        exposure="3 sides",
        section_factor=145.2,
        inputs={"u_sec_size": "UB 457x191x67"},
        outputs={
            "side_a_sec": "UB 457x191x67",
            "side_a_load_ratio": 0.45,
            "side_a_critical_temp": 580.0,
            "side_b_sec": "UB 457x191x67",
            "side_b_load_ratio": 0.52,
            "side_b_critical_temp": 548.5,
            "side_c_sec": "UB 457x191x67",
            "side_c_load_ratio": 0.41,
            "side_c_critical_temp": 600.0,
            "side_d_sec": "UB 457x191x67",
            "side_d_load_ratio": 0.39,
            "side_d_critical_temp": 612.0,
        },
    )


def _extract_all_xml_text(docx_bytes: bytes) -> str:
    parts = []
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        for name in z.namelist():
            if name.endswith(".xml") and (
                name == "word/document.xml"
                or name.startswith("word/header")
                or name.startswith("word/footer")
            ):
                parts.append(z.read(name).decode("utf-8", errors="ignore"))
    return "\n".join(parts)


def test_collated_report_uses_template_and_strips_panattoni_leakage():
    settings = {
        "reportDetails": {
            "client": "Acme Developments Ltd",
            "location": "Milton Keynes, Buckinghamshire",
            "reportTitle": "Fire Resistance of the Office Composite Floor",
            "author": "Ian Shaw",
            "checkedBy": "Kevin Kurniawan",
            "verifiedBy": "Diana Prostire",
            "buildingDescription": "A two-storey steel-framed office annex attached to a distribution warehouse.",
            "targetReliability": 98.2,
        },
        "macsBatch": {
            "batch_id": "batch-apex-1",
            "name": "Apex Office Floor 1",
            "run_count": 5000,
            "pass_count": 4950,
            "fail_count": 50,
            "error_count": 0,
            "reliability_percent": 99.0,
            "setup": {
                "groups": [
                    {
                        "title": "Geometry",
                        "fields": [
                            {"key": "span1", "label": "Span 1", "unit": "m", "value": 9.0, "varies": False}
                        ],
                    }
                ]
            },
            "shear_check": {"checked": 5000, "sub_limit_runs": []},
            "sample_runs": [
                {
                    "run_id": 1001,
                    "run_number": 101,
                    "total_runs": 5000,
                    "qf": 500.0,
                    "window_percent": 20.0,
                    "uf_max": 0.45,
                    "time_series": [
                        {"time_step": 0, "time_min": 0.0, "fire_temp": 20.0, "lofl_temp": 20.0, "mesh_temp": 20.0, "slabtop_temp": 20.0, "slabbot_temp": 20.0, "beam_hot_capacity": 40.0, "deflection": 100.0, "slab_yield": 1.0, "enhancement": 2.0, "slab_cap": 2.0, "total_plate_capacity": 42.0, "utilization_factor": 0.45}
                    ],
                },
                {
                    "run_id": 1002,
                    "run_number": 202,
                    "total_runs": 5000,
                    "qf": 700.0,
                    "window_percent": 15.0,
                    "uf_max": 0.79,
                    "time_series": [
                        {"time_step": 0, "time_min": 0.0, "fire_temp": 20.0, "lofl_temp": 20.0, "mesh_temp": 20.0, "slabtop_temp": 20.0, "slabbot_temp": 20.0, "beam_hot_capacity": 40.0, "deflection": 100.0, "slab_yield": 1.0, "enhancement": 2.0, "slab_cap": 2.0, "total_plate_capacity": 42.0, "utilization_factor": 0.79}
                    ],
                },
            ],
            "charts": {
                "scatter": SAMPLE_PNG_B64,
                "totalCapacity": SAMPLE_PNG_B64,
                "beamTemp": SAMPLE_PNG_B64,
                "meshTemp": SAMPLE_PNG_B64,
            },
        },
        "timeEqInputs": {
            "mcOccupancy": "Office",
            "fireResistancePeriod": 60,
            "compartmentHeight": 3.6,
            "isSprinklered": False,
            "criticalTemp": 549,
            "sectionFactor": 145,
            "section": "UB 457x191x67",
            "customBValue": "1400",
        },
        "timeEqResult": {
            "failure_prob": 0.012,
            "reliabilityPercent": 98.8,
            "seed": 101,
            "nSim": 10000,
            "nFailed": 120,
            "charts": {
                "steelTempSpaghetti": SAMPLE_PNG_B64,
                "passFailScatter": SAMPLE_PNG_B64,
            },
        },
    }

    docx_bytes = build_structural_fire_report_docx(
        _make_project("Apex Logistics Hub", settings),
        _make_run(),
    )
    doc = Document(io.BytesIO(docx_bytes))
    body_text = "\n".join(p.text for p in doc.paragraphs)
    table_text = "\n".join(
        cell.text for t in doc.tables for row in t.rows for cell in row.cells
    )
    all_xml = _extract_all_xml_text(docx_bytes)

    # 1. House boilerplate & structure preserved from template
    assert "Tensile Membrane Action" in body_text
    assert "Background and Methodology" in body_text
    assert "Assumptions and Limitations" in body_text
    assert "Outcomes and Conclusion" in body_text
    assert "References" in body_text

    # 2. Project-specific metadata slotted in (body, tables, headers, and author email)
    assert "Apex Logistics Hub" in all_xml
    assert "Acme Developments Ltd" in all_xml
    assert "Milton Keynes, Buckinghamshire" in body_text
    assert "Ian Shaw" in table_text
    assert "ian@firedynamicsgroup.com" in all_xml
    assert "diana@firedynamicsgroup.com" not in all_xml
    assert "[Placeholder —" in body_text
    assert "headerReference" in all_xml

    # 3. No Panattoni-specific data or review comments leaked
    for forbidden in ("Panattoni", "Winvic", "Castleford", "AEW Architects", "J&D Pierce", "4,851", "9,882", "98.82%"):
        assert forbidden not in all_xml, f"Leaked template text: {forbidden}"

    # 4. Dynamic MACS+ and Time Eq outcomes & tables present
    assert "5,000" in body_text or "5,000" in table_text
    assert "99.00%" in body_text or "99.00%" in table_text
    assert "98.80%" in body_text or "98.8%" in body_text or "98.80%" in table_text
    assert "UB 457x191x67" in body_text or "UB 457x191x67" in table_text
    assert "548.5" in body_text or "548.5" in table_text

    # Both A.1 and A.2 Sheet 3 Tabular results nested tables must have 12 columns including Unity factor
    nested_tabular = [
        nt
        for tbl in doc.tables
        if tbl.rows and ("A.1." in tbl.rows[0].cells[0].text or "A.2." in tbl.rows[0].cells[0].text)
        and "Sheet 3" in tbl.rows[0].cells[0].text
        for nt in tbl.rows[7].cells[0].tables
    ]
    assert len(nested_tabular) == 2
    for nt in nested_tabular:
        assert len(nt.columns) == 12
        assert "unity factor" in " ".join(nt.rows[0].cells[-1].text.split()).lower()

    # 5. Charts slotted in (4 MACS + 2 Time Eq + static theory images)
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        media_files = [f for f in z.namelist() if f.startswith("word/media/")]
        assert len(media_files) >= 6
        core_xml = z.read("docProps/core.xml").decode("utf-8")
        app_xml = z.read("docProps/app.xml").decode("utf-8")
        assert "Apex Logistics Hub" in core_xml
        assert "Fire Resistance of the Office Composite Floor" in core_xml
        assert "Acme Developments Ltd" in app_xml
        assert "Panattoni" not in core_xml
        assert "Panattoni" not in app_xml
        assert "Winvic" not in app_xml


def test_collated_report_handles_missing_optional_data_honestly():
    docx_bytes = build_structural_fire_report_docx(
        _make_project("Empty Project", {}),
        None,
    )
    doc = Document(io.BytesIO(docx_bytes))
    body_text = "\n".join(p.text for p in doc.paragraphs)
    all_xml = _extract_all_xml_text(docx_bytes)

    assert "Empty Project" in all_xml
    assert "No MACS+" in body_text
    assert "No Monte Carlo Time Equivalence" in body_text
    for forbidden in ("Panattoni", "Winvic", "Castleford", "9,882"):
        assert forbidden not in all_xml
