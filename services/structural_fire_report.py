"""DOCX report generator for combined MACS+ & Time Equivalence structural fire report.

Uses the Fire Dynamics collated Structural Fire Resistance template
(``templates/structural_fire_report_template.docx``) as the document skin and
slots in project-specific metadata, MACS+ batch/run results & charts, and
Monte Carlo Time Equivalence results & charts.
"""

from __future__ import annotations

import base64
import copy
import datetime as dt
import io
import zipfile
from pathlib import Path
from typing import Any

from docx import Document
from lxml import etree
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.shared import Inches, Pt
from docx.text.paragraph import Paragraph

from models.db_models import MacsRun, Project

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "templates" / "structural_fire_report_template.docx"
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _decode_b64_image(b64_str: str | None) -> bytes | None:
    if not b64_str or not isinstance(b64_str, str):
        return None
    if "base64," in b64_str:
        b64_str = b64_str.split("base64,", 1)[1]
    try:
        raw = base64.b64decode(b64_str)
        return raw if len(raw) >= 8 else None
    except Exception:
        return None


def _remove_element(el: Any) -> None:
    """Remove an XML element (paragraph or table) from its parent."""
    xml_el = getattr(el, "_element", el)
    parent = xml_el.getparent()
    if parent is not None:
        parent.remove(xml_el)


def _insert_paragraph_after(
    anchor: Any,
    text: str = "",
    style: str | None = None,
    bold: bool = False,
    space_after: Pt | None = None,
    align: WD_ALIGN_PARAGRAPH | None = None,
) -> Paragraph:
    """Insert a new paragraph immediately after ``anchor`` (Paragraph or Table)."""
    anchor_el = getattr(anchor, "_element", anchor)
    new_p_el = OxmlElement("w:p")
    anchor_el.addnext(new_p_el)
    p = Paragraph(new_p_el, anchor._parent if hasattr(anchor, "_parent") else None)
    if style:
        try:
            p.style = style
        except KeyError:
            pass
    if text:
        run = p.add_run(text)
        run.bold = bold
    if space_after is not None:
        p.paragraph_format.space_after = space_after
    if align is not None:
        p.alignment = align
    return p


def _insert_table_after(
    doc: Document,
    anchor: Any,
    rows: int,
    cols: int,
    style: str = "Table Grid",
):
    """Create a table using python-docx and move it immediately after ``anchor``."""
    tbl = doc.add_table(rows=rows, cols=cols)
    try:
        tbl.style = style
    except KeyError:
        pass
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    anchor_el = getattr(anchor, "_element", anchor)
    anchor_el.addnext(tbl._element)
    return tbl


def _insert_b64_image_after(
    anchor: Any,
    b64_str: str | None,
    caption: str,
    width: Inches = Inches(5.8),
) -> Any:
    """Insert a centered image and caption after ``anchor``. Returns last inserted element."""
    raw = _decode_b64_image(b64_str)
    if not raw:
        return anchor

    img_p = _insert_paragraph_after(anchor, align=WD_ALIGN_PARAGRAPH.CENTER)
    img_run = img_p.add_run()
    img_run.add_picture(io.BytesIO(raw), width=width)

    cap_p = _insert_paragraph_after(
        img_p,
        text=caption,
        style="Caption",
        align=WD_ALIGN_PARAGRAPH.CENTER,
        space_after=Pt(8),
    )
    if not cap_p.runs:
        cap_p.add_run(caption)
    return cap_p


def _direct_p_text_elements(p_el: Any) -> list[Any]:
    """Return <w:t> elements belonging directly to ``p_el`` (not nested textboxes)."""
    t_els: list[Any] = []
    for child in p_el:
        tag = child.tag
        if tag == f"{{{W_NS}}}r":
            # Skip runs that contain drawings/picts (which hold nested textboxes)
            if child.find(f".//{{{W_NS}}}txbxContent") is not None:
                continue
            t_els.extend(child.findall(f"./{{{W_NS}}}t"))
        elif tag in (f"{{{W_NS}}}hyperlink", f"{{{W_NS}}}smartTag"):
            t_els.extend(child.findall(f"./{{{W_NS}}}r/{{{W_NS}}}t"))
        elif tag == f"{{{W_NS}}}sdt":
            sdt_content = child.find(f"./{{{W_NS}}}sdtContent")
            if sdt_content is not None:
                t_els.extend(sdt_content.findall(f"./{{{W_NS}}}r/{{{W_NS}}}t"))
    return t_els


def _replace_text_in_xml_tree(root: Any, replacements: list[tuple[str, str]]) -> None:
    """Replace target strings across <w:p> elements while preserving run formatting."""
    for p_el in root.findall(f".//{{{W_NS}}}p"):
        t_els = _direct_p_text_elements(p_el)
        if not t_els:
            continue
        full = "".join(t.text or "" for t in t_els)
        updated = full
        for old, new in replacements:
            if old in updated:
                updated = updated.replace(old, new)
        if updated == full:
            continue
        # Try single-run replacement first to preserve per-run styling
        replaced_in_single = False
        for t in t_els:
            if t.text:
                t_new = t.text
                for old, new in replacements:
                    t_new = t_new.replace(old, new)
                if t_new != t.text:
                    t.text = t_new
                    replaced_in_single = True
        if not replaced_in_single:
            t_els[0].text = updated
            for t in t_els[1:]:
                t.text = ""


def _set_paragraph_text(p: Paragraph, text: str) -> None:
    """Replace a paragraph's text while keeping its paragraph style."""
    if p.runs:
        p.runs[0].text = text
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.add_run(text)


def _find_paragraph(doc: Document, prefix: str) -> Paragraph | None:
    for p in doc.paragraphs:
        if p.text.strip().startswith(prefix):
            return p
    return None


def _paragraph_index(doc: Document, target: Paragraph) -> int:
    target_el = target._element
    for idx, p in enumerate(doc.paragraphs):
        if p._element is target_el:
            return idx
    raise ValueError("Paragraph not found in document")


def _set_cell_lines(cell: Any, lines: list[str], default_pt: float = 8.0) -> None:
    """Replace all content in a table cell while preserving the template's run font/size."""
    tc = cell._tc
    p_els = tc.findall(f"./{{{W_NS}}}p")
    # Capture first non-bold or template rPr before clearing
    template_rpr = None
    for p_el in p_els:
        for r_el in p_el.findall(f".//{{{W_NS}}}r"):
            rpr = r_el.find(f"./{{{W_NS}}}rPr")
            if rpr is not None:
                template_rpr = copy.deepcopy(rpr)
                break
        if template_rpr is not None:
            break

    for extra_p in p_els[1:]:
        tc.remove(extra_p)
    for tbl in tc.findall(f"./{{{W_NS}}}tbl"):
        tc.remove(tbl)
    p = cell.paragraphs[0]
    for child in list(p._element):
        if child.tag != f"{{{W_NS}}}pPr":
            p._element.remove(child)
    for idx, line in enumerate(lines):
        if idx > 0:
            p.add_run("\n")
        run = p.add_run(line)
        if template_rpr is not None:
            old_rpr = run._element.find(f"./{{{W_NS}}}rPr")
            if old_rpr is not None:
                run._element.remove(old_rpr)
            run._element.insert(0, copy.deepcopy(template_rpr))
        else:
            run.font.size = Pt(default_pt)


