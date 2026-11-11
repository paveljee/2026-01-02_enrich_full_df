from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import duckdb
import pytest

from src.helpers.context import PipelineContext
from src.helpers.data_models import NameKey
from src.helpers.schema import OUTERDICT_EXCLUDED_STUB_TABLE, SAMPLES_WITH_NAMES_VIEW
from src.steps import step_03_infer_names, step_06_build_outerdict_stub


def test_inferred_names_trim_edges_before_namekey_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        step_03_infer_names,
        "HCR_XLSX_NAME_COLS",
        {"names.xlsx": ("first", "last")},
    )
    conn = duckdb.connect()
    try:
        conn.execute(
            'CREATE TABLE population ('
            '"ktp.population_index" INTEGER, "ktp.hcr_filename" VARCHAR, '
            '"first" VARCHAR, "last" VARCHAR)'
        )
        conn.executemany(
            "INSERT INTO population VALUES (?, ?, ?, ?)",
            [
                (1, "names.xlsx", " JinRong ", " Wang "),
                (2, "names.xlsx", "JinRong", "Wang"),
                (3, "names.xlsx", " \t ", "Wang"),
                (4, "names.xlsx", None, "Wang"),
                (5, "names.xlsx", "Hakon H.", "Hakonarson"),
                (6, "names.xlsx", "Hakon H", "Hakonarson"),
                (7, "names.xlsx", "Gaoquan ", "Shi"),
                (8, "names.xlsx", "Gaoquan", "Shi"),
            ],
        )
        context = cast(
            PipelineContext,
            SimpleNamespace(
                conn=conn,
                resources=SimpleNamespace(xlsx_resources={}),
                config=SimpleNamespace(match_rule_version=SimpleNamespace(ssn_name=2)),
                log=None,
                outer_dict=None,
            ),
        )
        step_03_infer_names.run(context)
        conn.execute(
            f'''
            CREATE VIEW {SAMPLES_WITH_NAMES_VIEW} AS
            SELECT p."ktp.hcr_filename" AS "ktp.filename",
                   CAST(p."ktp.population_index" AS VARCHAR) AS "ktp.fragment",
                   CAST(p."ktp.population_index" AS VARCHAR) AS "ktp.draw_number",
                   n."ktp.first_name", n."ktp.last_name"
            FROM population p
            JOIN population_names n USING ("ktp.population_index")
            '''
        )

        result = step_06_build_outerdict_stub.run(context)

        assert context.outer_dict is not None
        assert set(context.outer_dict.keys()) == {
            NameKey(first_name="JinRong", last_name="Wang").to_json_key(),
            NameKey(first_name="Hakon H.", last_name="Hakonarson").to_json_key(),
            NameKey(first_name="Hakon H", last_name="Hakonarson").to_json_key(),
            NameKey(first_name="Gaoquan", last_name="Shi").to_json_key(),
        }
        assert "Excluded null/empty-name rows: 2" in result.diagnostics
        excluded_count = conn.execute(
            f"SELECT COUNT(*) FROM {OUTERDICT_EXCLUDED_STUB_TABLE}"
        ).fetchone()
        assert excluded_count == (2,)
    finally:
        conn.close()


def test_inferred_names_preserve_spelling_regardless_of_ssn_rule_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        step_03_infer_names,
        "HCR_XLSX_NAME_COLS",
        {"names.xlsx": ("first", "last")},
    )
    conn = duckdb.connect()
    try:
        conn.execute(
            'CREATE TABLE population AS SELECT 1 AS "ktp.population_index", '
            "'names.xlsx' AS \"ktp.hcr_filename\", "
            "' Håkon H. ' AS first, ' Håkonarson ' AS last"
        )
        context = cast(
            PipelineContext,
            SimpleNamespace(
                conn=conn,
                resources=SimpleNamespace(xlsx_resources={}),
                config=SimpleNamespace(match_rule_version=SimpleNamespace(ssn_name=1)),
            ),
        )
        step_03_infer_names.run(context)

        assert conn.execute(
            'SELECT "ktp.first_name", "ktp.last_name" FROM population_names'
        ).fetchone() == ("Håkon H.", "Håkonarson")
    finally:
        conn.close()
