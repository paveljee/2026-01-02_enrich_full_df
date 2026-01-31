from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from src._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from src.cards import build_cards, write_cards_zip
from src.data_models import InnerDict, NameKey, OuterDict
from src.io_utils import find_files_by_extension, validate_csv_headers
from src.outer_dict_utils import build_outer_dict_from_names


class DummyProcedure:
    dataset_id_field = "ktp.source_key"


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


def test_validate_csv_headers(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    mismatch = tmp_path / "mismatch.csv"

    pd.DataFrame([{"a": 1, "b": 2}]).to_csv(first, index=False)
    pd.DataFrame([{"a": 3, "b": 4}]).to_csv(second, index=False)
    pd.DataFrame([{"a": 5, "c": 6}]).to_csv(mismatch, index=False)

    assert validate_csv_headers([first, second]) is True
    assert validate_csv_headers([first, mismatch]) is False


def test_write_cards_zip(tmp_path: Path) -> None:
    name_key = NameKey(first_name="Jane", last_name="Doe")
    outer_dict = OuterDict.from_name_keys([name_key])
    inner = InnerDict.from_mapping({"field": "value"}, DummyProcedure())
    outer_dict.add_inner(name_key, inner)

    cards = build_cards(outer_dict)
    zip_path = write_cards_zip(
        cards,
        output_dir=tmp_path,
        output_format="txt",
        bundle_name="sample",
        reference_docx_path=Path("resources/pandoc-custom-reference.docx"),
    )

    assert zip_path.exists()
    with ZipFile(zip_path) as zipf:
        names = set(zipf.namelist())

    assert "Jane_Doe.txt" in names