def _setup_lookup(macs_batch: dict[str, Any]) -> dict[str, str]:
    """Flatten macsBatch.setup.groups into a lowercase label/key -> formatted value map."""
    out: dict[str, str] = {}
    for g in (macs_batch.get("setup") or {}).get("groups") or []:
        g_title = str(g.get("title") or "").strip().lower()
        for f in g.get("fields") or []:
            key = str(f.get("key") or "").strip().lower()
            lbl = str(f.get("label") or "").strip().lower()
            unit = str(f.get("unit") or "").strip()
            if f.get("varies"):
                if "min" in f and "max" in f:
                    val = f"{f['min']} – {f['max']}"
                elif f.get("values"):
                    val = ", ".join(str(v) for v in f["values"][:5])
                else:
                    val = "Varies across batch"
            else:
                raw_v = f.get("value")
                val = str(raw_v) if raw_v is not None and str(raw_v) != "" else ""
            if val and unit:
                val = f"{val} {unit}"
            if val:
                if key:
                    out[key] = val
                if lbl:
                    out[lbl] = val
                    if g_title:
                        out[f"{g_title}:{lbl}"] = val
    return out


def _pick(lookup: dict[str, str], *keys: str, default: str = "[Placeholder]") -> str:
    for k in keys:
        v = lookup.get(k.lower())
        if v:
            return v
    return default


def _render_single_run_charts(
    time_series: list[dict[str, Any]],
    factored_hot: float | None = None,
) -> list[bytes]:
    """Render the 2 Sheet 4 single-run MACS+ charts from a run's time_series."""
    if not time_series:
        return []
    try:
        from services.teq_reliability_charts import MPL_LOCK, HOUSE_CHART_CONFIG, HOUSE_DPI
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return []

    t_vals = [float(r["time_min"]) for r in time_series if isinstance(r.get("time_min"), (int, float))]
    if len(t_vals) < 2:
        return []

    def _series(key: str) -> list[float] | None:
        vals = [r.get(key) for r in time_series]
        if len(vals) == len(t_vals) and all(isinstance(v, (int, float)) for v in vals):
            return [float(v) for v in vals]
        return None

    out_pngs: list[bytes] = []
    with MPL_LOCK:
        with plt.rc_context(HOUSE_CHART_CONFIG):
            # 1. Temperature vs Time
            fig, ax = plt.subplots(figsize=(5.6, 3.3))
            for key, lbl, color in (
                ("slabtop_temp", "Slab top", "#4798EA"),
                ("slabbot_temp", "Slab bottom", "#1E3A8A"),
                ("lofl_temp", "Unprotected beam", "#EC4899"),
                ("mesh_temp", "Mesh", "#22C55E"),
                ("fire_temp", "Fire", "#F59E0B"),
            ):
                y = _series(key)
                if y is not None:
                    ax.plot(t_vals, y, label=lbl, color=color, linewidth=1.3)
            ax.set_xlabel("Time (min)")
            ax.set_ylabel("Temperature (°C)")
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
            ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3, frameon=False, fontsize=7.5)
            buf1 = io.BytesIO()
            fig.savefig(buf1, format="png", dpi=HOUSE_DPI, bbox_inches="tight")
            plt.close(fig)
            out_pngs.append(buf1.getvalue())

            # 2. Bending Capacity & Maximum Allowable Deflection vs Time
            slab_cap = _series("slab_cap")
            beam_cap = _series("beam_hot_capacity")
            total_cap = _series("total_plate_capacity")
            defl = _series("deflection")
            if any(x is not None for x in (slab_cap, beam_cap, total_cap)):
                fig2, ax1 = plt.subplots(figsize=(5.6, 3.3))
                if slab_cap is not None:
                    ax1.plot(t_vals, slab_cap, label="Slab capacity", color="#1E3A8A", linewidth=1.3)
                if beam_cap is not None:
                    ax1.plot(t_vals, beam_cap, label="Unprotected beam capacity", color="#22C55E", linewidth=1.3)
                if total_cap is not None:
                    ax1.plot(t_vals, total_cap, label="Total capacity", color="#4798EA", linewidth=1.3)
                if isinstance(factored_hot, (int, float)):
                    ax1.axhline(float(factored_hot), linestyle="--", color="#475569", linewidth=1.0, label="Factored load")
                ax1.set_xlabel("Time (min)")
                ax1.set_ylabel("Bending capacity (kN/m²)")
                ax1.set_xlim(left=0)
                ax1.set_ylim(bottom=0)

                if defl is not None:
                    ax2 = ax1.twinx()
                    ax2.plot(t_vals, defl, label="Maximum allowable deflection", color="#EC4899", linewidth=1.3)
                    ax2.set_ylabel("Maximum allowable deflection (mm)")
                    h1, l1 = ax1.get_legend_handles_labels()
                    h2, l2 = ax2.get_legend_handles_labels()
                    ax1.legend(h1 + h2, l1 + l2, loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, fontsize=7.5)
                else:
                    ax1.legend(loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=2, frameon=False, fontsize=7.5)

                buf2 = io.BytesIO()
                fig2.savefig(buf2, format="png", dpi=HOUSE_DPI, bbox_inches="tight")
                plt.close(fig2)
                out_pngs.append(buf2.getvalue())

    return out_pngs


def _sample_time_series(rows: list[dict[str, Any]], max_rows: int = 13) -> list[dict[str, Any]]:
    """Sample a MACS+ time_series list to ~13 evenly spaced rows (including first & last)."""
    if len(rows) <= max_rows:
        return rows
    step = (len(rows) - 1) / (max_rows - 1)
    indices = sorted({round(i * step) for i in range(max_rows)})
    return [rows[i] for i in indices]


