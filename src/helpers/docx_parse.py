import re
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W15 = "http://schemas.microsoft.com/office/word/2012/wordml"
NS = {"w": W, "w15": W15}


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


def _paragraph_to_text(
    p,
    *,
    plain: bool = False,
    numbering_defs: dict[int, dict[int, dict[str, object]]] | None = None,
    counters: dict[int, dict[int, int]] | None = None,
) -> str:
    out: list[str] = []
    if numbering_defs is not None and counters is not None:
        out.append(
            _paragraph_list_prefix(
                p,
                numbering_defs=numbering_defs,
                counters=counters,
            )
        )
    for node in p:
        tag = etree.QName(node).localname
        if tag == "r":
            out.append(_run_to_text_plain(node) if plain else _run_to_text(node))
        elif tag == "hyperlink":
            for r in node.findall("w:r", namespaces=NS):
                out.append(_run_to_text_plain(r) if plain else _run_to_text(r))
    return "".join(out)


def _collect_paragraph_texts(
    root,
    *,
    xpath: str,
    numbering_defs: dict[int, dict[int, dict[str, object]]],
) -> list[str]:
    texts: list[str] = []
    counters: dict[int, dict[int, int]] = {}
    for p in root.findall(xpath, namespaces=NS):
        txt = _paragraph_to_text(
            p,
            numbering_defs=numbering_defs,
            counters=counters,
        ).strip()
        if txt:
            texts.append(txt)
    return texts


def _collect_body_text_below_tables(
    root,
    *,
    numbering_defs: dict[int, dict[int, dict[str, object]]],
) -> list[str]:
    body = root.find("./w:body", namespaces=NS)
    if body is None:
        return []
    texts: list[str] = []
    counters: dict[int, dict[int, int]] = {}
    seen_table = False
    for child in body:
        tag = etree.QName(child).localname
        if tag == "tbl":
            seen_table = True
            continue
        if not seen_table or tag != "p":
            continue
        txt = _paragraph_to_text(
            child,
            numbering_defs=numbering_defs,
            counters=counters,
        ).strip()
        if txt:
            texts.append(txt)
    return texts


def _extract_comment_ids_from_node(node) -> set[str]:
    ids: set[str] = set()
    for marker_tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
        for marker in node.findall(f".//w:{marker_tag}", namespaces=NS):
            cid = marker.get(f"{{{W}}}id")
            if cid is not None:
                ids.add(str(cid))
    return ids


def _extract_table_comment_ids(root) -> tuple[list[list[set[str]]], list[set[str]], list[set[str]]]:
    body = root.find("./w:body", namespaces=NS)
    if body is None:
        return [], [], []

    row_ids_by_table: list[list[set[str]]] = []
    header_ids_by_table: list[set[str]] = []
    below_ids_by_table: list[set[str]] = []
    table_nodes = [child for child in body if etree.QName(child).localname == "tbl"]
    below_ids_by_table = [set() for _ in table_nodes]

    for tbl in table_nodes:
        tr_nodes = tbl.findall("./w:tr", namespaces=NS)
        row_ids: list[set[str]] = []
        for tr in tr_nodes:
            row_comment_ids = _extract_comment_ids_from_node(tr)
            row_ids.append(row_comment_ids)
        row_ids_by_table.append(row_ids[1:] if len(row_ids) > 1 else [])
        header_ids_by_table.append(row_ids[0] if row_ids else set())

    children = list(body)
    table_cursor = -1
    for child in children:
        tag = etree.QName(child).localname
        if tag == "tbl":
            table_cursor += 1
            continue
        if tag != "p" or table_cursor < 0 or table_cursor >= len(below_ids_by_table):
            continue
        below_ids_by_table[table_cursor].update(_extract_comment_ids_from_node(child))

    return row_ids_by_table, header_ids_by_table, below_ids_by_table


