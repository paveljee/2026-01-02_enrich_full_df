from __future__ import annotations

import duckdb
import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import register_frame
from ..helpers.models import NameKey, OuterDict
from ..helpers.schema import OUTERDICT_NAME_VIEW, OUTERDICT_STUB_TABLE, SAMPLES_WITH_NAMES_VIEW
from ..helpers.vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL


def run(context: PipelineContext) -> StepResult:
    conn: duckdb.DuckDBPyConnection = context.conn
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
            name_key,
            json_extract_string(name_key, '$.\"{KTP_FIRST_NAME_COL}\"') AS "{KTP_FIRST_NAME_COL}",
            json_extract_string(name_key, '$.\"{KTP_LAST_NAME_COL}\"') AS "{KTP_LAST_NAME_COL}"
        FROM {OUTERDICT_STUB_TABLE}
        """
    )

    return StepResult(
        step_id="build_outerdict",
        artifacts={"outer_dict": outer_dict},
        messages=[f"OuterDict keys: {len(name_keys)}"],
        diagnostics=[f"Unique name keys: {len(name_keys)}"],
    )
