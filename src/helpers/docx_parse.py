import re
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def _fmt_flags(r):
    rPr = r.find("w:rPr", namespaces=NS)
    if rPr is None:
        return False, False, False, False

    bold = rPr.find("w:b", namespaces=NS) is not None
    italic = rPr.find("w:i", namespaces=NS) is not None

    sub = sup = False
    va = rPr.find("w:vertAlign", namespaces=NS)
    if va is not None:
        val = va.get(f"{{{W}}}val")  # w:val
        sub = (val == "subscript")
        sup = (val == "superscript")

    return bold, italic, sub, sup


def _wrap(txt, bold, italic, sub, sup):
    if txt == "":
        return txt
    if bold:
        txt = f"**{txt}**"
    if italic:
        txt = f"_{txt}_"
    if sub:
        txt = f"~{txt}~"
    if sup:
        txt = f"^{txt}^"
    return txt


def _run_to_text(r):
    bold, italic, sub, sup = _fmt_flags(r)
    out = []
    for child in r:
        tag = etree.QName(child).localname
        if tag == "t":
            out.append(_wrap(child.text or "", bold, italic, sub, sup))
        elif tag == "tab":
            out.append("\t")
        elif tag in ("br", "cr"):
            out.append("\n")
        # ignore other run children (drawing, fldChar, etc.) but they don't contain visible text
    return "".join(out)


def _run_to_text_plain(r):
    out = []
    for child in r:
        tag = etree.QName(child).localname
        if tag == "t":
            out.append(child.text or "")
        elif tag == "tab":
            out.append("\t")
        elif tag in ("br", "cr"):
            out.append("\n")
    return "".join(out)


def _as_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _to_roman(num: int, *, upper: bool = True) -> str:
    values = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    n = max(1, num)
    out: list[str] = []
    for value, numeral in values:
        while n >= value:
            out.append(numeral)
            n -= value
    roman = "".join(out)
    return roman if upper else roman.lower()


def _to_alpha(num: int, *, upper: bool = False) -> str:
    # 1 -> a, 26 -> z, 27 -> aa
    n = max(1, num)
    chars: list[str] = []
    while n > 0:
        n -= 1
        chars.append(chr(ord("A") + (n % 26)))
        n //= 26
    result = "".join(reversed(chars))
    return result if upper else result.lower()


def _format_list_number(value: int, fmt: str) -> str:
    if fmt == "upperRoman":
        return _to_roman(value, upper=True)
    if fmt == "lowerRoman":
        return _to_roman(value, upper=False)
    if fmt == "upperLetter":
        return _to_alpha(value, upper=True)
    if fmt == "lowerLetter":
        return _to_alpha(value, upper=False)
    if fmt == "decimalZero":
        return f"{value:02d}"
    return str(value)


def _normalize_bullet(marker: str) -> str:
    raw = marker.strip()
    if not raw:
        return "•"
    # Word often stores Symbol bullets as private-use glyphs (e.g. \uf0b7).
    if any("\uf000" <= ch <= "\uf8ff" for ch in raw):
        return "•"
    return raw


def _parse_level_definition(lvl) -> dict[str, object]:
    num_fmt_node = lvl.find("./w:numFmt", namespaces=NS)
    lvl_text_node = lvl.find("./w:lvlText", namespaces=NS)
    start_node = lvl.find("./w:start", namespaces=NS)
    ilvl = _as_int(lvl.get(f"{{{W}}}ilvl"), 0)
    return {
        "num_fmt": (
            str(num_fmt_node.get(f"{{{W}}}val"))
            if num_fmt_node is not None and num_fmt_node.get(f"{{{W}}}val") is not None
            else "decimal"
        ),
        "lvl_text": (
            str(lvl_text_node.get(f"{{{W}}}val"))
            if lvl_text_node is not None and lvl_text_node.get(f"{{{W}}}val") is not None
            else f"%{ilvl + 1}."
        ),
        "start": _as_int(start_node.get(f"{{{W}}}val") if start_node is not None else None, 1),
    }


def _load_numbering_definitions(z: ZipFile) -> dict[int, dict[int, dict[str, object]]]:
    try:
        numbering_xml = z.read("word/numbering.xml")
    except KeyError:
        return {}

    root = etree.fromstring(numbering_xml)

    abstract_defs: dict[int, dict[int, dict[str, object]]] = {}
    for abstract in root.findall(".//w:abstractNum", namespaces=NS):
        abstract_id = _as_int(abstract.get(f"{{{W}}}abstractNumId"), -1)
        if abstract_id < 0:
            continue
        levels: dict[int, dict[str, object]] = {}
        for lvl in abstract.findall("./w:lvl", namespaces=NS):
            ilvl = _as_int(lvl.get(f"{{{W}}}ilvl"), 0)
            levels[ilvl] = _parse_level_definition(lvl)
        abstract_defs[abstract_id] = levels

    numbering_defs: dict[int, dict[int, dict[str, object]]] = {}
    for num in root.findall(".//w:num", namespaces=NS):
        num_id = _as_int(num.get(f"{{{W}}}numId"), -1)
        if num_id < 0:
            continue
        abstract_node = num.find("./w:abstractNumId", namespaces=NS)
        abstract_id = _as_int(
            abstract_node.get(f"{{{W}}}val") if abstract_node is not None else None, -1
        )
        levels = {k: dict(v) for k, v in abstract_defs.get(abstract_id, {}).items()}

        for override in num.findall("./w:lvlOverride", namespaces=NS):
            ilvl = _as_int(override.get(f"{{{W}}}ilvl"), 0)
            lvl = override.find("./w:lvl", namespaces=NS)
            start_override = override.find("./w:startOverride", namespaces=NS)
            if lvl is not None:
                levels[ilvl] = _parse_level_definition(lvl)
            elif start_override is not None:
                base = dict(levels.get(ilvl, {"num_fmt": "decimal", "lvl_text": f"%{ilvl + 1}."}))
                base["start"] = _as_int(start_override.get(f"{{{W}}}val"), 1)
                levels[ilvl] = base

        numbering_defs[num_id] = levels

    return numbering_defs


