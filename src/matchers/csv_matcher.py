from __future__ import annotations

import duckdb
import pandas as pd

from .._vars import (
    CSV_ROW_INDEX_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    SOURCE_KEY_COL,
)
from ..data_models import InnerDict, OuterDict, RegisteredResource, SourceKey
from .utils import NAME_KEY_COL, build_name_key_frame


class CsvMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


def _values_equal(left: object, right: object) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    return left == right


class CsvDuckdbMatcher:
    def __init__(self, outer_dict: OuterDict, resources: dict[str, RegisteredResource]) -> None:
        self.outer_dict = outer_dict
        self.resources = resources
        self.procedure = CsvMatchProcedure()
        self._inner_lists = {
            key: outer_dict.ensure_inner_list_by_key(key)
            for key in outer_dict.data
        }

    def _is_duplicate_of_existing(self, name_key: str, record: dict[str, object]) -> bool:
        ignored_keys = {SOURCE_KEY_COL, KTP_FILENAME_COL, CSV_ROW_INDEX_COL}
        for existing in self._inner_lists[name_key]:
            existing_data = existing.data
            matches = True
            for key, value in record.items():
                if key in ignored_keys:
                    continue
                if key not in existing_data:
                    matches = False
                    break
                if not _values_equal(existing_data[key], value):
                    matches = False
                    break
            if matches:
                return True
        return False

    def match(self, csv_df: pd.DataFrame) -> None:
        if csv_df.empty:
            return
        name_keys = build_name_key_frame(self.outer_dict)
        if name_keys.empty:
            return

        conn = duckdb.connect()
        conn.register("csv_df", csv_df)
        conn.register("name_keys", name_keys)
        matched = conn.execute(
            f"""
            SELECT nk.{NAME_KEY_COL} AS name_key, c.*
            FROM csv_df c
            JOIN name_keys nk
              ON c."{KTP_FIRST_NAME_COL}" = nk."{KTP_FIRST_NAME_COL}"
             AND c."{KTP_LAST_NAME_COL}" = nk."{KTP_LAST_NAME_COL}"
            """
        ).df()
        conn.close()

        for record in matched.to_dict("records"):
            name_key = record.pop(NAME_KEY_COL)
            filename = record.get(KTP_FILENAME_COL)
            if filename is None:
                raise ValueError("CSV record missing source filename")
            resource = self.resources.get(filename)
            if resource is None:
                raise ValueError(f"Missing registered resource for filename '{filename}'")
            fragment = record.get(CSV_ROW_INDEX_COL)
            if fragment is None:
                raise ValueError("CSV record missing row index")
            record[SOURCE_KEY_COL] = SourceKey(
                resource=resource,
                fragment=str(fragment),
            ).to_string_key()
            if not self._is_duplicate_of_existing(name_key, record):
                raise ValueError(
                    "CSV record is not a duplicate of an existing XLSX-sourced inner dict"
                )
            inner = InnerDict.from_mapping(record, self.procedure)
            self._inner_lists[name_key].append(inner)