def _populate_tabular_results_cell(cell: Any, time_series: list[dict[str, Any]], max_unity: float | None) -> None:
    """Populate Sheet 3 Row 7 using the template's existing 12-column nested table styling."""
    tc = cell._tc
    existing_tbl_el = tc.find(f"./{{{W_NS}}}tbl")

    if not time_series:
        _set_cell_lines(cell, ["• Tabular results: [Placeholder — Insert MACS+ Tabular results output]"])
        return

    status = "Floor slab adequate" if (max_unity is not None and max_unity <= 1.0) else "Check unity factor"
    uf_lbl = f"{max_unity:.2f} ({status})" if max_unity is not None else "—"

    # Update the intro paragraphs above the nested table without deleting existing_tbl_el
    p_els = tc.findall(f"./{{{W_NS}}}p")
    for idx, p_el in enumerate(p_els):
        for child in list(p_el):
            if child.tag != f"{{{W_NS}}}pPr":
                p_el.remove(child)
        from docx.text.paragraph import Paragraph as _P
        p_obj = _P(p_el, cell)
        if idx == 0:
            r = p_obj.add_run("• Tabular results")
            r.font.size = Pt(8)
        elif idx == 1:
            r = p_obj.add_run(f"    Maximum unity factor: {uf_lbl}")
            r.font.size = Pt(8)

    col_keys = [
        ("time_min", ".0f"),
        ("lofl_temp", ".0f"),
        ("mesh_temp", ".0f"),
        ("slabtop_temp", ".0f"),
        ("slabbot_temp", ".0f"),
        ("beam_hot_capacity", ".2f"),
        ("deflection", ".0f"),
        ("slab_yield", ".2f"),
        ("enhancement", ".2f"),
        ("slab_cap", ".2f"),
        ("total_plate_capacity", ".2f"),
        ("utilization_factor", ".2f"),
    ]
    sampled = _sample_time_series(time_series)

    if existing_tbl_el is not None:
        from docx.table import Table as _T, _Cell
        tbl = _T(existing_tbl_el, cell)
        if len(tbl.rows) >= 3:
            # Template A.2 nested table has 11 columns (missing Unity factor); append the 12th column to match A.1
            tbl_grid = existing_tbl_el.find(f"./{{{W_NS}}}tblGrid")
            if tbl_grid is not None:
                grid_cols = tbl_grid.findall(f"./{{{W_NS}}}gridCol")
                if len(grid_cols) == len(col_keys) - 1 and grid_cols:
                    tbl_grid.append(copy.deepcopy(grid_cols[-1]))
            for r_idx, tr_el in enumerate(existing_tbl_el.findall(f"./{{{W_NS}}}tr")):
                row_tcs = tr_el.findall(f"./{{{W_NS}}}tc")
                if len(row_tcs) == len(col_keys) - 1 and row_tcs:
                    new_tc = copy.deepcopy(row_tcs[-1])
                    tr_el.append(new_tc)
                    if r_idx == 0:
                        _set_cell_lines(_Cell(new_tc, tbl), ["Unity factor"], default_pt=7.5)
                    elif r_idx == 1:
                        _set_cell_lines(_Cell(new_tc, tbl), ["-"], default_pt=7.5)

            proto_tr = copy.deepcopy(tbl.rows[2]._tr)
            # Remove all old template data rows (keep header rows 0 and 1)
            for tr in list(existing_tbl_el.findall(f"./{{{W_NS}}}tr"))[2:]:
                existing_tbl_el.remove(tr)
            for row_data in sampled:
                new_tr = copy.deepcopy(proto_tr)
                existing_tbl_el.append(new_tr)
                tcs = new_tr.findall(f"./{{{W_NS}}}tc")
                for ci, (key, fmt) in enumerate(col_keys):
                    if ci >= len(tcs):
                        break
                    val = row_data.get(key)
                    txt = format(float(val), fmt) if isinstance(val, (int, float)) else "-"
                    from docx.table import _Cell
                    _set_cell_lines(_Cell(tcs[ci], tbl), [txt], default_pt=7.5)
                    # Highlight peak Unity factor cell in soft green (or soft red if > 1.0)
                    if (
                        key == "utilization_factor"
                        and max_unity is not None
                        and isinstance(val, (int, float))
                        and abs(float(val) - max_unity) < 1e-6
                    ):
                        tc_pr = tcs[ci].find(f"./{{{W_NS}}}tcPr")
                        if tc_pr is None:
                            tc_pr = OxmlElement("w:tcPr")
                            tcs[ci].insert(0, tc_pr)
                        for old_shd in tc_pr.findall(f"./{{{W_NS}}}shd"):
                            tc_pr.remove(old_shd)
                        shd = OxmlElement("w:shd")
                        shd.set(f"{{{W_NS}}}val", "clear")
                        shd.set(f"{{{W_NS}}}color", "auto")
                        shd.set(f"{{{W_NS}}}fill", "C6E0B4" if max_unity <= 1.0 else "F8CBAD")
                        tc_pr.append(shd)
            return

    # Fallback if template nested table was absent
    _set_cell_lines(cell, ["• Tabular results", f"    Maximum unity factor: {uf_lbl}"])


