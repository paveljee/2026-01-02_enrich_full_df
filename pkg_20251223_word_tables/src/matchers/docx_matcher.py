from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .._vars import (
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    RIGHT_NAME_COL,
)
from ..data_models import OuterDict
from .base import NAME_KEY_COL, BaseMatcher, build_name_key_frame

NON_ALNUM_ANYWHERE = re.compile(r"[^0-9A-Za-z]+")


class DocxNameMatchProcedure:
    dataset_id_field = KTP_FILENAME_COL


def _clean_series(series: pd.Series) -> pd.Series:
    series_str = series.astype("string")
    return (
        series_str.str.replace(NON_ALNUM_ANYWHERE, "", regex=True)
        .str.casefold()
    )


def _clean_token(value: str) -> str:
    return NON_ALNUM_ANYWHERE.sub("", str(value)).casefold()


class DocxMatcher(BaseMatcher):
    def __init__(self, outer_dict: OuterDict) -> None:
        super().__init__(outer_dict, DocxNameMatchProcedure())

    def match(self, docx_df: pd.DataFrame) -> None:
        if docx_df.empty:
            return
        name_keys = build_name_key_frame(self.outer_dict)
        if name_keys.empty:
            return
        name_keys["_first_clean"] = name_keys[KTP_FIRST_NAME_COL].map(_clean_token)
        name_keys["_last_clean"] = name_keys[KTP_LAST_NAME_COL].map(_clean_token)
        name_keys = name_keys[
            (name_keys["_first_clean"] != "") & (name_keys["_last_clean"] != "")
        ]
        if name_keys.empty:
            return

        docx_columns = list(docx_df.columns)
        docx_match_df = docx_df.copy()
        docx_match_df["_docx_clean"] = _clean_series(docx_df[RIGHT_NAME_COL])
        docx_match_df["_cross"] = 1
        name_keys["_cross"] = 1

        cross = docx_match_df.merge(
            name_keys,
            on="_cross",
            how="inner",
            suffixes=("", "_key"),
        )
        docx_values = cross["_docx_clean"].to_numpy(dtype=str)
        first_values = cross["_first_clean"].to_numpy(dtype=str)
        last_values = cross["_last_clean"].to_numpy(dtype=str)
        mask = (np.char.find(docx_values, first_values) >= 0) & (
            np.char.find(docx_values, last_values) >= 0
        )
        matched = cross.loc[mask]
        if matched.empty:
            return
        for key, group in matched.groupby(NAME_KEY_COL, sort=False):
            records = group[docx_columns].to_dict("records")
            self._append_records(key, records)
