from __future__ import annotations

import json

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import NameKey, OuterDict
from ..helpers.duckdb_utils import register_frame
from ..helpers.schema import (
    OUTERDICT_EXCLUDED_NAME_VIEW,
    OUTERDICT_EXCLUDED_STUB_TABLE,
    OUTERDICT_NAME_VIEW,
    OUTERDICT_STUB_TABLE,
    SAMPLES_WITH_NAMES_VIEW,
)
from ..helpers.vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_LAST_NAME_COL,
    KTP_SOURCE_KEY_COL,
    STEP_BUILD_OUTERDICT,
    STEP_BUILD_OUTERDICT_EXCLUDED_LOG_MAX_ROWS,
)


def run(context: PipelineContext) -> StepResult:
    conn: duckdb.DuckDBPyConnection = context.conn

    def log(msg: str) -> None:
        if context.log:
            context.log(msg, "cyan")

    def _normalize_name_part(value: object) -> str | None:
        if pd.isna(value):
            return None
        return str(value)

    def _name_key_json(first: object, last: object) -> str:
        payload = {
            KTP_FIRST_NAME_COL: _normalize_name_part(first),
            KTP_LAST_NAME_COL: _normalize_name_part(last),
        }
        return json.dumps(payload, sort_keys=True)

    excluded_rows_df = conn.execute(
        f"""
        SELECT
            "{KTP_FILENAME_COL}" AS "{KTP_FILENAME_COL}",
            "{KTP_FRAGMENT_COL}" AS "{KTP_FRAGMENT_COL}",
            CAST("{DRAW_LABEL}" AS VARCHAR) AS "{DRAW_LABEL}",
            "{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
            "{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}"
        FROM {SAMPLES_WITH_NAMES_VIEW}
        WHERE "{KTP_FIRST_NAME_COL}" IS NULL
           OR "{KTP_LAST_NAME_COL}" IS NULL
           OR "{KTP_FIRST_NAME_COL}" = ''
           OR "{KTP_LAST_NAME_COL}" = ''
        ORDER BY
            CASE
                WHEN starts_with(CAST("{DRAW_LABEL}" AS VARCHAR), 'pilot.') THEN 0
                WHEN TRY_CAST("{DRAW_LABEL}" AS BIGINT) IS NOT NULL THEN 1
                ELSE 2
            END,
            COALESCE(
                CASE
                    WHEN starts_with(CAST("{DRAW_LABEL}" AS VARCHAR), 'pilot.')
                        THEN TRY_CAST(split_part(CAST("{DRAW_LABEL}" AS VARCHAR), '.', 2) AS BIGINT)
                    WHEN TRY_CAST("{DRAW_LABEL}" AS BIGINT) IS NOT NULL
                        THEN CAST("{DRAW_LABEL}" AS BIGINT)
                    ELSE NULL
                END,
                999999999
            ),
            CAST("{DRAW_LABEL}" AS VARCHAR),
            "{KTP_FILENAME_COL}",
            "{KTP_FRAGMENT_COL}"
        """
    ).df()
    excluded_name_rows = len(excluded_rows_df)
    excluded_name_pairs = (
        len(excluded_rows_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]].drop_duplicates())
        if excluded_name_rows
        else 0
    )
    excluded_pairs_df = (
        excluded_rows_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]]
        .drop_duplicates()
        .reset_index(drop=True)
        if excluded_name_rows
        else pd.DataFrame(columns=[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL])
    )
    if excluded_name_rows:
        log(
            "Exclude null/empty names before OuterDict key build: "
            f"{excluded_name_rows} row(s), {excluded_name_pairs} distinct name pair(s)."
        )

        def _fmt_name_part(value: object) -> str:
            if pd.isna(value):
                return "<NULL>"
            if value == "":
                return "''"
            return str(value)

        max_logged_rows = STEP_BUILD_OUTERDICT_EXCLUDED_LOG_MAX_ROWS
        for row in excluded_rows_df.head(max_logged_rows).itertuples(index=False):
            row_map = dict(zip(excluded_rows_df.columns, row, strict=True))
            log(
                "Excluded name row "
                f"[draw={row_map[DRAW_LABEL]}] "
                f"{row_map[KTP_FILENAME_COL]}#{row_map[KTP_FRAGMENT_COL]}: "
                f"first={_fmt_name_part(row_map[KTP_FIRST_NAME_COL])}, "
                f"last={_fmt_name_part(row_map[KTP_LAST_NAME_COL])}"
            )
        if excluded_name_rows > max_logged_rows:
            log(f"...and {excluded_name_rows - max_logged_rows} more excluded row(s).")

    excluded_stub_df = pd.DataFrame(
        {
            "name_key": [
                _name_key_json(first, last)
                for first, last in (
                    excluded_pairs_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]].itertuples(
                        index=False, name=None
                    )
                )
            ],
            "innerdicts": ["" for _ in range(len(excluded_pairs_df))],
        }
    )
    register_frame(conn, "outerdict_excluded_stub_frame", excluded_stub_df)
    conn.execute(
        "CREATE OR REPLACE TABLE "
        f"{OUTERDICT_EXCLUDED_STUB_TABLE} AS "
        "SELECT * FROM outerdict_excluded_stub_frame"
    )
    conn.execute("DROP TABLE IF EXISTS outerdict_excluded_stub_frame")
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {OUTERDICT_EXCLUDED_NAME_VIEW} AS
        SELECT
            name_key AS "{KTP_SOURCE_KEY_COL}",
            json_extract_string(name_key, '$.\"{KTP_FIRST_NAME_COL}\"') AS "{KTP_FIRST_NAME_COL}",
            json_extract_string(name_key, '$.\"{KTP_LAST_NAME_COL}\"') AS "{KTP_LAST_NAME_COL}"
        FROM {OUTERDICT_EXCLUDED_STUB_TABLE}
        """
    )
    if excluded_name_pairs:
        log(
            "Archive excluded-name OuterDict stub: "
            f"{excluded_name_pairs} key(s) in "
            f"{OUTERDICT_EXCLUDED_STUB_TABLE} / {OUTERDICT_EXCLUDED_NAME_VIEW}."
        )

    names_df = conn.execute(
        f"""
        SELECT DISTINCT "{KTP_FIRST_NAME_COL}", "{KTP_LAST_NAME_COL}"
        FROM {SAMPLES_WITH_NAMES_VIEW}
        """
    ).df()
    names_df = names_df.dropna(subset=[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL])
    names_df = names_df[(names_df[KTP_FIRST_NAME_COL] != "") & (names_df[KTP_LAST_NAME_COL] != "")]
    name_keys = [
        NameKey(first_name=first, last_name=last)
        for first, last in names_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]].itertuples(
            index=False, name=None
        )
    ]
    outer_dict = OuterDict.from_name_keys(name_keys)
    context.outer_dict = outer_dict
    outer_dict_excluded = OuterDict(
        data={name_key: [] for name_key in excluded_stub_df["name_key"].astype(str).tolist()}
    )

    stub_df = pd.DataFrame(
        {
            "name_key": [nk.to_json_key() for nk in name_keys],
            "innerdicts": ["" for _ in name_keys],
        }
    )
    register_frame(conn, "outerdict_stub_frame", stub_df)
    conn.execute(
        f"CREATE OR REPLACE TABLE {OUTERDICT_STUB_TABLE} AS SELECT * FROM outerdict_stub_frame"
    )
    conn.execute("DROP TABLE IF EXISTS outerdict_stub_frame")
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {OUTERDICT_NAME_VIEW} AS
        SELECT
            name_key AS "{KTP_SOURCE_KEY_COL}",
            json_extract_string(name_key, '$.\"{KTP_FIRST_NAME_COL}\"') AS "{KTP_FIRST_NAME_COL}",
            json_extract_string(name_key, '$.\"{KTP_LAST_NAME_COL}\"') AS "{KTP_LAST_NAME_COL}"
        FROM {OUTERDICT_STUB_TABLE}
        """
    )

    return StepResult(
        step_id=STEP_BUILD_OUTERDICT,
        artifacts={"outer_dict": outer_dict, "outer_dict_excluded": outer_dict_excluded},
        messages=[f"OuterDict keys: {len(name_keys)}"],
        diagnostics=[
            f"Unique name keys: {len(name_keys)}",
            f"Excluded null/empty-name rows: {excluded_name_rows}",
            f"Excluded null/empty-name distinct pairs: {excluded_name_pairs}",
        ],
    )
