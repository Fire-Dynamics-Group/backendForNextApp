"""DOCX report generator for combined MACS+ & Time Equivalence structural fire report."""

from __future__ import annotations

import base64
import io
import re
from typing import Any

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from models.db_models import MacsRun, Project


def _add_b64_image(doc: Document, b64_str: str | None, caption: str, width: Inches = Inches(5.5)) -> bool:
    if not b64_str or not isinstance(b64_str, str):
        return False
    if "base64," in b64_str:
        b64_str = b64_str.split("base64,")[1]
    try:
        raw_bytes = base64.b64decode(b64_str)
        if len(raw_bytes) < 8:
            return False
        p = doc.add_paragraph()
        run = p.add_run(caption)
        run.bold = True
        run.font.size = Pt(10)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

        img_p = doc.add_paragraph()
        img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img_run = img_p.add_run()
        img_run.add_picture(io.BytesIO(raw_bytes), width=width)
        return True
    except Exception as e:
        print(f"Warning: could not add image {caption}: {e}")
        return False


def build_structural_fire_report_docx(
    project: Project,
    latest_run: MacsRun | None = None,
) -> bytes:
    doc = Document()

    # Standard 1-inch margins
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

    settings = project.settings or {}
    macs_batch = settings.get("macsBatch") or {}
    time_eq_inputs = settings.get("timeEqInputs") or {}
    time_eq_result = settings.get("timeEqResult") or {}

    # Document Header / Title
    title_p = doc.add_paragraph()
    title_run = title_p.add_run("Structural Fire Engineering Assessment")
    title_run.bold = True
    title_run.font.size = Pt(22)
    title_run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x8A)

    sub_p = doc.add_paragraph()
    sub_run = sub_p.add_run(f"Project: {project.name or 'Untitled Project'}")
    sub_run.bold = True
    sub_run.font.size = Pt(13)

    date_str = project.updated_at.strftime("%Y-%m-%d %H:%M") if getattr(project, "updated_at", None) else "N/A"
    date_p = doc.add_paragraph(f"Generated: {date_str}")
    date_p.paragraph_format.space_after = Pt(16)

    # ═════════════════════════════════════════════════════════════════════════
    # SECTION 1: MACS+ Composite Slab Assessment
    # ═════════════════════════════════════════════════════════════════════════
    h1 = doc.add_heading("1. MACS+ Composite Floor Assessment", level=1)
    h1.paragraph_format.space_before = Pt(14)
    h1.paragraph_format.space_after = Pt(8)

    if macs_batch:
        b_name = macs_batch.get("name") or "MACS Batch"
        b_id = macs_batch.get("batch_id") or "N/A"
        run_count = macs_batch.get("run_count", 0)
        pass_count = macs_batch.get("pass_count", 0)
        fail_count = macs_batch.get("fail_count", 0)
        error_count = macs_batch.get("error_count", 0)
        reliability_pct = macs_batch.get("reliability_percent", 0.0)

        intro = doc.add_paragraph()
        intro.add_run(
            "MACS+ tensile membrane action analysis assesses the fire resistance of composite floor slabs with unprotected secondary beams. "
        )
        intro.add_run(f"Batch '{b_name}' ({b_id}) evaluated {run_count:,} fire scenarios.\n")

        # Summary Metrics Table
        t_summary = doc.add_table(rows=2, cols=5)
        t_summary.style = "Table Grid"
        t_summary.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["Total Simulations", "Passed", "Failed", "Errors", "Batch Reliability"]
        for i, h in enumerate(headers):
            cell = t_summary.rows[0].cells[i]
            cell.text = h
            cell.paragraphs[0].runs[0].bold = True
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        vals = [f"{run_count:,}", f"{pass_count:,}", f"{fail_count:,}", str(error_count), f"{reliability_pct:.2f}%"]
        for i, v in enumerate(vals):
            cell = t_summary.rows[1].cells[i]
            cell.text = v
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            if i == 4:
                cell.paragraphs[0].runs[0].bold = True

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Setup parameters
        setup = macs_batch.get("setup") or {}
        groups = setup.get("groups") or []
        if groups:
            h_setup = doc.add_heading("Batch Configuration & Input Parameters", level=2)
            h_setup.paragraph_format.space_before = Pt(10)

            total_param_rows = sum(len(g.get("fields", [])) for g in groups)
            t_setup = doc.add_table(rows=1 + total_param_rows + len(groups), cols=3)
            t_setup.style = "Table Grid"
            t_setup.alignment = WD_TABLE_ALIGNMENT.CENTER

            t_setup.rows[0].cells[0].text = "Group / Parameter"
            t_setup.rows[0].cells[0].paragraphs[0].runs[0].bold = True
            t_setup.rows[0].cells[1].text = "Value / Range"
            t_setup.rows[0].cells[1].paragraphs[0].runs[0].bold = True
            t_setup.rows[0].cells[2].text = "Unit"
            t_setup.rows[0].cells[2].paragraphs[0].runs[0].bold = True

            cur_row = 1
            for g in groups:
                cell_g = t_setup.rows[cur_row].cells[0]
                cell_g.text = g.get("title", "Parameters")
                cell_g.paragraphs[0].runs[0].bold = True
                t_setup.rows[cur_row].cells[1].text = ""
                t_setup.rows[cur_row].cells[2].text = ""
                cur_row += 1

                for f in g.get("fields", []):
                    lbl = f.get("label") or f.get("key") or ""
                    unit = f.get("unit") or ""
                    if f.get("varies"):
                        if "min" in f and "max" in f:
                            val_str = f"{f['min']} – {f['max']} (varies)"
                        elif f.get("values"):
                            val_str = f"{', '.join(str(v) for v in f['values'][:5])} (varies)"
                        else:
                            val_str = "Varies across batch"
                    else:
                        val_str = str(f.get("value") if f.get("value") is not None else "-")

                    t_setup.rows[cur_row].cells[0].text = f"  {lbl}"
                    t_setup.rows[cur_row].cells[1].text = val_str
                    t_setup.rows[cur_row].cells[2].text = unit
                    cur_row += 1

            doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Perimeter beam critical temperatures
        if latest_run:
            h_beam = doc.add_heading("Governing Perimeter Beam & Critical Temperatures", level=2)
            h_beam.paragraph_format.space_before = Pt(10)

            p_beam = doc.add_paragraph()
            p_beam.add_run(f"Governing Perimeter Side: Side {latest_run.governing_side}\n").bold = True
            p_beam.add_run(f"Governing Critical Temperature: {latest_run.critical_temp:.1f} °C\n")
            p_beam.add_run(
                f"Section: {latest_run.section}  |  Exposure: {latest_run.exposure}  |  Section Factor (Ap/V): {latest_run.section_factor:.1f} m⁻¹\n"
            )

            t_sides = doc.add_table(rows=5, cols=4)
            t_sides.style = "Table Grid"
            t_sides.alignment = WD_TABLE_ALIGNMENT.CENTER
            for i, h in enumerate(["Perimeter Side", "Section Size", "Load Ratio", "Critical Temp (°C)"]):
                c = t_sides.rows[0].cells[i]
                c.text = h
                c.paragraphs[0].runs[0].bold = True

            outputs = latest_run.outputs or {}
            inputs = latest_run.inputs or {}
            for row_idx, s in enumerate(["A", "B", "C", "D"], 1):
                s_lower = s.lower()
                sec = (
                    outputs.get(f"side_{s_lower}_sec")
                    or inputs.get(f"side_{s_lower}_sec")
                    or (latest_run.section if latest_run.governing_side == s else "-")
                )
                lr = outputs.get(f"side_{s_lower}_load_ratio")
                lr_str = f"{lr:.2f}" if lr is not None else "-"
                ct = outputs.get(f"side_{s_lower}_critical_temp")
                ct_str = f"{ct:.1f}" if ct is not None else "-"

                t_sides.rows[row_idx].cells[0].text = f"Side {s}{' (Governing)' if latest_run.governing_side == s else ''}"
                t_sides.rows[row_idx].cells[1].text = str(sec)
                t_sides.rows[row_idx].cells[2].text = lr_str
                t_sides.rows[row_idx].cells[3].text = ct_str
                if latest_run.governing_side == s:
                    t_sides.rows[row_idx].cells[0].paragraphs[0].runs[0].bold = True
                    t_sides.rows[row_idx].cells[3].paragraphs[0].runs[0].bold = True

            doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Degree of shear connection check
        shear_check = macs_batch.get("shear_check") or {}
        checked = shear_check.get("checked", 0)
        sub_limit = shear_check.get("sub_limit_runs") or []
        h_shear = doc.add_heading("EN 1994-1-1 Degree of Shear Connection Check", level=2)
        h_shear.paragraph_format.space_before = Pt(10)
        p_shear = doc.add_paragraph()
        if not sub_limit:
            p_shear.add_run(
                f"All {checked:,} evaluated runs satisfy the EN 1994-1-1 minimum degree of shear connection. No beams are below the advisory threshold."
            ).bold = True
        else:
            p_shear.add_run(
                f"Notice: {len(sub_limit):,} of {checked:,} runs contain internal beams with degree of shear connection below the EN 1994-1-1 advisory limit."
            )
        p_shear.paragraph_format.space_after = Pt(8)

        # Matplotlib Charts from MACS
        charts = macs_batch.get("charts") or {}
        if any(charts.values()):
            h_mc_charts = doc.add_heading("MACS+ Assessment Figures", level=2)
            h_mc_charts.paragraph_format.space_before = Pt(10)

            _add_b64_image(doc, charts.get("scatter"), "Figure 1: Fire Load Density vs Glazing Breakage (Unity Factor Pass/Fail)")
            _add_b64_image(doc, charts.get("totalCapacity"), "Figure 2: Total Slab Plate Capacity vs Time")
            _add_b64_image(doc, charts.get("beamTemp"), "Figure 3: Unprotected Secondary Beam Temperature vs Time")
            _add_b64_image(doc, charts.get("meshTemp"), "Figure 4: Slab Reinforcement Mesh Temperature vs Time")

    else:
        doc.add_paragraph("No MACS+ batch assessment data has been uploaded or linked to this project.")

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # SECTION 2: Monte Carlo Time Equivalence & Structural Fire Reliability
    # ═════════════════════════════════════════════════════════════════════════
    h2 = doc.add_heading("2. Monte Carlo Time Equivalence & Reliability Analysis", level=1)
    h2.paragraph_format.space_before = Pt(14)
    h2.paragraph_format.space_after = Pt(8)

    if time_eq_result or time_eq_inputs:
        intro2 = doc.add_paragraph()
        intro2.add_run(
            "Parametric fire time equivalence determines the equivalent standard ISO 834 fire exposure duration for the compartment. "
        )
        intro2.add_run(
            "The Monte Carlo reliability study assesses the probability of member temperature exceeding the MACS+ governing critical temperature under realistic fire loading.\n"
        )

        h_geo = doc.add_heading("Compartment & Structural Properties", level=2)
        h_geo.paragraph_format.space_before = Pt(10)

        t_teq = doc.add_table(rows=7, cols=2)
        t_teq.style = "Table Grid"
        t_teq.alignment = WD_TABLE_ALIGNMENT.CENTER

        occ = time_eq_inputs.get("mcOccupancy") or time_eq_inputs.get("use") or "Office"
        fr = time_eq_inputs.get("fireResistancePeriod", 60)
        h_comp = time_eq_inputs.get("compartmentHeight", 3.0)
        sprink = "Yes" if time_eq_inputs.get("isSprinklered") else "No"
        crit_t = time_eq_inputs.get("criticalTemp", 550)
        sec_fac = time_eq_inputs.get("sectionFactor", 140)
        b_val = time_eq_inputs.get("customBValue") or "Calculated from boundaries"

        teq_rows = [
            ("Occupancy Classification", str(occ)),
            ("Required Fire Resistance Period", f"{fr} minutes"),
            ("Compartment Ceiling Height", f"{h_comp} m"),
            ("Automatic Sprinkler Protection", sprink),
            ("Thermal Inertia (b-value)", f"{b_val} J/(m²·s^0.5·K)"),
            ("Steel Failure Temperature Limit", f"{crit_t} °C"),
            ("Steel Member Section Factor (Ap/V)", f"{sec_fac} m⁻¹"),
        ]
        for idx, (param, val) in enumerate(teq_rows):
            t_teq.rows[idx].cells[0].text = param
            t_teq.rows[idx].cells[0].paragraphs[0].runs[0].bold = True
            t_teq.rows[idx].cells[1].text = str(val)

        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Reliability Results
        h_rel = doc.add_heading("Reliability Outcome & Failure Probability", level=2)
        h_rel.paragraph_format.space_before = Pt(10)

        pf = time_eq_result.get("failure_prob")
        if pf is None and time_eq_result.get("nSim") and time_eq_result.get("nFailed") is not None:
            pf = time_eq_result["nFailed"] / time_eq_result["nSim"]

        rel_pct = time_eq_result.get("reliabilityPercent")
        if rel_pct is None and pf is not None:
            rel_pct = (1.0 - pf) * 100.0

        n_sim = time_eq_result.get("nSim") or 1000
        n_failed = time_eq_result.get("nFailed") or 0
        seed = time_eq_result.get("seed", 42)

        t_res = doc.add_table(rows=2, cols=4)
        t_res.style = "Table Grid"
        t_res.alignment = WD_TABLE_ALIGNMENT.CENTER
        res_headers = ["Sample Size (N)", "Simulations Exceeding Limit", "Failure Probability (Pf)", "Structural Reliability"]
        for i, h in enumerate(res_headers):
            c = t_res.rows[0].cells[i]
            c.text = h
            c.paragraphs[0].runs[0].bold = True
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

        pf_str = f"{pf * 100:.2f}% ({pf:.4f})" if pf is not None else "-"
        rel_str = f"{rel_pct:.2f}%" if rel_pct is not None else "-"
        res_vals = [f"{n_sim:,}", f"{n_failed:,}", pf_str, rel_str]
        for i, v in enumerate(res_vals):
            c = t_res.rows[1].cells[i]
            c.text = v
            c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            if i == 3:
                c.paragraphs[0].runs[0].bold = True

        doc.add_paragraph(
            f"Monte Carlo sampling seed: {seed}. Evaluation criterion: Member temperature remaining below {crit_t} °C under realistic natural fire trajectories."
        )
        doc.add_paragraph().paragraph_format.space_after = Pt(8)

        # Time Eq Charts
        teq_charts = time_eq_result.get("charts") or {}
        if any(teq_charts.values()):
            h_teq_charts = doc.add_heading("Time Equivalence Figures", level=2)
            h_teq_charts.paragraph_format.space_before = Pt(10)

            _add_b64_image(doc, teq_charts.get("steelTempSpaghetti"), "Figure 5: Steel Temperature vs Time (Monte Carlo Spaghetti vs ISO Standard Fire)")
            _add_b64_image(doc, teq_charts.get("passFailScatter"), "Figure 6: Equivalent Exposure Time vs Maximum Steel Temperature (Pass/Fail)")
    else:
        doc.add_paragraph("No Monte Carlo Time Equivalence results have been generated for this project.")

    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