def _extract_comment_anchor_by_id(root) -> dict[str, str]:
    context_ranges: dict[str, list[tuple[str, int, int]]] = {}

    for p in root.findall(".//w:p", namespaces=NS):
        active_starts: dict[str, list[int]] = {}
        para_parts: list[str] = []
        para_ranges: list[tuple[str, int, int]] = []
        current_offset = 0

        for node in p:
            tag = etree.QName(node).localname
            if tag == "commentRangeStart":
                comment_id = node.get(f"{{{W}}}id")
                if comment_id:
                    cid = str(comment_id)
                    active_starts.setdefault(cid, []).append(current_offset)
                continue
            if tag == "commentRangeEnd":
                comment_id = node.get(f"{{{W}}}id")
                if comment_id:
                    cid = str(comment_id)
                    starts = active_starts.get(cid, [])
                    if starts:
                        start_offset = starts.pop()
                        para_ranges.append((cid, start_offset, current_offset))
                continue

            text = ""
            if tag == "r":
                text = _run_to_text_plain(node)
            elif tag == "hyperlink":
                text = "".join(_run_to_text_plain(r) for r in node.findall("w:r", namespaces=NS))
            if not text:
                continue
            para_parts.append(text)
            current_offset += len(text)

        para_text = re.sub(r"\s+", " ", "".join(para_parts)).strip()
        if not para_text:
            continue
        for cid, starts in active_starts.items():
            for start_offset in starts:
                para_ranges.append((cid, start_offset, current_offset))
        for cid, start_offset, end_offset in para_ranges:
            context_ranges.setdefault(cid, []).append((para_text, start_offset, end_offset))

    anchor_by_id: dict[str, str] = {}
    for comment_id, ranges in context_ranges.items():
        anchors: list[str] = []
        for para_text, start_offset, end_offset in ranges:
            start = max(0, min(start_offset, len(para_text)))
            end = max(start, min(end_offset, len(para_text)))
            selected = para_text[start:end].strip()
            selected = re.sub(r"\s+", " ", selected).strip()
            if selected:
                anchors.append(selected)
        if anchors:
            seen: set[str] = set()
            deduped: list[str] = []
            for anchor in anchors:
                if anchor in seen:
                    continue
                seen.add(anchor)
                deduped.append(anchor)
            anchor_by_id[comment_id] = " | ".join(deduped)
    return anchor_by_id


def _collect_comments_with_metadata(
    comments_root,
    *,
    numbering_defs: dict[int, dict[int, dict[str, object]]],
    comments_extended_root=None,
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]], list[str]]:
    para_parent_map: dict[str, str] = {}
    para_done_map: dict[str, str] = {}
    if comments_extended_root is not None:
        for comment_ex in comments_extended_root.findall(".//w15:commentEx", namespaces=NS):
            para_id = ""
            para_parent_id = ""
            done = ""
            for attr_key, attr_val in comment_ex.attrib.items():
                local = etree.QName(attr_key).localname
                if local == "paraId":
                    para_id = str(attr_val)
                elif local == "paraIdParent":
                    para_parent_id = str(attr_val)
                elif local == "done":
                    done = str(attr_val)
            if para_id and para_parent_id:
                para_parent_map[para_id] = para_parent_id
            if para_id and done:
                para_done_map[para_id] = done

    comments: list[dict[str, str]] = []
    for comment in comments_root.findall(".//w:comment", namespaces=NS):
        comment_id = comment.get(f"{{{W}}}id", "")
        comment_para_id = ""
        first_p = comment.find("./w:p", namespaces=NS)
        if first_p is not None:
            for attr_key, attr_val in first_p.attrib.items():
                if etree.QName(attr_key).localname == "paraId":
                    comment_para_id = str(attr_val)
                    break

        parent_id = ""
        for attr_key, attr_val in comment.attrib.items():
            if etree.QName(attr_key).localname == "parentId":
                parent_id = str(attr_val)
                break

        author = (comment.get(f"{{{W}}}author", "") or "").strip()
        initials = (comment.get(f"{{{W}}}initials", "") or "").strip()
        date = (comment.get(f"{{{W}}}date", "") or "").strip()
        text = "\n".join(
            _collect_paragraph_texts(
                comment,
                xpath="./w:p",
                numbering_defs=numbering_defs,
            )
        ).strip()
        if not text:
            continue

        comments.append(
            {
                "id": comment_id,
                "para_id": comment_para_id,
                "parent_id": parent_id,
                "author": author,
                "initials": initials,
                "date": date,
                "text": text,
                "done": para_done_map.get(comment_para_id, ""),
            }
        )

    def sort_key(comment_meta: dict[str, str]) -> tuple[float, str]:
        raw_date = comment_meta.get("date", "").strip()
        if raw_date:
            normalized = raw_date.replace("Z", "+00:00")
            try:
                return (datetime.fromisoformat(normalized).timestamp(), comment_meta["id"])
            except ValueError:
                pass
        return (float("inf"), comment_meta["id"])

    by_id = {item["id"]: item for item in comments if item.get("id")}
    by_para = {item["para_id"]: item for item in comments if item.get("para_id")}
    for item in comments:
        if item.get("parent_id"):
            continue
        para_id = item.get("para_id", "")
        if para_id and para_id in para_parent_map:
            parent_para = para_parent_map[para_id]
            parent_comment = by_para.get(parent_para)
            if parent_comment and parent_comment.get("id"):
                item["parent_id"] = str(parent_comment["id"])

    children: dict[str, list[dict[str, str]]] = {}
    roots: list[dict[str, str]] = []
    for item in comments:
        parent = item.get("parent_id", "").strip()
        if parent and parent in by_id:
            children.setdefault(parent, []).append(item)
        else:
            roots.append(item)

    for child_list in children.values():
        child_list.sort(key=sort_key)
    roots.sort(key=sort_key)

    root_ids = [item["id"] for item in roots if item.get("id")]
    return by_id, {k: [c["id"] for c in v if c.get("id")] for k, v in children.items()}, root_ids