def _paragraph_list_prefix(
    p,
    *,
    numbering_defs: dict[int, dict[int, dict[str, object]]],
    counters: dict[int, dict[int, int]],
) -> str:
    pPr = p.find("./w:pPr", namespaces=NS)
    if pPr is None:
        return ""
    numPr = pPr.find("./w:numPr", namespaces=NS)
    if numPr is None:
        return ""

    num_id_node = numPr.find("./w:numId", namespaces=NS)
    if num_id_node is None:
        return ""
    ilvl_node = numPr.find("./w:ilvl", namespaces=NS)

    num_id = _as_int(num_id_node.get(f"{{{W}}}val"), -1)
    ilvl = _as_int(ilvl_node.get(f"{{{W}}}val") if ilvl_node is not None else None, 0)
    if num_id < 0:
        return ""

    level_defs = numbering_defs.get(num_id, {})
    current_level = dict(
        level_defs.get(ilvl, {"num_fmt": "decimal", "lvl_text": f"%{ilvl + 1}.", "start": 1})
    )
    fmt = str(current_level.get("num_fmt", "decimal"))
    lvl_text = str(current_level.get("lvl_text", f"%{ilvl + 1}."))
    start = _as_int(str(current_level.get("start", 1)), 1)

    if fmt == "bullet":
        return f"{_normalize_bullet(lvl_text)} "

    num_counters = counters.setdefault(num_id, {})
    next_value = num_counters.get(ilvl, start - 1) + 1
    num_counters[ilvl] = next_value
    for lvl in list(num_counters.keys()):
        if lvl > ilvl:
            del num_counters[lvl]

    def repl(match: re.Match[str]) -> str:
        lvl_ref = int(match.group(1)) - 1
        lvl_def = level_defs.get(
            lvl_ref,
            {"num_fmt": "decimal", "lvl_text": f"%{lvl_ref + 1}.", "start": 1},
        )
        if lvl_ref not in num_counters:
            num_counters[lvl_ref] = _as_int(str(lvl_def.get("start", 1)), 1)
        return _format_list_number(
            num_counters[lvl_ref], str(lvl_def.get("num_fmt", "decimal"))
        )

    marker = re.sub(r"%([1-9])", repl, lvl_text).strip()
    return f"{marker} " if marker else ""


def cell_text(
    tc,
    *,
    plain: bool = False,
    numbering_defs: dict[int, dict[int, dict[str, object]]] | None = None,
    counters: dict[int, dict[int, int]] | None = None,
):
    out = []
    ps = tc.findall(".//w:p", namespaces=NS)
    for pi, p in enumerate(ps):
        if pi > 0:
            out.append("\n")  # paragraph boundary
        if numbering_defs is not None and counters is not None:
            out.append(
                _paragraph_list_prefix(
                    p,
                    numbering_defs=numbering_defs,
                    counters=counters,
                )
            )

        # keep true document order inside the paragraph: runs + hyperlinks (which contain runs)
        for node in p:
            tag = etree.QName(node).localname
            if tag == "r":
                out.append(_run_to_text_plain(node) if plain else _run_to_text(node))
            elif tag == "hyperlink":
                for r in node.findall("w:r", namespaces=NS):
                    out.append(_run_to_text_plain(r) if plain else _run_to_text(r))
            # other paragraph children are usually bookmarks/proofErr/etc.
    return "".join(out)


def parse_docx_table(docx_path: Path) -> list[pd.DataFrame]:
    with ZipFile(docx_path) as z:
        xml = z.read("word/document.xml")
        numbering_defs = _load_numbering_definitions(z)

    root = etree.fromstring(xml)

    dfs = []
    for tbl in root.findall(".//w:tbl", namespaces=NS):
        rows = []
        counters: dict[int, dict[int, int]] = {}
        for tri, tr in enumerate(tbl.findall("./w:tr", namespaces=NS)):
            is_header = (tri == 0)
            row = []
            for tc in tr.findall("./w:tc", namespaces=NS):
                row.append(
                    cell_text(
                        tc,
                        plain=is_header,
                        numbering_defs=numbering_defs,
                        counters=counters,
                    )
                )
            rows.append(row)

        df = pd.DataFrame(rows)
        df.columns = df.iloc[0]          # header now plain (no **, _, ~, ^)
        
        # Strip and sanitize whitespaces
        df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.iloc[0]]
        
        df = df.iloc[1:].reset_index(drop=True)
        dfs.append(df)

    return dfs
