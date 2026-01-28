from __future__ import annotations

from typing import Iterable, Mapping, Protocol

import pandas as pd

from .._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from ..data_models import InnerDict, MatchingProcedure, NameKey, OuterDict

NAME_KEY_COL = "_name_key"


class Matcher(Protocol):
    outer_dict: OuterDict
    procedure: MatchingProcedure

    def match(self, df: pd.DataFrame) -> None:
        """Append matching rows from the dataset to the outer dict."""


class BaseMatcher:
    def __init__(self, outer_dict: OuterDict, procedure: MatchingProcedure) -> None:
        self.outer_dict = outer_dict
        self.procedure = procedure
        self._inner_lists = {
            key: outer_dict.ensure_inner_list_by_key(key)
            for key in outer_dict.data
        }

    def _append_records(self, key: str, records: Iterable[Mapping[str, object]]) -> None:
        inner_list = self._inner_lists[key]
        inner_list.extend(
            [
                InnerDict.from_mapping(record, self.procedure)
                for record in records
            ]
        )


def build_name_key_frame(outer_dict: OuterDict) -> pd.DataFrame:
    rows = []
    for key in outer_dict.data:
        name_key = NameKey.from_json_key(key)
        rows.append(
            {
                NAME_KEY_COL: key,
                KTP_FIRST_NAME_COL: name_key.first_name,
                KTP_LAST_NAME_COL: name_key.last_name,
            }
        )
    return pd.DataFrame(rows, columns=[NAME_KEY_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL])
