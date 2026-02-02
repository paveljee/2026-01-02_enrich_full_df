from __future__ import annotations

import duckdb
import pandas as pd

from src import _vars
from src._vars import (
    DOCX_FRAGMENT_COL,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    KTP_FILENAME_COL,
    RIGHT_NAME_COL,
)
from src.data_models import FragmentType, NameKey, OuterDict, ResourceGroup
from src.hcr_xlsx.matcher import match_population
from src.manual_docx.matcher import match_docx
from src.utils.resources import register_resource


def test_xlsx_matcher_appends_records(tmp_path, monkeypatch) -> None:
    xlsx_path = tmp_path / "sample.xlsx"
    xlsx_path.write_text("stub", encoding="utf-8")
    resources = {
        xlsx_path.name: register_resource(
            xlsx_path,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        )
    }
    monkeypatch.setitem(
        _vars.HCR_XLSX_NAME_COLS,
        xlsx_path.name,
        ("hcr.first_name", "hcr.last_name"),
    )

    outer_dict = OuterDict.from_name_keys(
        [
            NameKey(first_name="Ada", last_name="Lovelace"),
            NameKey(first_name="Grace", last_name="Hopper"),
        ]
    )

    population_df = pd.DataFrame(
        [
            {
                "hcr.first_name": "Ada",
                "hcr.last_name": "Lovelace",
                HCR_FILENAME_COL: xlsx_path.name,
                HCR_ROW_COL: 10,
            },
            {
                "hcr.first_name": "Alan",
                "hcr.last_name": "Turing",
                HCR_FILENAME_COL: xlsx_path.name,
                HCR_ROW_COL: 11,
            },
        ]
    )

    conn = duckdb.connect()
    conn.register("population", population_df)
    conn.execute("CREATE OR REPLACE TABLE population AS SELECT * FROM population")
    match_population(conn, outer_dict, population_table="population", resources=resources)
    conn.close()

    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    grace_key = NameKey(first_name="Grace", last_name="Hopper").to_json_key()

    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data[HCR_ROW_COL] == 10
    assert outer_dict.data[ada_key][0].data[KTP_FILENAME_COL] == xlsx_path.name
    assert outer_dict.data[grace_key] == []


def test_docx_matcher_matches_cleaned_names(tmp_path) -> None:
    docx_path = tmp_path / "doc1.docx"
    docx_path.write_text("stub", encoding="utf-8")
    resources = {
        docx_path.name: register_resource(
            docx_path,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.DOCX_ROW,
        )
    }

    outer_dict = OuterDict.from_name_keys(
        [
            NameKey(first_name="Jane", last_name="Doe"),
            NameKey(first_name="Ada", last_name="Lovelace"),
        ]
    )
    docx_df = pd.DataFrame(
        [
            {
                RIGHT_NAME_COL: "Dr. Jane A. Doe",
                KTP_FILENAME_COL: docx_path.name,
                DOCX_FRAGMENT_COL: "table0_row0",
            },
            {
                RIGHT_NAME_COL: "Ada-Lovelace",
                KTP_FILENAME_COL: docx_path.name,
                DOCX_FRAGMENT_COL: "table0_row1",
            },
            {
                RIGHT_NAME_COL: "Unmatched Person",
                KTP_FILENAME_COL: docx_path.name,
                DOCX_FRAGMENT_COL: "table0_row2",
            },
        ]
    )

    conn = duckdb.connect()
    match_docx(conn, outer_dict, docx_df, resources, fragment_col=DOCX_FRAGMENT_COL)
    conn.close()

    jane_key = NameKey(first_name="Jane", last_name="Doe").to_json_key()
    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()

    assert len(outer_dict.data[jane_key]) == 1
    assert outer_dict.data[jane_key][0].data[RIGHT_NAME_COL] == "Dr. Jane A. Doe"
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data[RIGHT_NAME_COL] == "Ada-Lovelace"
