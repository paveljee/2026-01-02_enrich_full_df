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


def cell_text(tc, *, plain=False):
    out = []
    ps = tc.findall(".//w:p", namespaces=NS)
    for pi, p in enumerate(ps):
        if pi > 0:
            out.append("\n")  # paragraph boundary

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

    root = etree.fromstring(xml)

    dfs = []
    for tbl in root.findall(".//w:tbl", namespaces=NS):
        rows = []
        for tri, tr in enumerate(tbl.findall("./w:tr", namespaces=NS)):
            is_header = (tri == 0)
            row = []
            for tc in tr.findall("./w:tc", namespaces=NS):
                row.append(cell_text(tc, plain=is_header))
            rows.append(row)

        df = pd.DataFrame(rows)
        df.columns = df.iloc[0]          # header now plain (no **, _, ~, ^)
        
        # Strip and sanitize whitespaces
        df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.iloc[0]]
        
        df = df.iloc[1:].reset_index(drop=True)
        dfs.append(df)

    return dfs
