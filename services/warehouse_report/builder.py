"""Turn a rendered line-oriented text into paragraphs on a Word "skin".

Line grammar (one paragraph per line, blank lines ignored)::

    # Heading                    Main Headd            (numbered 1., 2., ...)
    ## Heading                   FD Subheading 1       (numbered 3.1., ...)
    ### Heading                  Astute References, unnumbered, bold, indented
    = text                       definition line (ASTUTE Body Text), indented
    > text                       equation "where:" line, unnumbered, italic, indented
    - text                       reference list entry, hanging indent
    @Style Name| text            any paragraph style from the skin, as-is
    !! text                      engineer prompt: bold, highlighted, must be edited out
    !fig key | caption           picture from figures[key], then "Figure N: caption"
    !figblock key | blockname    a block that is itself a figure with its own caption;
                                 {{FIGURE_NUMBER}} inside it becomes N
    !tab key                     marker: assigns the next table number to key
    !pagebreak                   start a new page
    !table key | caption         table from tables[key] (rows of cells; "^" merges up)
    [[name]]                     a block from blocks/: a whole paragraph or table when
                                 the fragment is w:p / w:tbl, a display equation when
                                 m:oMathPara, or an inline symbol (m:oMath) mid-line
    text                         Parag                 (numbered 1.1.1., ...)

Inline: ``**bold**``; ``[3]`` citations are superscript (except in reference lines);
``{fig:key}`` / ``{tab:key}`` become the figure/table numbers.
``{{KEY}}`` placeholders inside w:tbl / w:p blocks and in the skin's cover/header are
replaced from the substitution mapping.

The per-line paragraph overrides (no numbering, indents, italics) reproduce what the
team's template applied directly to those paragraphs on top of the named styles.
"""

import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Union

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_COLOR_INDEX
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, Twips

FIGURE_WIDTH_IN = 6.0
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
INLINE = re.compile(r"(\[\[\w+\]\]|\*\*.+?\*\*|\[\d+\])")
CITATION = re.compile(r"^\[\d+\]$")

ImageSource = Union[BytesIO, str, Path]


@dataclass(frozen=True)
class Fmt:
    """Paragraph + run overrides applied on top of a named style."""

    style: str
    unnumbered: bool = False
    indent: Optional[int] = None  # twips
    hanging: Optional[int] = None  # twips
    center: bool = False
    bold: bool = False
    italic: bool = False
    highlight: bool = False
    font: Optional[str] = None
    size_pt: Optional[float] = None
    superscript_citations: bool = True  # "[3]" in running text; off for the reference list itself


HEADING_1 = Fmt("Main Headd")
HEADING_2 = Fmt("FD Subheading 1")
HEADING_3 = Fmt("Astute References", unnumbered=True, indent=720, bold=True)
BODY = Fmt("Parag")
DEFINITION = Fmt("ASTUTE Body Text", indent=720, font="Segoe UI Semilight", size_pt=10)
WHERE_LINE = Fmt("Appendix Text", unnumbered=True, indent=1416, italic=True)
EQUATION = Fmt("Appendix Text", unnumbered=True, indent=720)
PICTURE = Fmt("Appendix Text", unnumbered=True, center=True)
CAPTION = Fmt("figure / table title")
REFERENCE = Fmt("List Paragraph", indent=714, hanging=357, superscript_citations=False)
ENGINEER_NOTE = Fmt("Parag", unnumbered=True, indent=720, bold=True, highlight=True)
TABLE_STYLE = "Table Grid"


