from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from src._vars import KTP_FILENAME_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from src.cards import build_cards_archive
from src.data_models import InnerDict, NameKey, OuterDict
from src.io_utils import find_files_by_extension, validate_csv_headers


def test_find_files_by_extension(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.docx").write_text("stub", encoding="utf-8")
    (tmp_path / "b.docx").write_text("stub", encoding="utf-8")
    (tmp_path / "c.csv").write_text("stub", encoding="utf-8")

    non_recursive = find_files_by_extension(tmp_path, "docx")
    assert {p.name for p in non_recursive} == {"b.docx"}

    recursive = find_files_by_extension(tmp_path, "docx", recursive=True)
    assert {p.name for p in recursive} == {"a.docx", "b.docx"}


def test_validate_csv_headers(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    mismatch = tmp_path / "mismatch.csv"

    pd.DataFrame([{"a": 1, "b": 2}]).to_csv(first, index=False)
    pd.DataFrame([{"a": 3, "b": 4}]).to_csv(second, index=False)
    pd.DataFrame([{"a": 5, "c": 6}]).to_csv(mismatch, index=False)

    assert validate_csv_headers([first, second]) is True
    assert validate_csv_headers([first, mismatch]) is False


def test_build_cards_archive_creates_zip(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    outer_dict = OuterDict.from_name_keys(
        [NameKey(first_name="Jane", last_name="Doe")]
    )
    inner = InnerDict.from_mapping(
        {KTP_FIRST_NAME_COL: "Jane", KTP_LAST_NAME_COL: "Doe", KTP_FILENAME_COL: "source.csv"},
        type("Procedure", (), {"dataset_id_field": "ktp.source_key"})(),
    )
    outer_dict.add_inner(NameKey(first_name="Jane", last_name="Doe"), inner)

    zip_path = build_cards_archive(
        outer_dict,
        output_dir=output_dir,
        output_format="txt",
        total_draws=310,
        reference_docx=Path("resources/pandoc-custom-reference.docx"),
        archive_stem="output",
    )
    assert zip_path.exists()

    with ZipFile(zip_path) as zipf:
        names = set(zipf.namelist())

    assert "Jane_Doe.txt" in names
