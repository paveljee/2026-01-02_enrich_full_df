from __future__ import annotations

import duckdb
import pandas as pd

from src._vars import KTP_FILENAME_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL, RIGHT_NAME_COL
from src.data_models import FragmentType, NameKey, OuterDict, ResourceGroup
from src.io_utils import CSV_ROW_INDEX_COL, DOCX_FRAGMENT_COL
from src.matchers import match_csv_df, match_docx_df
from src.resources_utils import register_resource


def test_csv_matcher_appends_records(tmp_path) -> None:
    csv_path = tmp_path / "source.csv"
    csv_path.write_text("stub", encoding="utf-8")
    resources = {
        csv_path.name: register_resource(
            csv_path,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.CSV_ROW,
        )
    }

    outer_dict = OuterDict.from_name_keys(
        [
            NameKey(first_name="Ada", last_name="Lovelace"),
            NameKey(first_name="Grace", last_name="Hopper"),
        ]
    )
    csv_df = pd.DataFrame(
        [
            {
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Lovelace",
                KTP_FILENAME_COL: csv_path.name,
                CSV_ROW_INDEX_COL: 0,
                "score": 10,
            },
        ]
    )
    population_df = csv_df.copy()

    conn = duckdb.connect()
    match_csv_df(conn, outer_dict, csv_df, population_df, resources)
    conn.close()

    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    grace_key = NameKey(first_name="Grace", last_name="Hopper").to_json_key()

    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data["score"] == 10
    assert outer_dict.data[ada_key][0].data[KTP_FILENAME_COL] == csv_path.name
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
    match_docx_df(conn, outer_dict, docx_df, resources)
    conn.close()

    jane_key = NameKey(first_name="Jane", last_name="Doe").to_json_key()
    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()

    assert len(outer_dict.data[jane_key]) == 1
    assert outer_dict.data[jane_key][0].data[RIGHT_NAME_COL] == "Dr. Jane A. Doe"
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data[RIGHT_NAME_COL] == "Ada-Lovelace"
