"""One-time extraction of the warehouse smoke layer report "skin" and blocks.

Kathryn's Word template carries two kinds of content:

* things we can author as text (headings, prose, captions) — these live in
  ``templates/warehouse/report_single_building.md.j2`` and are NOT taken from here;
* things we cannot author as text — the cover page, header/footer, styles and
  numbering, the OMML equations, the ASET/RSET shapes diagram. Those are pulled out
  here once, into ``templates/warehouse/skin_single_building.docx`` (the document with
  its body emptied) and ``templates/warehouse/blocks/*.xml`` (named XML fragments).

Re-run only if the team changes the cover page, styling or an equation:

    python scripts/warehouse_report_extract.py "path/to/Report_Single_Building_Template.docx"

Body indices below refer to that template as of 1 Sep 2026.
"""

import copy
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "templates" / "warehouse"
BLOCKS = OUT_DIR / "blocks"

FIRST_BODY_INDEX = 47  # "Introduction" heading; everything before is cover + TOC

# name -> body index of the paragraph holding the maths (display equations)
EQUATIONS = {
    "eq_hrr": 128,
    "eq_mass_flow": 145,
    "eq_plume_temp": 157,
    "eq_layer_temp_change": 168,
    "eq_layer_density": 179,
    "eq_layer_depth": 187,
}

# name -> (body index, occurrence within that paragraph) of an inline symbol
SYMBOLS = {
    "Q": (130, 0),
    "t": (131, 0),
    "alpha": (132, 0),
    "Qc": (153, 0),
    "m_smoke": (148, 0),
    "T_smoke": (159, 0),
    "dT_upper": (170, 0),
    "T_upper": (172, 0),
    "m_upper": (174, 0),
    "rho_upper": (181, 0),
    "H": (189, 0),
    "timestep": (191, 0),
    "Area": (194, 0),
}

DIAGRAM_INDEX = 101  # ASET/RSET methodology, drawn with shapes
SITE_PLAN_INDEX = 61  # placeholder picture
RESULTS_TABLE_INDEX = 231  # ASET/RSET summary table, keeps its {{...}} cell placeholders

COMMENT_REL_TYPES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
    "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
    "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds",
    "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible",
    "http://schemas.microsoft.com/office/2011/relationships/people",
)

M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _write_xml(name: str, element) -> None:
    from lxml import etree

    xml = etree.tostring(element, encoding="unicode")
    (BLOCKS / f"{name}.xml").write_text(xml, encoding="utf-8")


def _replace_seq_fields(root, literal: str) -> None:
    """Replace every complex field (fldChar begin..end) under root with a literal run.

    The caption inside the diagram is "Figure { SEQ Figure } 2: ..." — Word would
    renumber it independently of our text captions, so it becomes a placeholder the
    builder fills with the number it assigned.
    """
    for paragraph in root.iter(qn("w:p")):
        runs = [r for r in paragraph if r.tag == qn("w:r")]
        field_runs = []
        state = None
        for run in runs:
            fld = run.find(qn("w:fldChar"))
            kind = fld.get(qn("w:fldCharType")) if fld is not None else None
            if kind == "begin":
                state = "in"
                field_runs = [run]
            elif state == "in":
                field_runs.append(run)
                if kind == "end":
                    # Keep the first run's formatting, give it the literal text.
                    keep = field_runs[0]
                    for child in list(keep):
                        if child.tag != qn("w:rPr"):
                            keep.remove(child)
                    t = keep.makeelement(qn("w:t"), {})
                    t.text = literal
                    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    keep.append(t)
                    for run_ in field_runs[1:]:
                        paragraph.remove(run_)
                    state = None
                    field_runs = []


def main(source: str) -> None:
    doc = Document(source)
    body = doc.element.body
    children = list(body.iterchildren())

    BLOCKS.mkdir(parents=True, exist_ok=True)

    # ---- blocks ----
    for name, idx in EQUATIONS.items():
        maths = children[idx].findall(".//" + M + "oMathPara")
        assert len(maths) == 1, (name, idx, len(maths))
        _write_xml(name, copy.deepcopy(maths[0]))

    for name, (idx, occurrence) in SYMBOLS.items():
        maths = children[idx].findall(".//" + M + "oMath")
        assert maths, (name, idx)
        _write_xml(name, copy.deepcopy(maths[occurrence]))

    diagram = children[DIAGRAM_INDEX]
    assert diagram.findall(".//" + A + "blip") == [], "diagram references images; handle rels"
    assert not [e for e in diagram.iter() if e.get(R + "embed") or e.get(R + "id")]
    # Strip comment anchors so the block is self-contained.
    for tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
        for el in diagram.findall(".//" + qn(f"w:{tag}")):
            el.getparent().remove(el)
    _replace_seq_fields(diagram, "{{FIGURE_NUMBER}}")
    assert diagram.findall(".//" + qn("w:fldChar")) == [], "unexpected field left in diagram"
    _write_xml("aset_rset_diagram", copy.deepcopy(diagram))

    table = children[RESULTS_TABLE_INDEX]
    assert table.tag == qn("w:tbl"), table.tag
    for tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
        for el in table.findall(".//" + qn(f"w:{tag}")):
            el.getparent().remove(el)
    # The template's value rows have stray bold on a few cells (Travel Time, Total
    # RSET, Calculated ASET); only the header row is meant to be bold.
    for row in table.findall(qn("w:tr"))[1:]:
        for bold in row.findall(".//" + qn("w:b")) + row.findall(".//" + qn("w:bCs")):
            bold.getparent().remove(bold)
    _write_xml("results_table", copy.deepcopy(table))

    blip = children[SITE_PLAN_INDEX].findall(".//" + A + "blip")[0]
    part = doc.part.related_parts[blip.get(R + "embed")]
    (BLOCKS / "site_plan_placeholder.png").write_bytes(part.blob)

    # ---- skin ----
    for child in children[FIRST_BODY_INDEX:]:
        if child.tag == qn("w:sectPr"):
            continue
        body.remove(child)

    for rel_id, rel in list(doc.part.rels.items()):
        if rel.reltype in COMMENT_REL_TYPES:
            doc.part.drop_rel(rel_id)

    leftovers = body.findall(".//" + qn("w:commentRangeStart"))
    assert not leftovers, "comment anchors remain in the cover/TOC"

    # Ask Word to refresh the TOC and other fields on open.
    settings = doc.settings.element
    if settings.find(qn("w:updateFields")) is None:
        from docx.oxml import OxmlElement

        upd = OxmlElement("w:updateFields")
        upd.set(qn("w:val"), "true")
        settings.insert(0, upd)

    doc.save(OUT_DIR / "skin_single_building.docx")
    print("wrote", OUT_DIR / "skin_single_building.docx")
    print("blocks:", sorted(p.name for p in BLOCKS.iterdir()))


if __name__ == "__main__":
    main(sys.argv[1])