def _populate_macs_sheet_pair(
    t_sheet12: Any | None,
    t_sheet34: Any | None,
    section_code: str,
    b_name: str,
    b_id: str,
    macs_batch: dict[str, Any],
    latest_run: MacsRun | None,
    lookup: dict[str, str],
    sample_run: dict[str, Any] | None = None,
) -> None:
    """Populate a Sheet 1–4 MACS+ calculation table pair while preserving template styling."""
    run_count = macs_batch.get("run_count", 0)
    pass_count = macs_batch.get("pass_count", 0)
    fail_count = macs_batch.get("fail_count", 0)
    error_count = macs_batch.get("error_count", 0)
    reliability_pct = macs_batch.get("reliability_percent", 0.0)
    sr_outputs = (sample_run or {}).get("outputs") or {}
    outputs = {**((latest_run.outputs if latest_run else None) or {}), **sr_outputs}
    inputs = (latest_run.inputs if latest_run else None) or {}
    sim_label = ""
    if sample_run and sample_run.get("run_number") is not None:
        total = sample_run.get("total_runs") or run_count
        sim_label = f" – Simulation {int(sample_run['run_number']):,} of {int(total):,}"

    if t_sheet12 is not None and len(t_sheet12.rows) >= 10:
        _set_cell_lines(t_sheet12.rows[0].cells[0], [f"{section_code} MACS+ Example Calculations – {b_name}{sim_label} (Sheet 1)"])
        _set_cell_lines(t_sheet12.rows[7].cells[0], [f"{section_code} MACS+ Example Calculations – {b_name}{sim_label} (Sheet 2)"])

        _set_cell_lines(
            t_sheet12.rows[2].cells[0],
            [
                "• Spans:",
                f"    Span 1: {_pick(lookup, 'span 1', 'span1')}",
                f"    Span 2: {_pick(lookup, 'span 2', 'span2')}",
                "• Unprotected beams:",
                f"    Number of internal unprotected beams: {_pick(lookup, 'number of beams', 'numbeam', 'num_beams', 'number of internal unprotected beams')}",
            ],
        )
        _set_cell_lines(t_sheet12.rows[2].cells[1], ["[Placeholder — Insert General Arrangement diagram from MACS+]"])

        _set_cell_lines(
            t_sheet12.rows[4].cells[0],
            [
                "• Deck properties:",
                f"    Deck: {_pick(lookup, 'deck profile', 'deck_name', 'deck', 'deck name')}",
                f"    Type: {_pick(lookup, 'deck type', 'deck_type')}",
                f"    Depth: {_pick(lookup, 'deck depth', 'deck_depth')}",
                f"    Top flange: {_pick(lookup, 'top width', 'deck_top', 'top flange', 'top_width')}",
                f"    Pitch: {_pick(lookup, 'trough pitch', 'deck_trug', 'pitch')}",
                f"    Bottom flange: {_pick(lookup, 'bottom width', 'deck_bot', 'bottom flange', 'bottom_width')}",
                f"    Stiffener height: {_pick(lookup, 'stiffener height', 'deck_stiff_height', 'stiffener_height')}",
            ],
        )
        _set_cell_lines(t_sheet12.rows[4].cells[1], ["[Placeholder — Insert Deck profile diagram from MACS+]"])

        _set_cell_lines(
            t_sheet12.rows[6].cells[0],
            [
                "• Concrete",
                f"    Concrete type: {_pick(lookup, 'concrete type', 'conc_type', 'concrete_type')}",
                f"    Slab depth: {_pick(lookup, 'slab depth', 'slab_depth')}",
                f"    Cylinder compressive strength (fck): {_pick(lookup, 'fck', 'concrete fck')}",
                "• Mesh",
                f"    Mesh type: {_pick(lookup, 'mesh', 'mesh_type', 'mesh type')}",
                f"    Longitudinal mesh area: {_pick(lookup, 'mesh area (main)', 'mesh_area_max', 'mesh area long', 'mesh_area_long')}",
                f"    Transverse mesh area: {_pick(lookup, 'mesh area (transverse)', 'mesh_area_min', 'mesh area trans', 'mesh_area_trans')}",
                f"    Mesh axis distance: {_pick(lookup, 'mesh axis distance', 'mesh_axis', 'mesh axis')}",
                f"    Steel strength: {_pick(lookup, 'mesh strength', 'mesh_strength', 'mesh_fy')}",
            ],
        )
        _set_cell_lines(t_sheet12.rows[6].cells[1], ["[Placeholder — Insert Mesh orientation & Slab section diagrams from MACS+]"])

        beam_lines = [
            "• Unprotected beams",
            f"    Section size: {_pick(lookup, 'unprotected section', 'u_sec_size', default=str(inputs.get('u_sec_size') or '[Placeholder]'))}",
            f"    Steel grade: {_pick(lookup, 'unprotected fy', 'u_sec_fy', 'u_fy')}",
        ]
        for s in ("A", "B", "C", "D"):
            sl = s.lower()
            sec = outputs.get(f"side_{sl}_sec") or inputs.get(f"side_{sl}_sec") or _pick(lookup, f"side {sl} section", f"side_{sl}_sec")
            edge_val = _pick(lookup, f"side {sl} edge beam", f"side_{sl}_edge", default="")
            comp_val = _pick(lookup, f"side {sl} composite", f"side_{sl}_composite", default="")
            loc_str = "Edge beam" if str(edge_val).strip() in ("1", "True", "true", "Edge") else ("Internal" if str(edge_val).strip() in ("0", "False", "false", "Internal") else "[Placeholder]")
            comp_str = "Composite" if str(comp_val).strip() in ("1", "True", "true", "Composite") else ("Non-composite" if str(comp_val).strip() in ("0", "False", "false", "Non-composite") else "[Placeholder]")
            beam_lines.extend([
                f"• Side {s} perimeter beam",
                f"    Section size: {sec}",
                f"    Steel grade: {_pick(lookup, f'side {sl} fy', f'side_{sl}_fy')}",
                f"    Beam location: {loc_str}  |  Construction type: {comp_str}",
            ])
        _set_cell_lines(t_sheet12.rows[9].cells[0], beam_lines)
        _set_cell_lines(t_sheet12.rows[9].cells[1], ["[Placeholder — Insert Perimeter beam layout diagram from MACS+]"])

    if t_sheet34 is not None and len(t_sheet34.rows) >= 13:
        _set_cell_lines(t_sheet34.rows[0].cells[0], [f"{section_code} MACS+ Example Calculations – {b_name}{sim_label} (Sheet 3)"])
        _set_cell_lines(t_sheet34.rows[8].cells[0], [f"{section_code} MACS+ Example Calculations – {b_name}{sim_label} (Sheet 4)"])

        _set_cell_lines(
            t_sheet34.rows[2].cells[0],
            [
                "• Normal (Cold)",
                f"    Leading variable action: {_pick(lookup, 'leading variable action', 'lead_var_act', 'leading variable', 'leading_var')}",
                f"    Accompanying variable action: {_pick(lookup, 'other variable action', 'othr_var_act', 'other variable', 'other_var')}",
                f"    Superimposed dead load: {_pick(lookup, 'superimposed dead load', 'cold_perm', 'superimposed dead', 'super_dead')}",
                f"    Slab self-weight: {_pick(lookup, 'slab self-weight', 'slab_weight')}",
                "• Fire (Hot)",
                f"    Combination factor (leading variable): {_pick(lookup, 'leading variable factor', 'lead_var_fac', 'leading variable psi', 'psi_1')}",
                f"    Combination factor (other variable): {_pick(lookup, 'other variable factor', 'othr_var_fac', 'other variable psi', 'psi_2')}",
            ],
        )
        _set_cell_lines(t_sheet34.rows[2].cells[1], ["[Placeholder — Insert Loading diagram from MACS+]"])

        sr_qf = (sample_run or {}).get("qf")
        sr_glazing = (sample_run or {}).get("window_percent")
        qf_str = f"{sr_qf:.1f} MJ/m²" if isinstance(sr_qf, (int, float)) else _pick(lookup, 'fire load density qf', 'qf', 'fire load', 'fireload')
        glaz_str = f"{sr_glazing:.1f} %" if isinstance(sr_glazing, (int, float)) else _pick(lookup, 'window opening', 'window_percent', 'glazing breakage', 'glazing')

        _set_cell_lines(
            t_sheet34.rows[4].cells[0],
            [
                f"• Analysis type: {_pick(lookup, 'analysis method', 'method', 'analysis', 'analysis_type')}",
                f"    Time limit: {_pick(lookup, 'time limit', 'time_limit')}",
                f"    Compartment dimensions: {_pick(lookup, 'compartment length lc', 'lc', 'compartment length', 'comp_length')} × {_pick(lookup, 'compartment breadth bc', 'bc', 'compartment width', 'comp_width')} × {_pick(lookup, 'compartment height hc', 'hc', 'compartment height', 'comp_height')}",
                f"    Fire load density: {qf_str}",
                f"    Glazing breakage: {glaz_str}",
            ],
        )
        if len(t_sheet34.rows[4].cells) > 1:
            _set_cell_lines(
                t_sheet34.rows[4].cells[1],
                [
                    f"Window height: {_pick(lookup, 'window height hw', 'hw', 'window height', 'window_height')}",
                    f"Window length: {_pick(lookup, 'window length lw', 'lw', 'window length', 'window_length')}",
                    f"Wall lining (B) factor: {_pick(lookup, 'bfac', 'bf', 'b factor', 'wall lining')}",
                    f"Combustion factor: {_pick(lookup, 'combustion factor', 'combustion_factor', 'combustion')}",
                ],
            )

        time_series = (sample_run or {}).get("time_series") or getattr(latest_run, "time_series", None) or []
        max_unity = (sample_run or {}).get("uf_max") or outputs.get("max_unity_factor") or outputs.get("unity_factor")
        if max_unity is None and time_series:
            uf_vals = [r.get("utilization_factor") for r in time_series if isinstance(r.get("utilization_factor"), (int, float))]
            if uf_vals:
                max_unity = max(uf_vals)
        unity_str = f"{max_unity:.2f}" if isinstance(max_unity, (int, float)) else "[Placeholder — from MACS+]"
        factored_hot = outputs.get("factored_hot")
        fh_str = f"{factored_hot:.2f} kN/m²" if isinstance(factored_hot, (int, float)) else "[Placeholder — from MACS+]"
        fire_curve_val = _pick(lookup, 'analysis method', 'method', 'analysis', 'analysis_type', default='Parametric')
        fire_curve_str = (
            "Standard temperature-time curve"
            if "standard" in fire_curve_val.lower() or "iso" in fire_curve_val.lower()
            else "Parametric temperature-time curve"
        )
        _set_cell_lines(
            t_sheet34.rows[6].cells[0],
            [
                "• Default mesh direction",
                f"    Maximum unity factor: {unity_str}",
                f"    Factored load in fire: {fh_str}",
                f"    Fire curve: {fire_curve_str}",
            ],
        )
        _populate_tabular_results_cell(t_sheet34.rows[7].cells[0], time_series, max_unity)

        def _side_lines(side: str) -> list[str]:
            sl = side.lower()
            sec = outputs.get(f"side_{sl}_sec") or inputs.get(f"side_{sl}_sec") or (latest_run.section if latest_run and latest_run.governing_side == side else "-")
            lr = outputs.get(f"side_{sl}_load_ratio")
            lr_str = f"{lr:.2f}" if isinstance(lr, (int, float)) else "[Placeholder]"
            ct = outputs.get(f"side_{sl}_critical_temp")
            ct_str = f"{ct:.1f}°C" if isinstance(ct, (int, float)) else "[Placeholder]"
            mr = outputs.get(f"side_{sl}_moment_resistance")
            if mr is None:
                mr = outputs.get("mb1_reqd") if side in ("A", "C") else outputs.get("mb2_reqd")
            mr_str = f"{mr:.2f} kNm" if isinstance(mr, (int, float)) else "[Placeholder]"
            ll = outputs.get(f"side_{sl}_line_load")
            ll_str = f"{ll:.2f} kN/m" if isinstance(ll, (int, float)) else "[Placeholder]"
            gov = " (Governing)" if latest_run and latest_run.governing_side == side else ""
            return [
                f"Side {side}{gov}",
                f"    Beam type: {_pick(lookup, f'side {sl} beam type', default='Solid beam')}",
                f"    Section size: {sec}",
                f"    Required moment resistance in fire situation: {mr_str}",
                f"    Line load in fire situation: {ll_str}",
                f"    Degree of utilization: {lr_str}",
                f"    Critical temperature: {ct_str}",
            ]

        _set_cell_lines(t_sheet34.rows[10].cells[0], _side_lines("A") + _side_lines("B"))
        _set_cell_lines(t_sheet34.rows[10].cells[1], _side_lines("C") + _side_lines("D"))

        single_charts = _render_single_run_charts(time_series, factored_hot if isinstance(factored_hot, (int, float)) else None)
        if single_charts:
            _set_cell_lines(t_sheet34.rows[12].cells[0], [])
            cell_graph = t_sheet34.rows[12].cells[0]
            for png_bytes in single_charts:
                p_img = cell_graph.add_paragraph()
                p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_img.add_run().add_picture(io.BytesIO(png_bytes), width=Inches(5.0))
        else:
            _set_cell_lines(
                t_sheet34.rows[12].cells[0],
                ["[Placeholder — Insert MACS+ single-run Graphical Output charts (Temperature vs Time & Bending Capacity vs Deflection)]"],
            )


