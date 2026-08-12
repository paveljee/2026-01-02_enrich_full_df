from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable
from zipfile import ZipFile

import pandas as pd

from .data_models import OuterDict
from .vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_ORIG_COLNAME_COL,
    KTP_LAST_NAME_ORIG_COLNAME_COL,
)

MARKDOWN_CODE_DELIMITER = "`"
MARKDOWN_LITERAL_LABEL_MARKER = "_"


def _markdown_literal(value: str) -> str:
    if MARKDOWN_LITERAL_LABEL_MARKER not in value:
        return value
    return f"{MARKDOWN_CODE_DELIMITER}{value}{MARKDOWN_CODE_DELIMITER}"


def build_cards(
    outer_dict: OuterDict,
    *,
    total_draws: int,
    intro: str,
    excluded_cols: set[str],
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict[str, str]:
    cards: dict[str, str] = {}
    intro_prefix = intro if intro.endswith("\n\n") else f"{intro}\n\n"
    items = list(outer_dict.items())
    total_cards = len(items)
    for card_idx, (name_key, inner_dicts) in enumerate(items, start=1):
        draw_numbers = []
        for inner in inner_dicts:
            draw_number = inner.data.get(DRAW_LABEL)
            if draw_number is not None and not pd.isna(draw_number):
                draw_numbers.append(str(draw_number))
        draw_numbers = sorted(set(draw_numbers))
        if draw_numbers:
            draw_label = ", ".join(draw_numbers)
            header = (
                f"### Draw #{draw_label} of {total_draws}: "
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
        docx_filename = re.sub(
            r"\s+",
            "_",
            re.sub(r"[^A-Za-z0-9\s]+", "", minified_card),
        ).strip("_")

        for inner in inner_dicts:
            filename = inner.data.get(KTP_FILENAME_COL, "unknown")
            filename_label = _markdown_literal(KTP_FILENAME_COL)
            rendered_filename = _markdown_literal(str(filename))
            card += f"\n\n#### {filename_label}: {rendered_filename}\n"
            for col, val in inner.data.items():
                if col in excluded_cols or pd.isna(val):
                    continue
                rendered_col = _markdown_literal(col)
                if "\n" in str(val):
                    card += (
                        f"**{rendered_col}**:\n\n"
                        f"{str(val).replace('\n', '\n\n')}\n\n"
                    )
                else:
                    card += f"**{rendered_col}**: {str(val)}\n\n"
                # if want to render null values: ####
                # if col in excluded_cols:
                #     continue
                # render_val = "null" if pd.isna(val) else str(val)
                # if "\n" in render_val:
                #     card += f"**{col}**:\n\n{render_val.replace('\n', '\n\n')}\n\n"
                # else:
                #     card += f"**{col}**: {render_val}\n\n"
        cards[docx_filename] = intro_prefix + card
        if progress_callback is not None:
            progress_callback(card_idx, total_cards, docx_filename)
    return cards


def _render_docx(md_path: Path, docx_path: Path, reference_docx: Path) -> Path:
    subprocess.run(
        [
            "pandoc",
            str(md_path),
            "-o",
            str(docx_path),
            "--reference-doc",
            str(reference_docx),
        ],
        check=True,
    )
    return docx_path


def write_cards_zip(
    cards: dict[str, str],
    output_dir: Path,
    zip_name: str,
    *,
    output_format: str,
    reference_docx: Path,
    docx_workers: int | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / zip_name
    with tempfile.TemporaryDirectory() as tmpdir:
        if output_format == "txt":
            txt_paths = []
            total = len(cards)
            for idx, (filename, card) in enumerate(cards.items(), start=1):
                txt_path = Path(tmpdir) / f"{filename}.txt"
                txt_path.write_text(card, encoding="utf-8")
                txt_paths.append(txt_path)
                if progress_callback is not None:
                    progress_callback(idx, total, filename)
            with ZipFile(zip_path, "w") as zipf:
                for path in txt_paths:
                    zipf.write(path, arcname=path.name)
        elif output_format == "docx":
            tmp_ref_path = Path(tmpdir) / reference_docx.name
            shutil.copy(reference_docx, tmp_ref_path)
            md_docx_pairs: list[tuple[Path, Path]] = []
            for filename, card in cards.items():
                md_path = Path(tmpdir) / f"{filename}.md"
                docx_path = Path(tmpdir) / f"{filename}.docx"
                md_path.write_text(card, encoding="utf-8")
                md_docx_pairs.append((md_path, docx_path))

            max_workers = docx_workers or max(1, min(8, os.cpu_count() or 1))
            docx_paths: list[Path] = []
            total = len(md_docx_pairs)
            done = 0
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_render_docx, md_path, docx_path, tmp_ref_path)
                    for md_path, docx_path in md_docx_pairs
                ]
                for future in as_completed(futures):
                    rendered = future.result()
                    docx_paths.append(rendered)
                    done += 1
                    if progress_callback is not None:
                        progress_callback(done, total, rendered.stem)
            with ZipFile(zip_path, "w") as zipf:
                for path in docx_paths:
                    zipf.write(path, arcname=path.name)
        else:
            raise ValueError(f"Unsupported output format: {output_format}")
    return zip_path
