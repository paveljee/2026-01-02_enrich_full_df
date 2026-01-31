from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

import pandas as pd

from src._vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_ORIG_COLNAME_COL,
    KTP_LAST_NAME_ORIG_COLNAME_COL,
    SOURCE_KEY_COL,
)
from src.data_models import OuterDict

TOTAL_DRAWS = 310

INTRODUCTION = """## Introduction
**Draw number** is the sequential order in which rows were sampled from HCR tables.

Name is displayed as **Last Name, First Name**.

Last modified (introduction): December 23, 2025

Date of report: {}
"""


def _sanitize_filename(value: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r"[^A-Za-z0-9\s]+", "", value)).strip("_")


def build_cards(outer_dict: OuterDict, *, excluded_cols: set[str] | None = None) -> dict[str, str]:
    if excluded_cols is None:
        excluded_cols = {KTP_FILENAME_COL, SOURCE_KEY_COL}

    cards: dict[str, str] = {}
    for name_key, inner_dicts in outer_dict.items():
        draw_numbers = []
        for inner in inner_dicts:
            draw_number = inner.data.get(DRAW_LABEL)
            if draw_number is not None and not pd.isna(draw_number):
                draw_numbers.append(str(draw_number))
        draw_numbers = sorted(set(draw_numbers))
        if draw_numbers:
            draw_label = ", ".join(draw_numbers)
            header = (
                f"### Draw #{draw_label} of {TOTAL_DRAWS}: "
                f"{name_key.last_name}, {name_key.first_name}\n"
            )
        else:
            draw_label = ""
            header = f"### {name_key.last_name}, {name_key.first_name}\n"

        fun_fact = ""
        for inner in inner_dicts:
            last_col = inner.data.get(KTP_LAST_NAME_ORIG_COLNAME_COL)
            first_col = inner.data.get(KTP_FIRST_NAME_ORIG_COLNAME_COL)
            if last_col and first_col:
                fun_fact = (
                    f"Fun fact: the last name came from `{last_col}` and the first name – "
                    f"from `{first_col}` in the originating HCR list."
                )
                break
        card = header + (fun_fact + "\n" if fun_fact else "")

        minified_card = (
            f"{draw_label}: {name_key.first_name} {name_key.last_name}"
            if draw_label
            else f"{name_key.first_name} {name_key.last_name}"
        )
        docx_filename = _sanitize_filename(minified_card)

        for inner in inner_dicts:
            filename = inner.data.get(KTP_FILENAME_COL, "unknown")
            card += f"\n\n#### {KTP_FILENAME_COL}: {filename}\n"
            for col, val in inner.data.items():
                if col in excluded_cols or pd.isna(val):
                    continue
                if "\n" in str(val):
                    card += f"**{col}**:\n\n{str(val).replace('\n','\n\n')}\n\n"
                else:
                    card += f"**{col}**: {str(val)}\n\n"
        cards[docx_filename] = card

    return cards


def write_cards_zip(
    cards: dict[str, str],
    *,
    output_dir: Path,
    output_format: str,
    bundle_name: str,
    reference_docx_path: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{bundle_name}_combined_cards.zip"

    today = datetime.now(ZoneInfo("America/Toronto")).strftime("%B %d, %Y")
    intro = INTRODUCTION.format(today) + "\n\n"

    if output_format == "txt":
        with tempfile.TemporaryDirectory() as tmpdir:
            txt_paths = []
            for filename, card in cards.items():
                txt_path = Path(tmpdir) / f"{filename}.txt"
                txt_path.write_text(intro + card, encoding="utf-8")
                txt_paths.append(txt_path)
            with ZipFile(zip_path, "w") as zipf:
                for path in txt_paths:
                    zipf.write(path, arcname=path.name)
        return zip_path

    if output_format == "docx":
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_ref_path = Path(tmpdir) / reference_docx_path.name
            shutil.copy(reference_docx_path, tmp_ref_path)
            docx_paths: list[Path] = []
            for filename, card in cards.items():
                md_path = Path(tmpdir) / f"{filename}.md"
                docx_path = Path(tmpdir) / f"{filename}.docx"
                md_path.write_text(intro + card, encoding="utf-8")
                subprocess.run(
                    [
                        "pandoc",
                        str(md_path),
                        "-o",
                        str(docx_path),
                        "--reference-doc",
                        str(tmp_ref_path),
                    ],
                    check=True,
                )
                docx_paths.append(docx_path)
            with ZipFile(zip_path, "w") as zipf:
                for path in docx_paths:
                    zipf.write(path, arcname=path.name)
        return zip_path

    raise ValueError(f"Unsupported output format: {output_format}")