def _populate_macs_appendix(
    doc: Document,
    anchor: Any,
    macs_batch: dict[str, Any],
    latest_run: MacsRun | None,
    t_a1_12: Any | None = None,
    t_a1_34: Any | None = None,
    t_a2_12: Any | None = None,
    t_a2_34: Any | None = None,
) -> Any:
    """Populate Appendix A (A.1 and A.2) using the template's Sheet 1–4 MACS+ calculation tables."""
    cursor = anchor
    if not macs_batch:
        for tbl in (t_a1_12, t_a1_34, t_a2_12, t_a2_34):
            if tbl is not None:
                _remove_element(tbl)
        return _insert_paragraph_after(
            cursor,
            "No MACS+ batch assessment data has been uploaded or linked to this project.",
            style="Appendix Text",
        )

    b_name = macs_batch.get("name") or "MACS Batch"
    b_id = macs_batch.get("batch_id") or "N/A"
    lookup = _setup_lookup(macs_batch)

    sample_runs = macs_batch.get("sample_runs") or []
    sr1 = sample_runs[0] if len(sample_runs) >= 1 else None
    sr2 = sample_runs[1] if len(sample_runs) >= 2 else None
    _populate_macs_sheet_pair(t_a1_12, t_a1_34, "A.1.", b_name, b_id, macs_batch, latest_run, lookup, sample_run=sr1)
    _populate_macs_sheet_pair(t_a2_12, t_a2_34, "A.2.", b_name, b_id, macs_batch, latest_run, lookup, sample_run=sr2)

    # Sheet 5: Monte Carlo Simulation Output Summary (the 4 MACS+ batch charts)
    charts = macs_batch.get("charts") or {}
    sheet5_anchor = t_a2_34 or t_a1_34 or cursor
    if any(charts.values()):
        # Clone the blue-bordered header rows from t_a2_12 so Sheet 5 matches Sheets 1-4
        if t_a2_12 is not None and len(t_a2_12.rows) >= 2:
            from docx.table import Table as _Table
            cloned_tbl_el = copy.deepcopy(t_a2_12._element)
            for tr in list(cloned_tbl_el.findall(f"./{{{W_NS}}}tr"))[2:]:
                cloned_tbl_el.remove(tr)
            sheet5_anchor._element.addnext(cloned_tbl_el)
            t_s5 = _Table(cloned_tbl_el, doc)
            _set_cell_lines(t_s5.rows[0].cells[0], [f"A.2. MACS+ Example Calculations – {b_name} (Sheet 5)"])
            _set_cell_lines(t_s5.rows[1].cells[0], ["Monte Carlo Simulation Output Summary"])
            sheet5_anchor = t_s5
        else:
            sheet5_anchor = _insert_paragraph_after(
                sheet5_anchor,
                f"A.2. MACS+ Example Calculations – {b_name} (Sheet 5): Monte Carlo Simulation Output Summary",
                style="Normal",
                bold=True,
            )

        sheet5_items = [
            ("scatter", "• All combinations of Fire Load Density vs Glazing Breakage"),
            ("totalCapacity", "• Total Capacity Distribution"),
            ("beamTemp", "• Unprotected Beam Temperature Distribution"),
            ("meshTemp", "• Reinforcement Bar Temperature Distribution"),
        ]
        for key, heading in sheet5_items:
            raw = _decode_b64_image(charts.get(key))
            if raw:
                p_h = _insert_paragraph_after(sheet5_anchor, heading, style="Normal")
                p_img = _insert_paragraph_after(p_h, align=WD_ALIGN_PARAGRAPH.CENTER)
                p_img.add_run().add_picture(io.BytesIO(raw), width=Inches(5.4))
                sheet5_anchor = p_img

    shear_check = macs_batch.get("shear_check") or {}
    checked = shear_check.get("checked", 0)
    sub_limit = shear_check.get("sub_limit_runs") or []
    if checked:
        msg = (
            f"EN 1994-1-1 Degree of Shear Connection Check: All {checked:,} evaluated runs satisfy the minimum degree of shear connection."
            if not sub_limit
            else f"EN 1994-1-1 Degree of Shear Connection Check: {len(sub_limit):,} of {checked:,} runs contain internal beams below the advisory limit."
        )
        cursor = _insert_paragraph_after(sheet5_anchor, msg, style="Normal", space_after=Pt(6))

    return cursor


