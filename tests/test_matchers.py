from __future__ import annotations

import pandas as pd

from src._vars import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    HCR_LIST_LABEL,
    HCR_ROW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    RIGHT_NAME_COL,
)
from src.data_models import FragmentType, NameKey, OuterDict, RegisteredResource, ResourceGroup
from src.matchers import CsvDuckdbMatcher, DocxDuckdbMatcher, XlsxDuckdbMatcher


def _resource(name: str, fragment_type: FragmentType) -> RegisteredResource:
    return RegisteredResource(
        name=name,
        hash="abc123",
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=fragment_type,
        url=f"file:///tmp/{name}",
        verify_hash_on_init=False,
    )


def test_xlsx_matcher_appends_records() -> None:
    outer_dict = OuterDict.from_name_keys(
        [NameKey(first_name="Ada", last_name="Lovelace")]
    )
    population_df = pd.DataFrame(
        [
            {
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Lovelace",
                HCR_LIST_LABEL: "source.xlsx",
                HCR_ROW_LABEL: 10,
            }
        ]
    )
    resources = {"source.xlsx": _resource("source.xlsx", FragmentType.EXCEL_ROW)}
    matcher = XlsxDuckdbMatcher(outer_dict, resources)
    matcher.match(population_df)

    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data[HCR_ROW_LABEL] == 10


def test_csv_matcher_requires_duplicates() -> None:
    outer_dict = OuterDict.from_name_keys(
        [NameKey(first_name="Ada", last_name="Lovelace")]
    )
    population_df = pd.DataFrame(
        [
            {
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Lovelace",
                HCR_LIST_LABEL: "source.xlsx",
                HCR_ROW_LABEL: 10,
            }
        ]
    )
    xlsx_resources = {"source.xlsx": _resource("source.xlsx", FragmentType.EXCEL_ROW)}
    XlsxDuckdbMatcher(outer_dict, xlsx_resources).match(population_df)

    csv_df = pd.DataFrame(
        [
            {
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Lovelace",
                KTP_FILENAME_COL: "source.csv",
                CSV_ROW_INDEX_COL: 0,
                HCR_LIST_LABEL: "source.xlsx",
                HCR_ROW_LABEL: 10,
            }
        ]
    )
    csv_resources = {"source.csv": _resource("source.csv", FragmentType.CSV_ROW)}
    matcher = CsvDuckdbMatcher(outer_dict, csv_resources)
    matcher.match(csv_df)

    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    assert len(outer_dict.data[ada_key]) == 2


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
            {
                RIGHT_NAME_COL: "Unmatched Person",
                KTP_FILENAME_COL: "doc1.docx",
                DOCX_FRAGMENT_COL: "table0_row2",
            },
        ]
    )

    resources = {"doc1.docx": _resource("doc1.docx", FragmentType.DOCX_ROW)}
    matcher = DocxDuckdbMatcher(outer_dict, resources)
    matcher.match(docx_df)

    jane_key = NameKey(first_name="Jane", last_name="Doe").to_json_key()
    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()

    assert len(outer_dict.data[jane_key]) == 1
    assert outer_dict.data[jane_key][0].data[RIGHT_NAME_COL] == "Dr. Jane A. Doe"
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data[RIGHT_NAME_COL] == "Ada-Lovelace"
