from __future__ import annotations

import duckdb
import pandas as pd

from src._vars import KTP_FILENAME_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL, SOURCE_KEY_COL
from src.data_models import (
    InnerDict,
    MatchingProcedure,
    NameKey,
    OuterDict,
    RegisteredResource,
    SourceKey,
)


class DocxDuckdbMatchProcedure:
    dataset_id_field = SOURCE_KEY_COL


def _build_name_key_frame(outer_dict: OuterDict) -> pd.DataFrame:
    rows = []
    for key in outer_dict.data:
        name_key = NameKey.from_json_key(key)
        rows.append(
            {
                "name_key": key,
                KTP_FIRST_NAME_COL: name_key.first_name,
                KTP_LAST_NAME_COL: name_key.last_name,
            }
        )
    return pd.DataFrame(rows)


def append_docx_matches(
    outer_dict: OuterDict,
    docx_df: pd.DataFrame,
    name_column: str,
    fragment_column: str,
    resources: dict[str, RegisteredResource],
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> None:
    name_keys = _build_name_key_frame(outer_dict)
    if name_keys.empty or docx_df.empty:
        return

    owns_conn = conn is None
    if conn is None:
        conn = duckdb.connect()

    conn.register("docx_df", docx_df)
    conn.register("name_keys_df", name_keys)

    matched = conn.execute(
        f"""
        WITH names AS (
            SELECT
                name_key,
                regexp_replace(lower("{KTP_FIRST_NAME_COL}"), '[^0-9a-z]+', '', 'g') AS first_clean,
                regexp_replace(lower("{KTP_LAST_NAME_COL}"), '[^0-9a-z]+', '', 'g') AS last_clean
            FROM name_keys_df
            WHERE "{KTP_FIRST_NAME_COL}" IS NOT NULL
              AND "{KTP_LAST_NAME_COL}" IS NOT NULL
              AND "{KTP_FIRST_NAME_COL}" <> ''
              AND "{KTP_LAST_NAME_COL}" <> ''
        ),
        docx AS (
            SELECT
                *,
                regexp_replace(
                    lower(COALESCE("{name_column}", '')),
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

    procedure: MatchingProcedure = DocxDuckdbMatchProcedure()
    for record in matched.to_dict("records"):
        name_key = record.pop("name_key")
        record.pop("docx_clean", None)
        filename = record.get(KTP_FILENAME_COL)
        resource = resources.get(filename)
        if resource is None:
            raise ValueError(f"Missing registered resource for filename '{filename}'")
        fragment = record.get(fragment_column)
        record[SOURCE_KEY_COL] = SourceKey(
            resource=resource,
            fragment=str(fragment),
        ).to_string_key()
        inner = InnerDict.from_mapping(record, procedure)
        outer_dict.add_inner_by_key(name_key, inner)

    if owns_conn:
        conn.close()