def _populate_teq_appendix(
    doc: Document,
    anchor: Any,
    time_eq_inputs: dict[str, Any],
    time_eq_result: dict[str, Any],
) -> Any:
    """Populate Appendix C matching the template: section heading + Time Eq scatter plot."""
    cursor = anchor
    if not (time_eq_result or time_eq_inputs):
        return _insert_paragraph_after(
            cursor,
            "No Monte Carlo Time Equivalence results have been generated for this project.",
            style="Appendix Text",
        )

    section_name = time_eq_inputs.get("section") or "Assessed Steel Section"
    crit_t = time_eq_inputs.get("criticalTemp", 550)
    cursor = _insert_paragraph_after(
        cursor,
        f"Results for Section Size of {section_name} with Critical Temperature of {crit_t}°C",
        style="Appendix Sub-Heading",
    )

    teq_charts = time_eq_result.get("charts") or {}
    scatter_raw = _decode_b64_image(teq_charts.get("passFailScatter"))
    if scatter_raw:
        img_p = _insert_paragraph_after(cursor, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=Pt(8))
        img_p.add_run().add_picture(io.BytesIO(scatter_raw), width=Inches(5.6))
        cursor = img_p
    else:
        cursor = _insert_paragraph_after(
            cursor,
            "[Placeholder — Insert Time Equivalence scatter plot]",
            style="Appendix Text",
        )
    return cursor


