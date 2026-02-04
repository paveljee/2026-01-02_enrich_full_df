from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.helpers.data_models import FragmentType, ResourceGroup
from src.helpers.docx_loader import load_docx_tables
from src.helpers.files import find_files_by_extension
from src.helpers.resources import register_resource
from src.helpers.vars import RIGHT_NAME_COL


def test_find_files_by_extension(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "a.docx").write_text("stub", encoding="utf-8")
    (tmp_path / "b.docx").write_text("stub", encoding="utf-8")
    (tmp_path / "c.csv").write_text("stub", encoding="utf-8")

    non_recursive = find_files_by_extension(tmp_path, "docx")
    assert {p.name for p in non_recursive} == {"b.docx"}

    recursive = find_files_by_extension(tmp_path, "docx", recursive=True)
    assert {p.name for p in recursive} == {"a.docx", "b.docx"}


def test_load_docx_tables_uses_parser(tmp_path: Path, monkeypatch) -> None:
    docx_path = tmp_path / "example.docx"
    docx_path.write_text("stub", encoding="utf-8")
    resource = register_resource(
        docx_path,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.DOCX_ROW,
    )

    def fake_parse_docx_table(_: Path) -> list[pd.DataFrame]:
        return [pd.DataFrame({RIGHT_NAME_COL: ["Jane Doe"], "extra": ["value"]})]

    monkeypatch.setattr("src.helpers.docx_loader.parse_docx_table", fake_parse_docx_table)

    df = load_docx_tables({resource.name: resource})
    assert RIGHT_NAME_COL in df.columns or "ktp.table_1_researcher_author" in df.columns
