from __future__ import annotations

import duckdb
import pandas as pd

from .._vars import (
    HCR_LIST_LABEL,
    HCR_ROW_LABEL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    SOURCE_KEY_COL,
)
from ..data_models import InnerDict, OuterDict, RegisteredResource, SourceKey
from .utils import NAME_KEY_COL, build_name_key_frame


class XlsxMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


class XlsxDuckdbMatcher:
    def __init__(self, outer_dict: OuterDict, resources: dict[str, RegisteredResource]) -> None:
        self.outer_dict = outer_dict
        self.resources = resources
        self.procedure = XlsxMatchProcedure()
        self._inner_lists = {
            key: outer_dict.ensure_inner_list_by_key(key)
            for key in outer_dict.data
        }

    def match(self, population_df: pd.DataFrame) -> None:
        if population_df.empty:
            return
        name_keys = build_name_key_frame(self.outer_dict)
        if name_keys.empty:
            return

        conn = duckdb.connect()
        conn.register("population_df", population_df)
        conn.register("name_keys", name_keys)
        matched = conn.execute(
            f"""
            SELECT nk.{NAME_KEY_COL} AS name_key, p.*
            FROM population_df p
            JOIN name_keys nk
              ON p."{KTP_FIRST_NAME_COL}" = nk."{KTP_FIRST_NAME_COL}"
             AND p."{KTP_LAST_NAME_COL}" = nk."{KTP_LAST_NAME_COL}"
            """
        ).df()
        conn.close()

        for record in matched.to_dict("records"):
            name_key = record.pop(NAME_KEY_COL)
            filename = record.get(HCR_LIST_LABEL)
            if filename is None:
                raise ValueError("Population record missing source filename")
            resource = self.resources.get(filename)
            if resource is None:
                raise ValueError(f"Missing registered resource for filename '{filename}'")
            fragment = record.get(HCR_ROW_LABEL)
            if fragment is None:
                raise ValueError("Population record missing row identifier")
            record[SOURCE_KEY_COL] = SourceKey(
                resource=resource,
                fragment=str(fragment),
            ).to_string_key()
            inner = InnerDict.from_mapping(record, self.procedure)
            self._inner_lists[name_key].append(inner)