def _render_comments_for_ids(
    *,
    selected_ids: set[str],
    by_id: dict[str, dict[str, str]],
    children_ids: dict[str, list[str]],
    root_ids: list[str],
    anchor_by_id: dict[str, str],
) -> list[str]:
    if not selected_ids:
        return []

    expanded_ids: set[str] = set()
    for cid in selected_ids:
        current = cid
        while current and current in by_id and current not in expanded_ids:
            expanded_ids.add(current)
            current = by_id[current].get("parent_id", "").strip()
    stack = list(expanded_ids)
    while stack:
        current = stack.pop()
        for child_id in children_ids.get(current, []):
            if child_id in by_id and child_id not in expanded_ids:
                expanded_ids.add(child_id)
                stack.append(child_id)

    lines: list[str] = []

    def render(comment_id: str, depth: int) -> None:
        meta = by_id.get(comment_id)
        if meta is None or comment_id not in expanded_ids:
            return
        author_display = (
            meta.get("author", "").strip() or meta.get("initials", "").strip() or "Comment"
        )
        date_display = meta.get("date", "").strip()
        status_bits: list[str] = []
        if date_display:
            status_bits.append(date_display)
        if meta.get("done", "").strip() == "1":
            status_bits.append("resolved")
        suffix = f" ({'; '.join(status_bits)})" if status_bits else ""
        indent = "  " * depth
        anchor = anchor_by_id.get(comment_id, "").strip() or "anchor unavailable"
        lines.append(
            f'{indent}- **{author_display}** commented on "{anchor}": '
            f"{meta.get('text', '')}{suffix}"
        )
        for child_id in children_ids.get(comment_id, []):
            render(child_id, depth + 1)

    roots_for_render: list[str] = []
    for cid in root_ids:
        if cid in expanded_ids:
            roots_for_render.append(cid)
    for cid in sorted(expanded_ids):
        if cid in roots_for_render:
            continue
        parent_id = by_id.get(cid, {}).get("parent_id", "").strip()
        if not parent_id or parent_id not in expanded_ids:
            roots_for_render.append(cid)

    for rid in roots_for_render:
        render(rid, 0)

    return lines


def parse_docx_tables_and_notes(docx_path: Path) -> tuple[list[pd.DataFrame], str, list[list[str]]]:
    with ZipFile(docx_path) as z:
        xml = z.read("word/document.xml")
        numbering_defs = _load_numbering_definitions(z)
        try:
            comments_xml = z.read("word/comments.xml")
        except KeyError:
            comments_xml = None
        try:
            comments_extended_xml = z.read("word/commentsExtended.xml")
        except KeyError:
            comments_extended_xml = None

    root = etree.fromstring(xml)

    row_ids_by_table, header_ids_by_table, below_ids_by_table = _extract_table_comment_ids(root)

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

    footnotes_chunks = _collect_body_text_below_tables(
        root,
        numbering_defs=numbering_defs,
    )

    comments_by_table_row: list[list[str]] = [[""] * len(df) for df in dfs]
    if comments_xml is not None:
        comments_root = etree.fromstring(comments_xml)
        comments_extended_root = (
            etree.fromstring(comments_extended_xml) if comments_extended_xml is not None else None
        )
        by_id, children_ids, root_ids = _collect_comments_with_metadata(
            comments_root,
            numbering_defs=numbering_defs,
            comments_extended_root=comments_extended_root,
        )
        anchor_by_id = _extract_comment_anchor_by_id(root)
        for table_idx, df in enumerate(dfs):
            table_row_comments: list[str] = []
            row_id_sets = row_ids_by_table[table_idx] if table_idx < len(row_ids_by_table) else []
            header_ids = (
                header_ids_by_table[table_idx] if table_idx < len(header_ids_by_table) else set()
            )
            below_ids = (
                below_ids_by_table[table_idx] if table_idx < len(below_ids_by_table) else set()
            )
            for row_idx in range(len(df)):
                row_ids = row_id_sets[row_idx] if row_idx < len(row_id_sets) else set()
                selected_ids = set(row_ids) | set(header_ids) | set(below_ids)
                rendered = _render_comments_for_ids(
                    selected_ids=selected_ids,
                    by_id=by_id,
                    children_ids=children_ids,
                    root_ids=root_ids,
                    anchor_by_id=anchor_by_id,
                )
                table_row_comments.append("\n".join(rendered))
            comments_by_table_row[table_idx] = table_row_comments

    return dfs, "\n".join(footnotes_chunks), comments_by_table_row


def parse_docx_table(docx_path: Path) -> list[pd.DataFrame]:
    tables, _, _ = parse_docx_tables_and_notes(docx_path)
    return tables
