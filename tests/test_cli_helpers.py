from __future__ import annotations

from pathlib import Path

import pandas as pd

from src._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL, RIGHT_NAME_COL
from src.data_models import FragmentType, NameKey, ResourceGroup
from src.manual_docx.loader import load_docx_tables
from src.utils.files import find_files_by_extension
from src.utils.name_keys import build_outer_dict_from_names
from src.utils.resources import register_resource


def test_build_outer_dict_from_names():
    names = pd.DataFrame(
        [
            {KTP_FIRST_NAME_COL: "Ada", KTP_LAST_NAME_COL: "Lovelace"},
            {KTP_FIRST_NAME_COL: "Grace", KTP_LAST_NAME_COL: "Hopper"},
        ]
    )
    outer_dict = build_outer_dict_from_names(names)

    assert len(outer_dict.data) == 2
    keys = set(outer_dict.data)
    assert NameKey(first_name="Ada", last_name="Lovelace").to_json_key() in keys
    assert NameKey(first_name="Grace", last_name="Hopper").to_json_key() in keys


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

    monkeypatch.setattr("src.manual_docx.loader.parse_docx_table", fake_parse_docx_table)

    df = load_docx_tables({resource.name: resource})
    assert RIGHT_NAME_COL in df.columns or "ktp.table_1_researcher_author" in df.columns
