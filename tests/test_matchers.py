from __future__ import annotations

import pandas as pd

from src._vars import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    HCR_FILENAME_COL,
    HCR_ROW_NUMBER_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    RIGHT_NAME_COL,
)
from src.data_models import FragmentType, NameKey, OuterDict, RegisteredResource, ResourceGroup
from src.matchers.csv_matcher import append_csv_matches
from src.matchers.docx_matcher import append_docx_matches
from src.matchers.xlsx_matcher import append_population_matches


class DummyProcedure:
    dataset_id_field = "ktp.source_key"


def _resource(name: str, fragment_type: FragmentType) -> RegisteredResource:
    return RegisteredResource(
        name=name,
        hash="hash",
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=fragment_type,
        url=f"file:///tmp/{name}",
        verify_hash_on_init=False,
    )


def test_xlsx_matcher_appends_records() -> None:
    outer_dict = OuterDict.from_name_keys(
        [
            NameKey(first_name="Ada", last_name="Lovelace"),
            NameKey(first_name="Grace", last_name="Hopper"),
        ]
    )
    population_df = pd.DataFrame(
        [
            {
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Lovelace",
                HCR_FILENAME_COL: "source.xlsx",
                HCR_ROW_NUMBER_COL: 10,
                "score": 10,
            },
        ]
    )
    resources = {"source.xlsx": _resource("source.xlsx", FragmentType.EXCEL_ROW)}

    append_population_matches(outer_dict, population_df, resources)

    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data["score"] == 10


def test_csv_matcher_appends_records() -> None:
    outer_dict = OuterDict.from_name_keys(
        [
            NameKey(first_name="Ada", last_name="Lovelace"),
        ]
    )
    population_df = pd.DataFrame(
        [
            {
                HCR_FILENAME_COL: "source.xlsx",
                HCR_ROW_NUMBER_COL: 10,
            }
        ]
    )
    csv_df = pd.DataFrame(
        [
            {
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Lovelace",
                HCR_FILENAME_COL: "source.xlsx",
                HCR_ROW_NUMBER_COL: 10,
                KTP_FILENAME_COL: "source.csv",
                CSV_ROW_INDEX_COL: 0,
                "score": 10,
            }
        ]
    )
    resources = {"source.csv": _resource("source.csv", FragmentType.CSV_ROW)}

    append_csv_matches(outer_dict, csv_df, population_df, resources)

    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data["score"] == 10


def test_docx_matcher_matches_cleaned_names() -> None:
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
                KTP_FILENAME_COL: "doc1.docx",
                DOCX_FRAGMENT_COL: "table0_row0",
            },
            {
                RIGHT_NAME_COL: "Ada-Lovelace",
                KTP_FILENAME_COL: "doc1.docx",
                DOCX_FRAGMENT_COL: "table0_row1",
            },
        ]
    )
    resources = {"doc1.docx": _resource("doc1.docx", FragmentType.DOCX_ROW)}

    append_docx_matches(outer_dict, docx_df, RIGHT_NAME_COL, DOCX_FRAGMENT_COL, resources)

    jane_key = NameKey(first_name="Jane", last_name="Doe").to_json_key()
    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()

    assert len(outer_dict.data[jane_key]) == 1
    assert outer_dict.data[jane_key][0].data[RIGHT_NAME_COL] == "Dr. Jane A. Doe"
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data[RIGHT_NAME_COL] == "Ada-Lovelace"
