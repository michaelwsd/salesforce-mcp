"""OOXML repair for screener .docx files.

python-docx appends hand-built elements (shading, borders, tabs, cell margins)
to the end of their parent, but the WordprocessingML schema requires a fixed
child order. Word tolerates some misordering and reports the rest as a
validation error ("Word found unreadable content"). This module puts every
property element back into schema order and fixes the default template's
<w:zoom> element, which lacks the required w:percent attribute.

Usage:
    python fix_xml.py input.docx output.docx

build_screener.py applies the same repair automatically before saving.
"""

import sys
import zipfile

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


# Child order from the ECMA-376 schema (CT_PPr, CT_TblPr, CT_TcPr, ...).
SCHEMA_ORDER = {
    "pPr": [
        "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr",
        "widowControl", "numPr", "suppressLineNumbers", "pBdr", "shd", "tabs",
        "suppressAutoHyphens", "kinsoku", "wordWrap", "overflowPunct",
        "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
        "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents",
        "suppressOverlap", "jc", "textDirection", "textAlignment",
        "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr", "sectPr",
        "pPrChange",
    ],
    "tblPr": [
        "tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize",
        "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing", "tblInd",
        "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption",
        "tblDescription", "tblPrChange",
    ],
    "tcPr": [
        "cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd",
        "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark",
        "headers", "cellIns", "cellDel", "cellMerge", "tcPrChange",
    ],
    "trPr": [
        "cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter",
        "cantSplit", "trHeight", "tblHeader", "tblCellSpacing", "jc", "hidden",
        "ins", "del", "trPrChange",
    ],
    "pBdr": ["top", "left", "bottom", "right", "between", "bar"],
    "tblBorders": ["top", "left", "start", "bottom", "right", "end", "insideH", "insideV"],
    "tcBorders": [
        "top", "left", "start", "bottom", "right", "end", "insideH", "insideV",
        "tl2br", "tr2bl",
    ],
    "tcMar": ["top", "left", "start", "bottom", "right", "end"],
    "tblCellMar": ["top", "left", "start", "bottom", "right", "end"],
}


def _reorder(parent, order: list[str]) -> None:
    rank = {_w(tag): i for i, tag in enumerate(order)}
    children = list(parent)
    # Stable sort keeps duplicates and unknown elements in their relative order;
    # unknown elements go last.
    children.sort(key=lambda c: rank.get(c.tag, len(order)))
    for child in children:
        parent.remove(child)
        parent.append(child)


def repair_tree(root) -> None:
    """Reorder property children into schema order, in place, for any part's XML root."""
    for local, order in SCHEMA_ORDER.items():
        for parent in root.iter(_w(local)):
            _reorder(parent, order)


def repair_settings(root) -> None:
    for zoom in root.iter(_w("zoom")):
        if zoom.get(_w("percent")) is None:
            zoom.set(_w("percent"), "100")


def repair_docx(src: str, dst: str) -> None:
    """Copy src to dst, repairing document, header, footer and settings parts."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            name = item.filename
            if name.startswith("word/") and name.endswith(".xml") and (
                name in ("word/document.xml", "word/settings.xml", "word/styles.xml")
                or name.startswith(("word/header", "word/footer"))
            ):
                root = etree.fromstring(data)
                repair_tree(root)
                if name == "word/settings.xml":
                    repair_settings(root)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python fix_xml.py input.docx output.docx")
    repair_docx(sys.argv[1], sys.argv[2])
    print(f"Repaired -> {sys.argv[2]}")
