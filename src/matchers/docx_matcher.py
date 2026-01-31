from __future__ import annotations

import re

import duckdb
import pandas as pd

from .._vars import (
    DOCX_FRAGMENT_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    RIGHT_NAME_COL,
    SOURCE_KEY_COL,
)
from ..data_models import InnerDict, OuterDict, RegisteredResource, SourceKey
from .utils import NAME_KEY_COL, build_name_key_frame


class DocxMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


def normalize_docx_column_name(column: str) -> str:
    if re.match(r"^[\w_]+\.", str(column)):
        return str(column)
    normalized = re.sub(r"[^\w\s]", "_", str(column).lower())
    normalized = re.sub(r"\s", "_", normalized)
    normalized = f"ktp.table_1_{normalized}"
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def resolve_docx_name_column(docx_df: pd.DataFrame) -> str:
    if RIGHT_NAME_COL in docx_df.columns:
        return RIGHT_NAME_COL
    normalized = normalize_docx_column_name(RIGHT_NAME_COL)
    if normalized in docx_df.columns:
        return normalized
    raise ValueError(
        f"Docx data does not contain expected name column '{RIGHT_NAME_COL}' "
        f"or normalized '{normalized}'."
    )


class DocxDuckdbMatcher:
    def __init__(self, outer_dict: OuterDict, resources: dict[str, RegisteredResource]) -> None:
        self.outer_dict = outer_dict
        self.resources = resources
        self.procedure = DocxMatchProcedure()
        self._inner_lists = {
            key: outer_dict.ensure_inner_list_by_key(key)
            for key in outer_dict.data
        }

    def match(self, docx_df: pd.DataFrame) -> None:
        if docx_df.empty:
            return
        name_keys = build_name_key_frame(self.outer_dict)
        if name_keys.empty:
            return

        docx_name_column = resolve_docx_name_column(docx_df)

        conn = duckdb.connect()
        conn.register("docx_df", docx_df)
        conn.register("name_keys", name_keys)
        matched = conn.execute(
            f"""
            WITH names AS (
                SELECT
                    {NAME_KEY_COL} AS name_key,
                    "{KTP_FIRST_NAME_COL}" AS first_name,
                    "{KTP_LAST_NAME_COL}" AS last_name,
                    regexp_replace(lower("{KTP_FIRST_NAME_COL}"), '[^0-9a-z]+', '', 'g')
                        AS first_clean,
                    regexp_replace(lower("{KTP_LAST_NAME_COL}"), '[^0-9a-z]+', '', 'g')
                        AS last_clean
                FROM name_keys
                WHERE "{KTP_FIRST_NAME_COL}" IS NOT NULL
                  AND "{KTP_LAST_NAME_COL}" IS NOT NULL
                  AND "{KTP_FIRST_NAME_COL}" <> ''
                  AND "{KTP_LAST_NAME_COL}" <> ''
            ),
            docx AS (
                SELECT
                    *,
                    regexp_replace(
                        lower(COALESCE("{docx_name_column}", '')),
                        '[^0-9a-z]+',
                        '',
                        'g'
                    ) AS docx_clean
                FROM docx_df
            )
            SELECT n.name_key, d.*
            FROM names n
            CROSS JOIN docx d
            WHERE n.first_clean <> ''
              AND n.last_clean <> ''
              AND d.docx_clean <> ''
              AND POSITION(n.first_clean IN d.docx_clean) > 0
              AND POSITION(n.last_clean IN d.docx_clean) > 0
            """
        ).df()
        conn.close()

        for record in matched.to_dict("records"):
            name_key = record.pop("name_key")
            record.pop("docx_clean", None)
            filename = record.get(KTP_FILENAME_COL)
            if filename is None:
                raise ValueError("DOCX record missing source filename")
            resource = self.resources.get(filename)
            if resource is None:
                raise ValueError(f"Missing registered resource for filename '{filename}'")
            fragment = record.get(DOCX_FRAGMENT_COL)
            if fragment is None:
                raise ValueError("DOCX record missing fragment identifier")
            record[SOURCE_KEY_COL] = SourceKey(
                resource=resource,
                fragment=str(fragment),
            ).to_string_key()
            inner = InnerDict.from_mapping(record, self.procedure)
            self._inner_lists[name_key].append(inner)
