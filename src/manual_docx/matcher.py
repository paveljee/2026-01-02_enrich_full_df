from __future__ import annotations

import duckdb
import pandas as pd

from .._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL, RIGHT_NAME_COL
from ..data_models import OuterDict, RegisteredResource
from ..utils.duckdb import register_frame
from ..utils.name_keys import build_name_key_frame
from ..utils.records import append_records
from .loader import normalize_docx_column_name


class DocxMatchProcedure:
    dataset_id_field = "ktp.source_key"


def match_docx(
    conn: duckdb.DuckDBPyConnection,
    outer_dict: OuterDict,
    docx_df: pd.DataFrame,
    resources: dict[str, RegisteredResource],
    *,
    fragment_col: str,
) -> None:
    name_keys = build_name_key_frame(outer_dict)
    if name_keys.empty or docx_df.empty:
        return

    name_column = (
        RIGHT_NAME_COL
        if RIGHT_NAME_COL in docx_df.columns
        else normalize_docx_column_name(RIGHT_NAME_COL)
    )
    if name_column not in docx_df.columns:
        raise ValueError(
            f"Docx data does not contain expected name column '{RIGHT_NAME_COL}'."
        )

    register_frame(conn, "docx_rows", docx_df)
    register_frame(conn, "docx_name_keys", name_keys)

    matched = conn.execute(
        f"""
        WITH names AS (
            SELECT
                name_key,
                regexp_replace(lower("{KTP_FIRST_NAME_COL}"), '[^0-9a-z]+', '', 'g')
                    AS first_clean,
                regexp_replace(lower("{KTP_LAST_NAME_COL}"), '[^0-9a-z]+', '', 'g')
                    AS last_clean
            FROM docx_name_keys
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
            FROM docx_rows
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
    if matched.empty:
        return

    records = matched.to_dict("records")
    for record in records:
        record.pop("docx_clean", None)

    append_records(
        outer_dict,
        records,
        DocxMatchProcedure(),
        resources,
        name_key_field="name_key",
        fragment_field=fragment_col,
    )