class DocBuilder:
    def __init__(self, skin: Union[str, Path], blocks_dir: Union[str, Path]):
        self.doc = Document(str(skin))
        self.blocks_dir = Path(blocks_dir)
        self._body = self.doc.element.body
        self._sect_pr = self._body.find(qn("w:sectPr"))

    # ------------------------------------------------------------------ public

    def substitute(self, mapping: Mapping[str, str]) -> None:
        """Replace {{KEY}} placeholders in the skin: body, text boxes, headers, footers."""
        roots = [self.doc.element]
        for section in self.doc.sections:
            roots.extend([section.header._element, section.footer._element])
        for root in roots:
            for paragraph in root.iter(qn("w:p")):
                _substitute_in_paragraph(paragraph, mapping)

    def render(
        self,
        text: str,
        figures: Optional[Mapping[str, ImageSource]] = None,
        tables: Optional[Mapping[str, List[List[str]]]] = None,
        substitutions: Optional[Mapping[str, str]] = None,
    ) -> None:
        figures = figures or {}
        tables = tables or {}
        substitutions = substitutions or {}

        lines = [line.rstrip() for line in text.splitlines()]
        lines = _resolve_numbers(lines)

        for line in lines:
            if not line.strip():
                continue
            self._render_line(line, figures, tables, substitutions)

    def save(self) -> BytesIO:
        stream = BytesIO()
        self.doc.save(stream)
        stream.seek(0)
        return stream

    def text(self) -> str:
        """Plain text of the body, for tests and snapshots."""
        parts = []
        for child in self._body.iterchildren():
            if child.tag == qn("w:p"):
                parts.append(_paragraph_text(child))
            elif child.tag == qn("w:tbl"):
                for row in child.iter(qn("w:tr")):
                    parts.append(" | ".join(_paragraph_text(p) for p in row.iter(qn("w:p"))))
        return "\n".join(parts)

    # ----------------------------------------------------------------- private

    def _render_line(self, line, figures, tables, substitutions) -> None:
        if line.startswith("!fig "):
            key, caption = _split_marker(line[5:])
            self._add_picture(figures[key])
            self._add_paragraph(CAPTION, f"Figure {caption}")
        elif line.startswith("!figblock "):
            name, number = _split_marker(line[10:])
            self._add_standalone_block(name, {**substitutions, "FIGURE_NUMBER": number})
        elif line.startswith("!tab "):
            return  # numbering marker only
        elif line.strip() == "!pagebreak":
            self.doc.add_page_break()
        elif line.startswith("!table "):
            key, caption = _split_marker(line[7:])
            self._add_table(tables[key])
            self._add_paragraph(CAPTION, f"Table {caption}")
        elif line.startswith("!! "):
            self._add_paragraph(ENGINEER_NOTE, "ENGINEER TO EDIT: " + line[3:].strip())
        elif line.startswith("### "):
            self._add_paragraph(HEADING_3, line[4:])
        elif line.startswith("## "):
            self._add_paragraph(HEADING_2, line[3:])
        elif line.startswith("# "):
            self._add_paragraph(HEADING_1, line[2:])
        elif line.startswith("= "):
            self._add_paragraph(DEFINITION, line[2:])
        elif line.startswith("> "):
            self._add_paragraph(WHERE_LINE, line[2:])
        elif line.startswith("- "):
            self._add_paragraph(REFERENCE, line[2:])
        elif line.startswith("@"):
            style, content = line[1:].split("|", 1)
            self._add_paragraph(Fmt(style.strip()), content.strip())
        elif re.fullmatch(r"\[\[\w+\]\]", line.strip()):
            self._add_standalone_block(line.strip()[2:-2], substitutions)
        else:
            self._add_paragraph(BODY, line)

    def _add_paragraph(self, fmt: Fmt, content: str):
        paragraph = self.doc.add_paragraph(style=fmt.style)
        _apply_paragraph_format(paragraph, fmt)
        for token in INLINE.split(content):
            if not token:
                continue
            if token.startswith("[[") and token.endswith("]]"):
                element = self._load_block(token[2:-2])
                if element.tag in (qn("m:oMath"), qn("m:oMathPara")):
                    paragraph._p.append(element)
                else:
                    raise ValueError(f"block {token} is not inline maths; put it on its own line")
            elif token.startswith("**") and token.endswith("**"):
                run = paragraph.add_run(token[2:-2])
                _apply_run_format(run, fmt)
                run.bold = True
            elif CITATION.match(token) and fmt.superscript_citations:
                run = paragraph.add_run(token)
                _apply_run_format(run, fmt)
                run.font.superscript = True
            else:
                _apply_run_format(paragraph.add_run(token), fmt)
        return paragraph

    def _add_standalone_block(self, name: str, substitutions: Mapping[str, str]) -> None:
        element = self._load_block(name)
        if element.tag == qn("m:oMathPara"):
            paragraph = self.doc.add_paragraph(style=EQUATION.style)
            _apply_paragraph_format(paragraph, EQUATION)
            paragraph._p.append(element)
        elif element.tag in (qn("w:p"), qn("w:tbl")):
            for paragraph in element.iter(qn("w:p")):
                _substitute_in_paragraph(paragraph, substitutions)
            self._sect_pr.addprevious(element)
        else:
            raise ValueError(f"block {name} ({element.tag}) cannot stand alone")

    def _add_picture(self, source: ImageSource) -> None:
        paragraph = self.doc.add_paragraph(style=PICTURE.style)
        _apply_paragraph_format(paragraph, PICTURE)
        if isinstance(source, BytesIO):
            source.seek(0)
        else:
            source = str(source)
        paragraph.add_run().add_picture(source, width=Inches(FIGURE_WIDTH_IN))

    def _add_table(self, rows: List[List[str]]) -> None:
        table = self.doc.add_table(rows=len(rows), cols=len(rows[0]))
        table.style = TABLE_STYLE
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if value == "^":
                    continue
                table.cell(r, c).text = value
                if r == 0:
                    for run in table.cell(r, c).paragraphs[0].runs:
                        run.bold = True
        # Merge "^" cells upward into the nearest filled cell above.
        for c in range(len(rows[0])):
            top = 0
            for r in range(len(rows)):
                if rows[r][c] != "^":
                    top = r
                elif r == len(rows) - 1 or rows[r + 1][c] != "^":
                    table.cell(top, c).merge(table.cell(r, c))

    def _load_block(self, name: str):
        path = self.blocks_dir / f"{name}.xml"
        if not path.exists():
            raise KeyError(f"unknown block [[{name}]] (no {path.name})")
        return parse_xml(path.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ helpers


def _apply_paragraph_format(paragraph, fmt: Fmt) -> None:
    pf = paragraph.paragraph_format
    if fmt.unnumbered:
        ppr = paragraph._p.get_or_add_pPr()
        num_pr = OxmlElement("w:numPr")
        ilvl = OxmlElement("w:ilvl")
        ilvl.set(qn("w:val"), "0")
        num_id = OxmlElement("w:numId")
        num_id.set(qn("w:val"), "0")
        num_pr.append(ilvl)
        num_pr.append(num_id)
        ppr.insert_element_before(
            num_pr,
            "w:suppressLineNumbers", "w:pBdr", "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku",
            "w:wordWrap", "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
            "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind", "w:contextualSpacing",
            "w:mirrorIndents", "w:suppressOverlap", "w:jc", "w:textDirection", "w:textAlignment",
            "w:textboxTightWrap", "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange",
        )
    if fmt.indent is not None:
        pf.left_indent = Twips(fmt.indent)
    if fmt.hanging is not None:
        pf.first_line_indent = Twips(-fmt.hanging)
    if fmt.center:
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _apply_run_format(run, fmt: Fmt) -> None:
    if fmt.bold:
        run.bold = True
    if fmt.italic:
        run.italic = True
    if fmt.highlight:
        run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    if fmt.font:
        run.font.name = fmt.font
    if fmt.size_pt:
        run.font.size = Pt(fmt.size_pt)


def _split_marker(rest: str):
    key, _, caption = rest.partition("|")
    return key.strip(), caption.strip()


def _resolve_numbers(lines: Iterable[str]) -> List[str]:
    """Assign figure/table numbers in order of appearance and resolve references."""
    lines = list(lines)
    figures: Dict[str, int] = {}
    tables: Dict[str, int] = {}
    for line in lines:
        if line.startswith("!fig "):
            key, _ = _split_marker(line[5:])
            figures.setdefault(key, len(figures) + 1)
        elif line.startswith("!figblock "):
            key, _ = _split_marker(line[10:])
            figures.setdefault(key, len(figures) + 1)
        elif line.startswith("!tab "):
            tables.setdefault(line[5:].strip(), len(tables) + 1)

    def resolve(text: str) -> str:
        text = re.sub(r"\{fig:(\w+)\}", lambda m: str(figures[m.group(1)]), text)
        return re.sub(r"\{tab:(\w+)\}", lambda m: str(tables[m.group(1)]), text)

    out = []
    for line in lines:
        if line.startswith("!fig "):
            key, caption = _split_marker(line[5:])
            out.append(f"!fig {key} | {figures[key]}: {resolve(caption)}")
        elif line.startswith("!figblock "):
            key, name = _split_marker(line[10:])
            out.append(f"!figblock {name} | {figures[key]}")
        elif line.startswith("!table "):
            key, caption = _split_marker(line[7:])
            out.append(f"!table {key} | {tables[key]}: {resolve(caption)}")
        else:
            out.append(resolve(line))
    return out


def _direct_texts(paragraph) -> list:
    """The w:t nodes of this paragraph's own runs.

    Deliberately not ``paragraph.iter(w:t)``: a paragraph that anchors text boxes
    (the cover page, the ASET/RSET diagram) contains whole nested paragraphs, and
    those must be handled on their own, not folded into their anchor's text.
    """
    p_tag = qn("w:p")

    def owner(node):
        parent = node.getparent()
        while parent is not None and parent.tag != p_tag:
            parent = parent.getparent()
        return parent

    return [t for t in paragraph.iter(qn("w:t")) if owner(t) is paragraph]


def _paragraph_text(paragraph) -> str:
    return "".join(t.text or "" for t in paragraph.iter(qn("w:t")))


def _substitute_in_paragraph(paragraph, mapping: Mapping[str, str]) -> None:
    """Replace {{KEY}} even when Word has split it across runs.

    The paragraph's own text is joined, substituted, and written back into the
    first text node; the other text nodes are emptied. Run formatting of the first
    node is kept, which is what the cover page and table cells need.
    """
    texts = _direct_texts(paragraph)
    if not texts:
        return
    joined = "".join(t.text or "" for t in texts)
    if "{{" not in joined:
        return

    def replacement(match):
        key = match.group(1)
        return str(mapping[key]) if key in mapping else match.group(0)

    new = PLACEHOLDER.sub(replacement, joined)
    if new == joined:
        return
    texts[0].text = new
    texts[0].set(qn("xml:space"), "preserve")
    for t in texts[1:]:
        t.text = ""
