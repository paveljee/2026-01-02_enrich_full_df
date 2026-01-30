from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pandas as pd

import repl

from ..src._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL, RIGHT_NAME_COL
from ..src.data_models import NameKey


def test_build_outer_dict_from_names():
    names = pd.DataFrame(
        [
            {KTP_FIRST_NAME_COL: "Ada", KTP_LAST_NAME_COL: "Lovelace"},
            {KTP_FIRST_NAME_COL: "Grace", KTP_LAST_NAME_COL: "Hopper"},
        ]
    )
    outer_dict = repl.build_outer_dict_from_names(names)

    assert len(outer_dict.data) == 2
    keys = set(outer_dict.data)
    assert NameKey(first_name="Ada", last_name="Lovelace").to_json_key() in keys
    assert NameKey(first_name="Grace", last_name="Hopper").to_json_key() in keys


def test_find_files_by_extension(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.docx").write_text("stub", encoding="utf-8")
    (tmp_path / "b.docx").write_text("stub", encoding="utf-8")
    (tmp_path / "c.csv").write_text("stub", encoding="utf-8")

    non_recursive = repl.find_files_by_extension(tmp_path, "docx")
    assert {p.name for p in non_recursive} == {"b.docx"}

    recursive = repl.find_files_by_extension(tmp_path, "docx", recursive=True)
    assert {p.name for p in recursive} == {"a.docx", "b.docx"}


def test_validate_csv_headers(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    mismatch = tmp_path / "mismatch.csv"

    pd.DataFrame([{"a": 1, "b": 2}]).to_csv(first, index=False)
    pd.DataFrame([{"a": 3, "b": 4}]).to_csv(second, index=False)
    pd.DataFrame([{"a": 5, "c": 6}]).to_csv(mismatch, index=False)

    assert repl.validate_csv_headers([first, second]) is True
    assert repl.validate_csv_headers([first, mismatch]) is False


def test_process_documents_creates_zip(tmp_path: Path, monkeypatch) -> None:
    docx_dir = tmp_path / "docx"
    csv_dir = tmp_path / "csv"
    output_dir = tmp_path / "output"
    docx_dir.mkdir()
    csv_dir.mkdir()

    (docx_dir / "example.docx").write_text("stub", encoding="utf-8")
    pd.DataFrame(
        [
            {"hcr.first_name": "Jane", "hcr.last_name": "Doe"},
        ]
    ).to_csv(csv_dir / "sample.csv", index=False)

    def fake_parse_docx_table(_: Path) -> list[pd.DataFrame]:
        return [pd.DataFrame({RIGHT_NAME_COL: ["Jane Doe"], "extra": ["value"]})]

    monkeypatch.setattr(repl, "parse_docx_table", fake_parse_docx_table)

    repl.process_documents(docx_dir, csv_dir, False, output_dir, "txt")

    zip_path = output_dir / f"{csv_dir.name}_combined_cards.zip"
    assert zip_path.exists()

    with ZipFile(zip_path) as zipf:
        names = set(zipf.namelist())

    assert "Jane_Doe.txt" in names