def build_structural_fire_report_docx(
    project: Project,
    latest_run: MacsRun | None = None,
) -> bytes:
    """Build a collated Structural Fire Resistance report from the Fire Dynamics template."""
    doc = Document(str(TEMPLATE_PATH))

    settings = project.settings or {}
    report_details = settings.get("reportDetails") or {}
    macs_batch = settings.get("macsBatch") or {}
    time_eq_inputs = settings.get("timeEqInputs") or {}
    time_eq_result = settings.get("timeEqResult") or {}

    project_name = (report_details.get("projectName") or "").strip() or project.name or "Untitled Project"
    client_name = (report_details.get("client") or "").strip() or "Client"
    location = (report_details.get("location") or "").strip()
    report_title = (report_details.get("reportTitle") or "").strip() or "Fire Resistance of the Office Floor Slab Structure"
    report_date = (report_details.get("date") or "").strip() or dt.date.today().strftime("%d-%m-%Y")
    author = (report_details.get("author") or "").strip() or "Fire Dynamics"
    author_first = author.split()[0].lower() if author != "Fire Dynamics" else "info"
    author_email = f"{author_first}@firedynamicsgroup.com"
    checked_by = (report_details.get("checkedBy") or "").strip() or "-"
    verified_by = (report_details.get("verifiedBy") or "").strip() or "-"
    target_rel = report_details.get("targetReliability")
    target_rel_str = f"{float(target_rel):.2f}%" if target_rel is not None else "98.20%"

    # 1. Global text replacements (cover, headers, SDTs, and Core/App properties)
    doc.core_properties.title = project_name
    doc.core_properties.subject = report_title
    doc.core_properties.author = author

    replacements = [
        ("Panattoni California Drive", project_name),
        ("Winvic Construction Ltd", client_name),
        ("Fire Resistance of the Office Floor Slab Structure", report_title),
        ("07-08-2026", report_date),
        ("diana@firedynamicsgroup.com", author_email),
    ]
    _replace_text_in_xml_tree(doc.element.body, replacements)
    for section in doc.sections:
        if section.header:
            _replace_text_in_xml_tree(section.header._element, replacements)

    # 2. Version history table (T[0]) — preserve template font & centered alignment
    if doc.tables:
        vh = doc.tables[0]
        if len(vh.rows) > 1:
            for col_idx, val in (
                (2, report_date),
                (3, author),
                (4, checked_by),
                (5, verified_by),
            ):
                cell = vh.rows[1].cells[col_idx]
                if cell.paragraphs:
                    _set_paragraph_text(cell.paragraphs[0], val)
                    cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                else:
                    cell.text = val

    # 3. Section 1.1 Summary & 1.2 Building Description & 1.3 Information Used
    p_sum = _find_paragraph(doc, "Fire Dynamics has been appointed by")
    if p_sum is not None:
        loc_clause = f" located in {location}" if location else ""
        _set_paragraph_text(
            p_sum,
            f"Fire Dynamics has been appointed by {client_name} to provide fire safety engineering advice for the proposed works on {project_name}{loc_clause}. "
            "The advice addresses the fire resistance of the secondary steel beams and composite deck floor structures.",
        )

    p_bldg = _find_paragraph(doc, "The main building is a single-storey")
    if p_bldg is not None:
        custom_bldg = (report_details.get("buildingDescription") or "").strip()
        if custom_bldg:
            _set_paragraph_text(p_bldg, custom_bldg)
        else:
            _set_paragraph_text(
                p_bldg,
                f"[Placeholder — Describe the main building and assessed floor areas for {project_name}{loc_clause}. Figure 1 shows the assessed locations.]",
            )
        p_idx = _paragraph_index(doc, p_bldg)
        site_plan_b64 = report_details.get("sitePlanImage")
        # Remove Panattoni Figure 1 image & caption; re-insert Figure 1 only if sitePlanImage provided
        for offset in (1, 2):
            if p_idx + 1 < len(doc.paragraphs):
                cand = doc.paragraphs[p_idx + 1]
                if not cand.text.strip() or cand.text.strip().startswith("Figure 1:"):
                    _remove_element(cand)
        if site_plan_b64:
            _insert_b64_image_after(p_bldg, site_plan_b64, "Figure 1: Assessed Building / Compartment Location")
        else:
            _insert_paragraph_after(
                p_bldg,
                "[Placeholder — Insert Figure 1: Site / Assessed Locations Plan]",
                style="Numbered Text",
            )
        # Replace Panattoni-specific details in remaining paragraphs with placeholders
        for p in doc.paragraphs:
            txt = p.text
            if "AEW Architects[2]" in txt:
                _set_paragraph_text(
                    p,
                    "It is understood from the fire strategy drawings[2] that, as a client/strategy requirement, the assessed areas need to achieve [Placeholder — e.g. 120-minutes] fire resistance separation where applicable.",
                )
            elif "4.2m and 8.4m" in txt:
                _set_paragraph_text(
                    p,
                    "In terms of load-bearing fire resistance for the upper floors, the structure should achieve at least [Placeholder — e.g. 30-minutes / 60-minutes] for life safety purposes given the top storey height(s) of [Placeholder — e.g. X.X m].",
                )
            elif "first floor of the main office sits above" in txt:
                _set_paragraph_text(
                    p,
                    "[Placeholder — Describe storey-by-storey use and structural arrangement (e.g. ground floor reception, upper open-plan offices, plant deck).]",
                )
            elif "fire strategy for this warehouse specifies" in txt:
                _set_paragraph_text(
                    p,
                    "[Placeholder — State the building-specific compartmentation / fire resistance separation requirements from the Fire Strategy.]",
                )
            elif "if they are located in the warehouse compartment" in txt:
                _set_paragraph_text(
                    p,
                    "All columns, edge beams, primary and secondary beams, and beams enclosing shafts (stairs or risers) will be passively protected to achieve [Placeholder — e.g. 60-minutes / 120-minutes] fire resistance in accordance with the fire strategy and Appendix D. The critical temperature used for determining the fire resistance for the primary beams and supporting structure should follow the results from the MACS+ calculations in Appendix A.",
                )
            elif "confirmed by J&D Pierce" in txt:
                _set_paragraph_text(
                    p,
                    "It is assumed from the beam layout drawings that all secondary beams will be designed to act as composite and it should be confirmed by the structural engineer that the degree of shear connection achieves the minimum requirement in Appendix A.",
                )
            elif "warehouse undercroft" in txt:
                _set_paragraph_text(
                    p,
                    "Distributions of parametric time-temperature curves have been generated using a Monte Carlo simulation and have been used in this analysis to simulate the possible fire scenarios within the assessed compartments.",
                )
            elif "plant deck area (third floor of the main office)" in txt:
                _set_paragraph_text(
                    p,
                    "An imposed load of [Placeholder — e.g. 5.0 kN/m²] has been used in the analysis on the structural elements supporting the assessed floor areas.",
                )

    # Section 1.3 Information Used bullets (keep drawing placeholders instead of AEW / J&D Pierce)
    p_pierce = _find_paragraph(doc, "Internal Office Plans and Elevations")
    if p_pierce is not None:
        _set_paragraph_text(p_pierce, "[Placeholder — Structural Plans and Elevations Drawings provided by Structural Engineer[3]]")
    p_aew_main = _find_paragraph(doc, "Main Office Fire Strategy Drawings")
    if p_aew_main is not None:
        _set_paragraph_text(p_aew_main, "[Placeholder — Fire Strategy Drawings provided by Architect[2]]")
    p_aew_tr = _find_paragraph(doc, "Transport Offices Fire Strategy Drawings")
    if p_aew_tr is not None:
        _remove_element(p_aew_tr)

    p_info_intro = _find_paragraph(doc, "The calculations in this report are based on")
    if p_info_intro is not None and report_details.get("informationUsed"):
        cursor = p_info_intro
        for item in report_details["informationUsed"]:
            cursor = _insert_paragraph_after(cursor, str(item), style="Bullet Point")

    # 4. Section 2.4 Figure 4 (Monte Carlo parametric / steel temp curves)
    p_fig4_intro = _find_paragraph(doc, "The parametric fire curves from the 10,000")
    if p_fig4_intro is not None:
        _set_paragraph_text(
            p_fig4_intro,
            "The Monte Carlo simulation generates stochastic parametric fire exposures and evaluates structural thermal response across the sampled scenarios.",
        )
        p_idx = _paragraph_index(doc, p_fig4_intro)
        # Remove template's Figure 4 image & caption (collect before removing so indices don't shift)
        to_remove = []
        for offset in (1, 2):
            if p_idx + offset < len(doc.paragraphs):
                cand = doc.paragraphs[p_idx + offset]
                if not cand.text.strip().startswith("Acceptance Criteria"):
                    to_remove.append(cand)
        for cand in to_remove:
            _remove_element(cand)
        fig4_b64 = (time_eq_result.get("charts") or {}).get("steelTempSpaghetti") or (macs_batch.get("charts") or {}).get("beamTemp")
        if fig4_b64:
            _insert_b64_image_after(p_fig4_intro, fig4_b64, "Figure 4: Monte Carlo Temperature Curves Distribution")

    # 5. Section 4 Outcomes and Conclusion
    p_outcomes_hdr = _find_paragraph(doc, "Outcomes and Conclusion")
    if p_outcomes_hdr is not None:
        p_idx = _paragraph_index(doc, p_outcomes_hdr)
        to_remove = []
        for cand in doc.paragraphs[p_idx + 1 :]:
            if cand.text.strip() == "References":
                break
            to_remove.append(cand)
        for cand in to_remove:
            _remove_element(cand)

        cursor = p_outcomes_hdr
        if macs_batch:
            rc = macs_batch.get("run_count", 0)
            pc = macs_batch.get("pass_count", 0)
            rel = macs_batch.get("reliability_percent", 0.0)
            cursor = _insert_paragraph_after(
                cursor,
                f"Among the {rc:,} MACS+ Monte Carlo simulations performed, the composite floor slab withstood the applied loads in {pc:,} cases, achieving a batch reliability of {rel:.2f}% against the {target_rel_str} acceptance criterion.",
                style="Numbered Text",
            )
            if latest_run:
                cursor = _insert_paragraph_after(
                    cursor,
                    f"The governing perimeter beam is on Side {latest_run.governing_side} ({latest_run.section}, {latest_run.exposure}), with a governing critical temperature of {latest_run.critical_temp:.1f}°C.",
                    style="Numbered Text",
                )
        else:
            cursor = _insert_paragraph_after(
                cursor,
                "No MACS+ batch assessment data has been linked to this project.",
                style="Numbered Text",
            )

        if time_eq_result:
            pf = time_eq_result.get("failure_prob")
            if pf is None and time_eq_result.get("nSim") and time_eq_result.get("nFailed") is not None:
                pf = time_eq_result["nFailed"] / time_eq_result["nSim"]
            rel_teq = time_eq_result.get("reliabilityPercent")
            if rel_teq is None and pf is not None:
                rel_teq = (1.0 - pf) * 100.0
            n_sim = time_eq_result.get("nSim") or 0
            n_failed = time_eq_result.get("nFailed") or 0
            crit_t = time_eq_inputs.get("criticalTemp", 550)
            fr = time_eq_inputs.get("fireResistancePeriod", 60)
            sec_name = time_eq_inputs.get("section") or "assessed steel section"
            rel_teq_str = f"{rel_teq:.2f}%" if rel_teq is not None else "N/A"
            _insert_paragraph_after(
                cursor,
                f"The Monte Carlo Time Equivalence analysis ({n_sim:,} simulations, {n_failed:,} exceeding {crit_t}°C) for {sec_name} protected to {fr} minutes fire resistance achieved a structural reliability of {rel_teq_str}.",
                style="Numbered Text",
            )
        else:
            _insert_paragraph_after(
                cursor,
                "No Monte Carlo Time Equivalence results have been generated for this project.",
                style="Numbered Text",
            )

    # 6. Section 5 References (replace Panattoni drawing references with placeholders so [1]..[14] numbering stays intact)
    p_ref_aew = _find_paragraph(doc, "AEW Architects.")
    if p_ref_aew is not None:
        _set_paragraph_text(p_ref_aew, "[Placeholder — Architect Fire Strategy Drawings reference]")
    p_ref_pierce = _find_paragraph(doc, "J&D Pierce Contracts Ltd.")
    if p_ref_pierce is not None:
        _set_paragraph_text(p_ref_pierce, "[Placeholder — Structural Engineer Drawings reference]")

    # 7. Appendix A (MACS+ Inputs, Calculations, and Results — keep template's A.1 & A.2 Sheet 1–4 tables!)
    p_app_a = _find_paragraph(doc, "Inputs, Calculations, and Results")
    if p_app_a is not None:
        t_a1_12 = t_a1_34 = t_a2_12 = t_a2_34 = None
        for tbl in list(doc.tables):
            first_cell = tbl.rows[0].cells[0].text if tbl.rows else ""
            if "A.1." in first_cell and "Sheet 1" in first_cell:
                t_a1_12 = tbl
            elif "A.1." in first_cell and "Sheet 3" in first_cell:
                t_a1_34 = tbl
            elif "A.2." in first_cell and "Sheet 1" in first_cell:
                t_a2_12 = tbl
            elif "A.2." in first_cell and "Sheet 3" in first_cell:
                t_a2_34 = tbl

        sample_runs = macs_batch.get("sample_runs") or []
        sr1_num = sample_runs[0].get("run_number") if len(sample_runs) >= 1 else None
        sr2_num = sample_runs[1].get("run_number") if len(sample_runs) >= 2 else None
        rc = macs_batch.get("run_count", 0)
        b_disp = macs_batch.get("name") or project_name

        p_a1_sub = _find_paragraph(doc, "Main Office First Floor")
        if p_a1_sub is not None and macs_batch:
            sim1 = f" – Simulation {int(sr1_num):,} of {int(rc):,}" if sr1_num is not None else ""
            _set_paragraph_text(p_a1_sub, f"MACS+ Assessment — {b_disp}{sim1}")
        elif p_a1_sub is not None:
            _remove_element(p_a1_sub)

        p_a2_sub = _find_paragraph(doc, "Main Office Second Floor")
        if p_a2_sub is not None and macs_batch:
            sim2 = f" – Simulation {int(sr2_num):,} of {int(rc):,}" if sr2_num is not None else ""
            _set_paragraph_text(p_a2_sub, f"MACS+ Assessment — {b_disp}{sim2}")
        elif p_a2_sub is not None:
            _remove_element(p_a2_sub)

        _populate_macs_appendix(
            doc, p_app_a, macs_batch, latest_run,
            t_a1_12=t_a1_12, t_a1_34=t_a1_34, t_a2_12=t_a2_12, t_a2_34=t_a2_34,
        )

    # 8. Appendix C (Time Equivalence Method Results)
    p_app_c = _find_paragraph(doc, "Time Equivalence Method Results")
    if p_app_c is not None:
        p_idx = _paragraph_index(doc, p_app_c)
        to_remove = []
        for cand in doc.paragraphs[p_idx + 1 :]:
            if cand.text.strip() == "Indicative Mark-up":
                break
            to_remove.append(cand)
        for cand in to_remove:
            _remove_element(cand)
        _populate_teq_appendix(doc, p_app_c, time_eq_inputs, time_eq_result)

    # 9. Appendix D (Indicative Mark-up)
    p_app_d = _find_paragraph(doc, "Indicative Mark-up")
    if p_app_d is not None:
        p_idx = _paragraph_index(doc, p_app_d)
        for cand in list(doc.paragraphs[p_idx + 1 :]):
            # Preserve any paragraph carrying <w:sectPr> (which holds the document's headerReference)
            if cand._element.find(f".//{{{W_NS}}}sectPr") is not None:
                for child in list(cand._element):
                    if child.tag != f"{{{W_NS}}}pPr":
                        cand._element.remove(child)
            else:
                _remove_element(cand)
        markup_b64 = report_details.get("markupImage")
        if markup_b64:
            _insert_b64_image_after(p_app_d, markup_b64, "Figure D.1: Indicative Fire Protection Mark-up")
        else:
            _insert_paragraph_after(
                p_app_d,
                "[Placeholder — Insert indicative fire protection mark-up drawings]",
                style="Appendix Text",
            )

    raw_out = io.BytesIO()
    doc.save(raw_out)
    raw_out.seek(0)

    # Update docProps/app.xml (<Company>, <TitlesOfParts>) so Word's data-bound
    # cover page Quick Parts reflect the project and client rather than template defaults.
    final_out = io.BytesIO()
    with zipfile.ZipFile(raw_out, "r") as zin, zipfile.ZipFile(final_out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                app_root = etree.fromstring(data)
                ep_ns = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
                vt_ns = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
                comp_el = app_root.find(f"{{{ep_ns}}}Company")
                if comp_el is not None:
                    comp_el.text = client_name
                for lpstr in app_root.findall(f".//{{{vt_ns}}}lpstr"):
                    if lpstr.text and "Panattoni" in lpstr.text:
                        lpstr.text = project_name
                data = etree.tostring(app_root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)
    return final_out.getvalue()
