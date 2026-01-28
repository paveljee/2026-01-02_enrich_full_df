from __future__ import annotations

import pandas as pd

from .._vars import KTP_FILENAME_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from ..data_models import OuterDict
from .base import BaseMatcher, NAME_KEY_COL, build_name_key_frame


class CsvNameMatchProcedure:
    dataset_id_field = KTP_FILENAME_COL


class CsvMatcher(BaseMatcher):
    def __init__(self, outer_dict: OuterDict) -> None:
        super().__init__(outer_dict, CsvNameMatchProcedure())

    def match(self, csv_df: pd.DataFrame) -> None:
        name_keys = build_name_key_frame(self.outer_dict)
        if name_keys.empty:
            return
        matched = csv_df.merge(
            name_keys,
            on=[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL],
            how="inner",
            copy=False,
        )
        if matched.empty:
            return
        for key, group in matched.groupby(NAME_KEY_COL, sort=False):
            records = group.drop(columns=[NAME_KEY_COL]).to_dict("records")
            self._append_records(key, records)
