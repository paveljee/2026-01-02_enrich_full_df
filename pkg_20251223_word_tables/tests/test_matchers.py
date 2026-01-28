from __future__ import annotations

import pandas as pd

from ..src._vars import KTP_FILENAME_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL, RIGHT_NAME_COL
from ..src.data_models import NameKey, OuterDict
from ..src.matchers import CsvMatcher, DocxMatcher


def test_csv_matcher_appends_records() -> None:
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
                KTP_FILENAME_COL: "source.csv",
                "score": 10,
            },
            {
                KTP_FIRST_NAME_COL: "Alan",
                KTP_LAST_NAME_COL: "Turing",
                KTP_FILENAME_COL: "source.csv",
                "score": 99,
            },
        ]
    )

    matcher = CsvMatcher(outer_dict)
    matcher.match(csv_df)

    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    grace_key = NameKey(first_name="Grace", last_name="Hopper").to_json_key()

    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data["score"] == 10
    assert outer_dict.data[ada_key][0].data[KTP_FILENAME_COL] == "source.csv"
    assert outer_dict.data[grace_key] == []


def test_docx_matcher_matches_cleaned_names() -> None:
    outer_dict = OuterDict.from_name_keys(
        [
            NameKey(first_name="Jane", last_name="Doe"),
            NameKey(first_name="Ada", last_name="Lovelace"),
        ]
    )
    docx_df = pd.DataFrame(
        [
            {RIGHT_NAME_COL: "Dr. Jane A. Doe", KTP_FILENAME_COL: "doc1.docx"},
            {RIGHT_NAME_COL: "Ada-Lovelace", KTP_FILENAME_COL: "doc1.docx"},
            {RIGHT_NAME_COL: "Unmatched Person", KTP_FILENAME_COL: "doc1.docx"},
        ]
    )

    matcher = DocxMatcher(outer_dict)
    matcher.match(docx_df)

    jane_key = NameKey(first_name="Jane", last_name="Doe").to_json_key()
    ada_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()

    assert len(outer_dict.data[jane_key]) == 1
    assert outer_dict.data[jane_key][0].data[RIGHT_NAME_COL] == "Dr. Jane A. Doe"
    assert len(outer_dict.data[ada_key]) == 1
    assert outer_dict.data[ada_key][0].data[RIGHT_NAME_COL] == "Ada-Lovelace"
