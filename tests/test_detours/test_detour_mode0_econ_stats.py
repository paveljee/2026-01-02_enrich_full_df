from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.detours.detour_mode0_econ_stats import (
    DETOUR_STEPS,
    MISSING_BREAKDOWN_LABEL,
    PARQUET_LEFT_JOIN_COLS,
    _is_exact_xlsx_match_payload,
    _normalize_country_list,
    run_detour,
)
from src.helpers.config import PipelineConfig
from src.helpers.data_models import FragmentType, ResourceGroup
from src.helpers.jsonlines import dumps_jsonlines
from src.helpers.resources import register_resource
from src.helpers.schema import (
    OUTERDICT_STUB_TABLE,
    PARQUET_INNERDICT_TABLE,
    PARQUET_OUTPUT_VIEW,
    POPULATION_ECON_VIEW,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    HCR_CATEGORY_COL,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    HCR_XLSX_KEY_PREFIX,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_ECONOMIES_ISO_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_PRIORITY_GROUP_LABELS,
    KTP_SOURCE_KEY_COL,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY,
    OGHIST_INCOME_LABELS,
    REQUIRED_FILES_CONFIG_KEYS,
    WORLD_BANK_XLSX_KEY,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def _name_key(first: str, last: str) -> str:
    return json.dumps({"ktp.first_name": first, "ktp.last_name": last}, ensure_ascii=False)


def _exact_xlsx_payload(first_tokens: list[str], last_norm: str) -> str:
    return json.dumps(
        {
            KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY: first_tokens,
            KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY: last_norm,
            KTP_XLSX_MATCH_FIRST_TOKENS_KEY: first_tokens,
            KTP_XLSX_MATCH_LAST_NAME_NORM_KEY: last_norm,
        },
        ensure_ascii=False,
    )


def _non_exact_xlsx_payload(
    source_tokens: list[str], first_tokens: list[str], last_norm: str
) -> str:
    return json.dumps(
        {
            KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY: source_tokens,
            KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY: last_norm,
            KTP_XLSX_MATCH_FIRST_TOKENS_KEY: first_tokens,
            KTP_XLSX_MATCH_LAST_NAME_NORM_KEY: last_norm,
        },
        ensure_ascii=False,
    )


def _write_world_bank_fixture(path: Path) -> str:
    rows = [
        [None, "Bank's fiscal year:", "FY24", "FY25", "FY26"],
        [None, "Data for calendar year :", "2022", "2023", "2024"],
        [None, "Low income (L)", "<= 1135", "<= 1145", "<= 1155"],
        [None, "Lower middle income (LM)", "1136-4465", "1146-4515", "1156-4565"],
        [None, "Upper middle income (UM)", "4466-13845", "4516-14005", "4566-14105"],
        [None, "High income (H)", "> 13845", "> 14005", "> 14105"],
        ["USA", "United States", "H", "H", "H"],
        ["FRA", "France", "H", "H", "H"],
        ["IND", "India", "LM", "LM", "LM"],
        ["NPL", "Nepal", "L", "L", "L"],
        ["CHN", "China", "UM", "UM", "UM"],
        ["BRA", "Brazil", "UM", "UM", "UM"],
        ["AFG", "Afghanistan", "L", "L", "L"],
    ]
    df = pd.DataFrame(rows)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Country Analytical History", header=False, index=False)
    resource = register_resource(
        path,
        group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
        fragment_type=FragmentType.EXCEL_ROW,
        description="World Bank country list fixture",
    )
    return resource.hash


def _minimal_config_dict(
    db_path: Path,
    world_bank_path: Path,
    world_bank_hash: str,
) -> dict[str, object]:
    files_config: dict[str, dict[str, str]] = {}
    for key in sorted(REQUIRED_FILES_CONFIG_KEYS):
        files_config[key] = {
            "path": f"/placeholder/{key}",
            "sha256": "0" * 64,
            "desc": f"placeholder {key}",
        }
    files_config[WORLD_BANK_XLSX_KEY] = {
        "path": str(world_bank_path),
        "sha256": world_bank_hash,
        "desc": "World Bank country list fixture",
    }
    files_config[f"{HCR_XLSX_KEY_PREFIX}2024"] = {
        "path": "/placeholder/2024_HCR.xlsx",
        "sha256": "1" * 64,
        "desc": "placeholder hcr",
    }
    return {
        "files_config": files_config,
        "db_file": str(db_path),
        "state_file": str(db_path.with_suffix(".state.json")),
        "output_dir": str(db_path.parent / "output"),
        "output_format": "txt",
        "pandoc_reference_docx": str(db_path.parent / "reference.docx"),
        "docx_dir": str(db_path.parent / "docx"),
        "timezone": "UTC",
        "sample_seed": 42,
        "sample_draw_sizes": [1],
        "pilot_xlsx_name": "2024_HCR.xlsx",
        "total_draws": 1,
        "card_subset_mode": 0,
    }


def _build_fixture_db(path: Path) -> dict[str, int]:
    con = duckdb.connect(str(path))
    try:
        con.execute(
            f"""
            CREATE TABLE {POPULATION_ECON_VIEW} (
                id INTEGER,
                "{KTP_POPULATION_INDEX_COL}" INTEGER,
                "{HCR_FILENAME_COL}" VARCHAR,
                "{HCR_ROW_COL}" VARCHAR,
                "{KTP_FIRST_NAME_COL}" VARCHAR,
                "{KTP_LAST_NAME_COL}" VARCHAR,
                "{HCR_CATEGORY_COL}" VARCHAR,
                "{KTP_HCR_PRIMARY_AFFILIATIONS_COL}" VARCHAR,
                "{KTP_HCR_SECONDARY_AFFILIATIONS_COL}" VARCHAR,
                "{KTP_ECONOMIES_COL}" VARCHAR,
                "{KTP_ECONOMIES_INCOME_GROUP_COL}" VARCHAR,
                "{KTP_PRIORITY_COL}" INTEGER,
                "{KTP_PRIORITY_GROUP_COL}" VARCHAR
            )
            """
        )

        con.execute(
            f"""
            CREATE TABLE {OUTERDICT_STUB_TABLE} (
                name_key VARCHAR,
                innerdicts VARCHAR
            )
            """
        )
        con.execute(
            f"""
            CREATE TABLE {XLSX_INNERDICT_TABLE} (
                name_key VARCHAR,
                innerdicts VARCHAR
            )
            """
        )
        con.execute(
            f"""
            CREATE TABLE {PARQUET_INNERDICT_TABLE} (
                "{KTP_SOURCE_KEY_COL}" VARCHAR
            )
            """
        )
        con.execute(
            """
            CREATE TABLE income_map (
                match_name VARCHAR,
                country VARCHAR,
                income_label VARCHAR
            )
            """
        )

        keys = {
            "sel_zero": _name_key("Sel", "Zero"),
            "sel_one": _name_key("Sel", "One"),
            "sel_two_income": _name_key("Sel", "TwoIncome"),
            "sel_two_priority": _name_key("Sel", "TwoPriority"),
            "sel_three": _name_key("Sel", "Three"),
            "sel_fourplus": _name_key("Sel", "FourPlus"),
            "fail_multi_sciscinet": _name_key("Fail", "MultiSci"),
            "fail_no_xlsx_present": _name_key("Fail", "NoXlsxPresent"),
            "fail_non_exact_jsonl": _name_key("Fail", "Jsonl"),
            "fail_zero_sciscinet": _name_key("Fail", "ZeroSci"),
        }
        con.executemany(
            f"INSERT INTO {OUTERDICT_STUB_TABLE} VALUES (?, ?)",
            [(name_key, "") for name_key in keys.values()],
        )

        def match_row(
            *,
            filename: str,
            fragment: str,
            payload: object,
            countries: object,
            income_group: object,
            priority_group: object,
            first_name: str,
            last_name: str,
            primary_affiliation: str,
            secondary_affiliation: str | None = None,
        ) -> dict[str, object]:
            return {
                KTP_FILENAME_COL: filename,
                KTP_FRAGMENT_COL: fragment,
                KTP_FIRST_NAME_COL: first_name,
                KTP_LAST_NAME_COL: last_name,
                KTP_HCR_PRIMARY_AFFILIATIONS_COL: primary_affiliation,
                KTP_HCR_SECONDARY_AFFILIATIONS_COL: secondary_affiliation,
                KTP_XLSX_MATCH_COL: payload,
                KTP_ECONOMIES_COL: countries,
                KTP_ECONOMIES_INCOME_GROUP_COL: income_group,
                KTP_PRIORITY_GROUP_COL: priority_group,
            }

        high = OGHIST_INCOME_LABELS["H"]
        low = OGHIST_INCOME_LABELS["L"]
        lower_middle = OGHIST_INCOME_LABELS["LM"]
        priority_fallback = KTP_PRIORITY_GROUP_LABELS[1]
        priority_china = KTP_PRIORITY_GROUP_LABELS[2]
        priority_eu = KTP_PRIORITY_GROUP_LABELS[4]
        priority_english = KTP_PRIORITY_GROUP_LABELS[5]
        upper_middle = OGHIST_INCOME_LABELS["UM"]

        con.executemany(
            "INSERT INTO income_map VALUES (?, ?, ?)",
            [
                ("United States", "United States", high),
                ("France", "France", high),
                ("India", "India", lower_middle),
                ("Nepal", "Nepal", low),
                ("China", "China", upper_middle),
                ("Brazil", "Brazil", upper_middle),
                ("Afghanistan", "Afghanistan", low),
            ],
        )

        xlsx_rows = [
            (
                keys["sel_zero"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2019_HCR.xlsx",
                            fragment="10",
                            payload=_exact_xlsx_payload(["sel"], "zero"),
                            countries="[]",
                            income_group=None,
                            priority_group=priority_fallback,
                            first_name="Sel",
                            last_name="Zero",
                            primary_affiliation="No Country Institute",
                        ),
                        match_row(
                            filename="2019_HCR.xlsx",
                            fragment="10",
                            payload=_exact_xlsx_payload(["sel"], "zero"),
                            countries="[]",
                            income_group=None,
                            priority_group=priority_fallback,
                            first_name="Sel",
                            last_name="Zero",
                            primary_affiliation="No Country Institute",
                        ),
                    ]
                ),
            ),
            (
                keys["sel_one"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2020_HCR.xlsx",
                            fragment="20",
                            payload=_exact_xlsx_payload(["sel"], "one"),
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Sel",
                            last_name="One",
                            primary_affiliation="Paris Health Center",
                        )
                    ]
                ),
            ),
            (
                keys["sel_two_income"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2021_HCR.xlsx",
                            fragment="30",
                            payload=_exact_xlsx_payload(["sel"], "twoincome"),
                            countries=json.dumps(["India"]),
                            income_group=lower_middle,
                            priority_group=priority_fallback,
                            first_name="Sel",
                            last_name="TwoIncome",
                            primary_affiliation="Delhi Policy Lab",
                        ),
                        match_row(
                            filename="2021_HCR.xlsx",
                            fragment="31",
                            payload=_exact_xlsx_payload(["sel"], "twoincome"),
                            countries=["Nepal"],
                            income_group=low,
                            priority_group=priority_fallback,
                            first_name="Sel",
                            last_name="TwoIncome",
                            primary_affiliation="Kathmandu Policy Lab",
                        ),
                    ]
                ),
            ),
            (
                keys["sel_two_priority"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2022_HCR.xlsx",
                            fragment="40",
                            payload=_exact_xlsx_payload(["sel"], "twopriority"),
                            countries=["United States"],
                            income_group=high,
                            priority_group=priority_english,
                            first_name="Sel",
                            last_name="TwoPriority",
                            primary_affiliation="Boston Health Institute",
                        ),
                        match_row(
                            filename="2022_HCR.xlsx",
                            fragment="41",
                            payload=_exact_xlsx_payload(["sel"], "twopriority"),
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Sel",
                            last_name="TwoPriority",
                            primary_affiliation="Paris Health Institute",
                        ),
                    ]
                ),
            ),
            (
                keys["sel_three"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2023_HCR.xlsx",
                            fragment="50",
                            payload=_exact_xlsx_payload(["sel"], "three"),
                            countries=["United States", "France", "India", "India"],
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Sel",
                            last_name="Three",
                            primary_affiliation="Tri-Country School",
                        )
                    ]
                ),
            ),
            (
                keys["sel_fourplus"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2024_HCR.xlsx",
                            fragment="60",
                            payload=_exact_xlsx_payload(["sel"], "fourplus"),
                            countries=json.dumps(
                                ["China", "United States", "France", "India", "Nepal", "China"]
                            ),
                            income_group=high,
                            priority_group=priority_china,
                            first_name="Sel",
                            last_name="FourPlus",
                            primary_affiliation="Global Health Alliance",
                        )
                    ]
                ),
            ),
            (
                keys["fail_multi_sciscinet"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2024_HCR.xlsx",
                            fragment="61",
                            payload=_exact_xlsx_payload(["fail"], "multisci"),
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Fail",
                            last_name="MultiSci",
                            primary_affiliation="Should Not Appear",
                        )
                    ]
                ),
            ),
            (
                keys["fail_no_xlsx_present"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2024_HCR.xlsx",
                            fragment="62",
                            payload=None,
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Fail",
                            last_name="NoXlsxPresent",
                            primary_affiliation="Should Not Appear",
                        ),
                        match_row(
                            filename="2024_HCR.xlsx",
                            fragment="62",
                            payload="   ",
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Fail",
                            last_name="NoXlsxPresent",
                            primary_affiliation="Should Not Appear",
                        ),
                    ]
                ),
            ),
            (
                keys["fail_non_exact_jsonl"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2024_HCR.xlsx",
                            fragment="63",
                            payload=_exact_xlsx_payload(["fail"], "jsonl"),
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Fail",
                            last_name="Jsonl",
                            primary_affiliation="Should Not Appear",
                        ),
                        match_row(
                            filename="2024_HCR.xlsx",
                            fragment="63",
                            payload=_non_exact_xlsx_payload(["fail"], ["different"], "jsonl"),
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Fail",
                            last_name="Jsonl",
                            primary_affiliation="Should Not Appear",
                        ),
                    ]
                ),
            ),
            (
                keys["fail_zero_sciscinet"],
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2024_HCR.xlsx",
                            fragment="64",
                            payload=_exact_xlsx_payload(["fail"], "zerosci"),
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Fail",
                            last_name="ZeroSci",
                            primary_affiliation="Should Not Appear",
                        )
                    ]
                ),
            ),
            (
                _name_key("Wrong", "Person"),
                dumps_jsonlines(
                    [
                        match_row(
                            filename="2020_HCR.xlsx",
                            fragment="20",
                            payload=_non_exact_xlsx_payload(["wrong"], ["sel"], "one"),
                            countries=json.dumps(["France"]),
                            income_group=high,
                            priority_group=priority_eu,
                            first_name="Sel",
                            last_name="One",
                            primary_affiliation="Paris Health Center",
                        )
                    ]
                ),
            ),
        ]
        con.executemany(f"INSERT INTO {XLSX_INNERDICT_TABLE} VALUES (?, ?)", xlsx_rows)
        population_rows = [
            (
                10,
                0,
                "2019_HCR.xlsx",
                "10",
                "Sel",
                "Zero",
                "Fixture",
                "No Country Institute",
                None,
                "[]",
                None,
                1,
                priority_fallback,
            ),
            (
                20,
                1,
                "2020_HCR.xlsx",
                "20",
                "Sel",
                "One",
                "Fixture",
                "Paris Health Center",
                None,
                json.dumps(["France"]),
                high,
                4,
                priority_eu,
            ),
            (
                30,
                2,
                "2021_HCR.xlsx",
                "30",
                "Sel",
                "TwoIncome",
                "Fixture",
                "Delhi Policy Lab",
                None,
                json.dumps(["India"]),
                lower_middle,
                1,
                priority_fallback,
            ),
            (
                31,
                3,
                "2021_HCR.xlsx",
                "31",
                "Sel",
                "TwoIncome",
                "Fixture",
                "Kathmandu Policy Lab",
                None,
                json.dumps(["Nepal"]),
                low,
                1,
                priority_fallback,
            ),
            (
                40,
                4,
                "2022_HCR.xlsx",
                "40",
                "Sel",
                "TwoPriority",
                "Fixture",
                "Boston Health Institute",
                None,
                json.dumps(["United States"]),
                high,
                5,
                priority_english,
            ),
            (
                41,
                5,
                "2022_HCR.xlsx",
                "41",
                "Sel",
                "TwoPriority",
                "Fixture",
                "Paris Health Institute",
                None,
                json.dumps(["France"]),
                high,
                4,
                priority_eu,
            ),
            (
                50,
                6,
                "2023_HCR.xlsx",
                "50",
                "Sel",
                "Three",
                "Fixture",
                "Tri-Country School",
                None,
                json.dumps(["United States", "France", "India", "India"]),
                high,
                4,
                priority_eu,
            ),
            (
                60,
                7,
                "2024_HCR.xlsx",
                "60",
                "Sel",
                "FourPlus",
                "Fixture",
                "Global Health Alliance",
                None,
                json.dumps(["China", "United States", "France", "India", "Nepal", "China"]),
                high,
                2,
                priority_china,
            ),
            (
                61,
                8,
                "2024_HCR.xlsx",
                "61",
                "Fail",
                "MultiSci",
                "Fixture",
                "Should Not Appear",
                None,
                json.dumps(["France"]),
                high,
                4,
                priority_eu,
            ),
            (
                62,
                9,
                "2024_HCR.xlsx",
                "62",
                "Fail",
                "NoXlsxPresent",
                "Fixture",
                "Should Not Appear",
                None,
                json.dumps(["France"]),
                high,
                4,
                priority_eu,
            ),
            (
                63,
                10,
                "2024_HCR.xlsx",
                "63",
                "Fail",
                "Jsonl",
                "Fixture",
                "Should Not Appear",
                None,
                json.dumps(["France"]),
                high,
                4,
                priority_eu,
            ),
            (
                64,
                11,
                "2024_HCR.xlsx",
                "64",
                "Fail",
                "ZeroSci",
                "Fixture",
                "Should Not Appear",
                None,
                json.dumps(["France"]),
                high,
                4,
                priority_eu,
            ),
            (
                70,
                12,
                "2024_HCR.xlsx",
                "70",
                None,
                "Danish",
                "Fixture",
                "Guangdong University of Foreign Studies",
                None,
                json.dumps(["China"]),
                upper_middle,
                2,
                priority_china,
            ),
            (
                71,
                13,
                "2024_HCR.xlsx",
                "71",
                "Nameless",
                None,
                "Fixture",
                "Boston Health Institute",
                None,
                json.dumps(["United States"]),
                high,
                5,
                priority_english,
            ),
        ]
        con.executemany(
            f"""
            INSERT INTO {POPULATION_ECON_VIEW} (
                id,
                "{KTP_POPULATION_INDEX_COL}",
                "{HCR_FILENAME_COL}",
                "{HCR_ROW_COL}",
                "{KTP_FIRST_NAME_COL}",
                "{KTP_LAST_NAME_COL}",
                "{HCR_CATEGORY_COL}",
                "{KTP_HCR_PRIMARY_AFFILIATIONS_COL}",
                "{KTP_HCR_SECONDARY_AFFILIATIONS_COL}",
                "{KTP_ECONOMIES_COL}",
                "{KTP_ECONOMIES_INCOME_GROUP_COL}",
                "{KTP_PRIORITY_COL}",
                "{KTP_PRIORITY_GROUP_COL}"
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            population_rows,
        )

        ssn_rows = [
            (keys["sel_zero"],),
            (keys["sel_one"],),
            (keys["sel_two_income"],),
            (keys["sel_two_priority"],),
            (keys["sel_three"],),
            (keys["sel_fourplus"],),
            (keys["fail_multi_sciscinet"],),
            (keys["fail_multi_sciscinet"],),
            (keys["fail_no_xlsx_present"],),
            (keys["fail_non_exact_jsonl"],),
        ]
        con.executemany(
            f'INSERT INTO {PARQUET_INNERDICT_TABLE} ("{KTP_SOURCE_KEY_COL}") VALUES (?)',
            ssn_rows,
        )
        con.execute(
            f"""
            CREATE OR REPLACE VIEW {PARQUET_OUTPUT_VIEW} AS
            SELECT
                "{KTP_SOURCE_KEY_COL}" AS "{KTP_SOURCE_KEY_COL}",
                0.25 AS "ssnau.p_gf",
                3 AS "ssnau.inference_counts",
                1 AS "ssnau.inference_sources",
                'author_details.parquet' AS "ssnad.filename",
                'authors.parquet' AS "ssnau.filename",
                '["Field A"]' AS "ssn.field_ids_list"
            FROM {PARQUET_INNERDICT_TABLE}
            """
        )

        return {
            "population_rows": len(population_rows),
            "outerdict_rows": len(keys),
            "xlsx_innerdict_rows": len(xlsx_rows),
            "ssn_innerdict_rows": len(ssn_rows),
            "mode0_selected_population_rows": 12,
            "population_rows_with_countries": 13,
            "population_rows_with_income_group": 13,
            "population_rows_with_priority_group": 14,
        }
    finally:
        con.close()


@pytest.fixture()
def detour_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, int]]:
    db_path = tmp_path / "fixture.duckdb"
    world_bank_path = tmp_path / "OGHIST_2025_07_01.xlsx"
    world_bank_hash = _write_world_bank_fixture(world_bank_path)
    counts = _build_fixture_db(db_path)
    cfg_path = tmp_path / "config.detour_mode0_econ.json"
    cfg_path.write_text(
        json.dumps(_minimal_config_dict(db_path, world_bank_path, world_bank_hash), indent=2),
        encoding="utf-8",
    )
    return cfg_path, db_path, counts


def test_detour_contract_and_mode0_econ_stats_readonly(
    detour_fixture: tuple[Path, Path, dict[str, int]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, db_path, baseline_counts = detour_fixture
    config = PipelineConfig.from_json(config_path)

    def _row_count(conn: duckdb.DuckDBPyConnection, table_name: str) -> int:
        row = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        if row is None:
            raise RuntimeError(f"Missing row count for {table_name}")
        return int(row[0])

    before = duckdb.connect(str(db_path), read_only=True)
    try:
        before_counts = {
            OUTERDICT_STUB_TABLE: _row_count(before, OUTERDICT_STUB_TABLE),
            XLSX_INNERDICT_TABLE: _row_count(before, XLSX_INNERDICT_TABLE),
            PARQUET_INNERDICT_TABLE: _row_count(before, PARQUET_INNERDICT_TABLE),
        }
    finally:
        before.close()

    result = run_detour(config, interactive=False)
    plain = _strip_ansi(capsys.readouterr().out)

    assert result.success is True
    assert result.steps_completed == DETOUR_STEPS == []
    assert "Mode-0 Economy Stats Detour" in plain
    assert "Priority-Group Definitions" in plain
    assert "Country Coverage Scope" in plain
    assert "Country Coverage by Economy Category" in plain
    assert "Country Coverage by Priority Category" in plain
    assert "Uncovered Countries" in plain
    assert "Shown in SVG" in plain
    assert "Uncovered countries SVG" in plain
    assert "Income-Group Breakdown" in plain
    assert "Priority-Group Breakdown" in plain
    assert "Population Rows" in plain
    assert "Multi-Country Divergence" in plain
    assert "Derived Final Name-Level Groups" in plain
    assert "Lower-tier preferred" in plain
    assert "Any Low-Income Affiliated Country" in plain
    assert "Missing Income Group" in plain
    assert "4+ Countries" in plain
    assert OGHIST_INCOME_LABELS["L"] in plain
    assert MISSING_BREAKDOWN_LABEL in plain
    assert KTP_PRIORITY_GROUP_LABELS[2] in plain
    assert KTP_PRIORITY_GROUP_LABELS[3] in plain
    assert KTP_PRIORITY_GROUP_LABELS[4] in plain
    assert KTP_PRIORITY_GROUP_LABELS[5] in plain
    assert KTP_PRIORITY_GROUP_LABELS[1] in plain

    md = result.metadata
    assert md["detour_id"] == "mode0-econ-stats"
    assert md["mode"] == 0
    assert md["tables_used"] == [
        OUTERDICT_STUB_TABLE,
        XLSX_INNERDICT_TABLE,
    ]
    assert md["world_bank_country_resource"]["resource_name"] == "OGHIST_2025_07_01.xlsx"
    assert md["world_bank_country_resource"]["resource_hash"]
    assert md["world_bank_country_resource"]["excluded_former_economies"] == []
    assert md["population_with_economy_parquet_csv"]["path"] == (
        "tmp/mode0_econ_stats_population_with_economy_and_parquet.csv"
    )
    assert md["country_coverage_map_svg"] == "tmp/mode0_econ_stats_not_covered_countries.svg"
    assert Path(md["country_coverage_map_svg"]).is_file()
    assert Path(md["population_with_economy_parquet_csv"]["path"]).is_file()
    dump_df = pd.read_csv(md["population_with_economy_parquet_csv"]["path"])
    assert len(dump_df) == baseline_counts["population_rows"]
    assert (
        md["population_with_economy_parquet_csv"]["rows"]
        == baseline_counts["population_rows"]
    )
    assert KTP_ECONOMIES_ISO_COL in dump_df.columns
    assert dump_df[KTP_PRIORITY_GROUP_COL].notna().sum() == baseline_counts[
        "population_rows_with_priority_group"
    ]
    assert dump_df[KTP_ECONOMIES_ISO_COL].eq("[]").sum() == 1
    assert md["population_with_economy_parquet_csv"]["parquet_prefixed_columns"] == (
        PARQUET_LEFT_JOIN_COLS
    )
    for col in PARQUET_LEFT_JOIN_COLS:
        assert col in dump_df.columns
    assert "ssnad.filename" not in dump_df.columns
    assert "ssnau.filename" not in dump_df.columns
    assert "ssn.field_ids_list" not in dump_df.columns

    counts = md["counts"]
    assert counts["population_rows"] == baseline_counts["population_rows"]
    assert counts["outerdict_keys"] == baseline_counts["outerdict_rows"]
    assert counts["mode0_selected_names"] == baseline_counts["outerdict_rows"]
    assert counts["mode0_selected_population_rows"] == baseline_counts[
        "mode0_selected_population_rows"
    ]
    assert counts["mode0_selected_pct_of_population_rows"] == pytest.approx(12 / 14 * 100.0)
    assert counts["selected_names_with_countries"] == 9
    assert counts["selected_names_with_income_group"] == 9
    assert counts["selected_names_with_priority_group"] == 10
    assert counts["row_label_scope_source"] == POPULATION_ECON_VIEW
    assert counts["row_label_population_rows"] == baseline_counts["population_rows"]
    assert counts["population_rows_with_countries"] == baseline_counts[
        "population_rows_with_countries"
    ]
    assert counts["population_rows_with_income_group"] == baseline_counts[
        "population_rows_with_income_group"
    ]
    assert counts["population_rows_with_priority_group"] == baseline_counts[
        "population_rows_with_priority_group"
    ]

    country_coverage = md["country_coverage"]
    assert country_coverage["total_countries"] == 7
    assert country_coverage["covered_countries"] == 5
    assert country_coverage["not_covered_countries"] == 2
    assert country_coverage["covered_pct_of_total_countries"] == pytest.approx(5 / 7 * 100.0)
    assert country_coverage["not_covered_pct_of_total_countries"] == pytest.approx(
        2 / 7 * 100.0
    )
    assert country_coverage["covered_country_names"] == [
        "China",
        "France",
        "India",
        "Nepal",
        "United States",
    ]
    assert country_coverage["not_covered_country_names"] == ["Afghanistan", "Brazil"]
    assert country_coverage["not_covered_country_codes"] == ["AFG", "BRA"]
    assert md["uncovered_countries"] == [
        {"country_code": "AFG", "country": "Afghanistan", "coverage": "Not covered"},
        {"country_code": "BRA", "country": "Brazil", "coverage": "Not covered"},
    ]

    country_income_breakdown = {
        row["label"]: row for row in country_coverage["income_group_breakdown"]
    }
    assert country_income_breakdown[OGHIST_INCOME_LABELS["H"]]["total_countries"] == 2
    assert country_income_breakdown[OGHIST_INCOME_LABELS["UM"]]["total_countries"] == 2
    assert country_income_breakdown[OGHIST_INCOME_LABELS["LM"]]["total_countries"] == 1
    assert country_income_breakdown[OGHIST_INCOME_LABELS["L"]]["total_countries"] == 2
    assert country_income_breakdown[OGHIST_INCOME_LABELS["H"]]["covered_countries"] == 2
    assert country_income_breakdown[OGHIST_INCOME_LABELS["UM"]]["covered_countries"] == 1
    assert country_income_breakdown[OGHIST_INCOME_LABELS["LM"]]["covered_countries"] == 1
    assert country_income_breakdown[OGHIST_INCOME_LABELS["L"]]["covered_countries"] == 1
    assert country_income_breakdown[OGHIST_INCOME_LABELS["UM"]]["not_covered_countries"] == 1
    assert country_income_breakdown[OGHIST_INCOME_LABELS["L"]]["not_covered_countries"] == 1

    country_priority_breakdown = {
        row["label"]: row for row in country_coverage["priority_group_breakdown"]
    }
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[2]]["total_countries"] == 1
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[3]]["total_countries"] == 0
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[4]]["total_countries"] == 1
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[5]]["total_countries"] == 1
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[1]]["total_countries"] == 4
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[2]]["covered_countries"] == 1
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[4]]["covered_countries"] == 1
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[5]]["covered_countries"] == 1
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[1]]["covered_countries"] == 2
    assert country_priority_breakdown[KTP_PRIORITY_GROUP_LABELS[1]][
        "not_covered_countries"
    ] == 2

    buckets = md["country_cardinality_buckets"]
    assert buckets["exact_0"] == 1
    assert buckets["exact_1"] == 5
    assert buckets["exact_2"] == 2
    assert buckets["exact_3"] == 1
    assert buckets["exact_4_or_more"] == 1

    dist = md["country_cardinality_distribution"]
    assert dist["n"] == 10
    assert dist["mean"] == pytest.approx(1.7, rel=0, abs=1e-12)
    assert dist["median"] == pytest.approx(1.0, rel=0, abs=1e-12)
    assert dist["q1"] == pytest.approx(1.0, rel=0, abs=1e-12)
    assert dist["q3"] == pytest.approx(2.0, rel=0, abs=1e-12)
    assert dist["min"] == pytest.approx(0.0, rel=0, abs=1e-12)
    assert dist["max"] == pytest.approx(5.0, rel=0, abs=1e-12)

    outliers = md["country_cardinality_outliers_tukey"]
    assert outliers["upper_outliers"] == 1
    assert outliers["total_outliers"] == 1

    income_breakdown = {row["income_group"]: row for row in md["income_group_breakdown"]}
    assert income_breakdown[OGHIST_INCOME_LABELS["H"]]["selected_population_rows"] == 10
    assert income_breakdown[OGHIST_INCOME_LABELS["LM"]]["selected_population_rows"] == 1
    assert income_breakdown[OGHIST_INCOME_LABELS["L"]]["selected_population_rows"] == 1
    assert income_breakdown[OGHIST_INCOME_LABELS["UM"]]["selected_population_rows"] == 1
    assert income_breakdown[MISSING_BREAKDOWN_LABEL]["selected_population_rows"] == 1

    lower_tier_breakdown = {
        row["income_group"]: row for row in md["income_group_breakdown_lower_tier_preferred"]
    }
    assert lower_tier_breakdown[OGHIST_INCOME_LABELS["H"]]["selected_population_rows"] == 8
    assert lower_tier_breakdown[OGHIST_INCOME_LABELS["UM"]]["selected_population_rows"] == 1
    assert lower_tier_breakdown[OGHIST_INCOME_LABELS["LM"]]["selected_population_rows"] == 2
    assert lower_tier_breakdown[OGHIST_INCOME_LABELS["L"]]["selected_population_rows"] == 2
    assert lower_tier_breakdown[MISSING_BREAKDOWN_LABEL]["selected_population_rows"] == 1

    priority_breakdown = {row["priority_group"]: row for row in md["priority_group_breakdown"]}
    assert priority_breakdown[KTP_PRIORITY_GROUP_LABELS[1]]["selected_population_rows"] == 3
    assert priority_breakdown[KTP_PRIORITY_GROUP_LABELS[2]]["selected_population_rows"] == 2
    assert priority_breakdown[KTP_PRIORITY_GROUP_LABELS[3]]["selected_population_rows"] == 0
    assert priority_breakdown[KTP_PRIORITY_GROUP_LABELS[4]]["selected_population_rows"] == 7
    assert priority_breakdown[KTP_PRIORITY_GROUP_LABELS[5]]["selected_population_rows"] == 2
    assert priority_breakdown[MISSING_BREAKDOWN_LABEL]["selected_population_rows"] == 0

    derived_higher = {
        (row["group_type"], row["label"]): row
        for row in md["derived_name_group_breakdown_higher_preferred"]
    }
    assert derived_higher[("Income group", OGHIST_INCOME_LABELS["H"])]["selected_names"] == 8
    assert derived_higher[("Income group", OGHIST_INCOME_LABELS["UM"])]["selected_names"] == 0
    assert derived_higher[("Income group", OGHIST_INCOME_LABELS["LM"])]["selected_names"] == 1
    assert derived_higher[("Income group", OGHIST_INCOME_LABELS["L"])]["selected_names"] == 0
    assert derived_higher[("Income group", MISSING_BREAKDOWN_LABEL)]["selected_names"] == 1
    assert (
        derived_higher[("Priority group", KTP_PRIORITY_GROUP_LABELS[4])]["selected_names"] == 7
    )
    assert (
        derived_higher[("Priority group", KTP_PRIORITY_GROUP_LABELS[2])]["selected_names"] == 1
    )
    assert (
        derived_higher[("Priority group", KTP_PRIORITY_GROUP_LABELS[1])]["selected_names"] == 2
    )
    assert (
        derived_higher[("Priority group", KTP_PRIORITY_GROUP_LABELS[3])]["selected_names"] == 0
    )
    assert (
        derived_higher[("Priority group", KTP_PRIORITY_GROUP_LABELS[5])]["selected_names"] == 0
    )
    assert derived_higher[("Priority group", MISSING_BREAKDOWN_LABEL)]["selected_names"] == 0

    derived_lower = {
        (row["group_type"], row["label"]): row
        for row in md["derived_name_group_breakdown_lower_preferred"]
    }
    assert derived_lower[("Income group", OGHIST_INCOME_LABELS["H"])]["selected_names"] == 6
    assert derived_lower[("Income group", OGHIST_INCOME_LABELS["UM"])]["selected_names"] == 0
    assert derived_lower[("Income group", OGHIST_INCOME_LABELS["LM"])]["selected_names"] == 1
    assert derived_lower[("Income group", OGHIST_INCOME_LABELS["L"])]["selected_names"] == 2
    assert derived_lower[("Income group", MISSING_BREAKDOWN_LABEL)]["selected_names"] == 1
    assert (
        derived_lower[("Priority group", KTP_PRIORITY_GROUP_LABELS[1])]["selected_names"] == 4
    )
    assert (
        derived_lower[("Priority group", KTP_PRIORITY_GROUP_LABELS[5])]["selected_names"] == 1
    )
    assert (
        derived_lower[("Priority group", KTP_PRIORITY_GROUP_LABELS[4])]["selected_names"] == 5
    )
    assert (
        derived_lower[("Priority group", KTP_PRIORITY_GROUP_LABELS[3])]["selected_names"] == 0
    )
    assert (
        derived_lower[("Priority group", KTP_PRIORITY_GROUP_LABELS[2])]["selected_names"] == 0
    )
    assert derived_lower[("Priority group", MISSING_BREAKDOWN_LABEL)]["selected_names"] == 0

    divergence = md["multi_country_divergence"]
    assert divergence["multi_country_names"] == 4
    assert divergence["different_income_groups"] == 3
    assert divergence["different_priority_groups"] == 3
    assert divergence["multi_country_pct_of_mode0"] == pytest.approx(40.0)
    assert divergence["different_income_groups_pct_of_multi_country"] == pytest.approx(75.0)
    assert divergence["different_priority_groups_pct_of_multi_country"] == pytest.approx(75.0)

    audit = md["label_coverage_consistency_audit"]
    assert audit["selected_names_without_income_group"] == 1
    assert audit["selected_names_without_priority_group"] == 0
    assert audit["selected_names_with_exactly_one_row_income_group"] == 8
    assert audit["selected_names_with_multiple_row_income_groups"] == 1
    assert audit["selected_names_with_exactly_one_row_priority_group"] == 9
    assert audit["selected_names_with_multiple_row_priority_groups"] == 1
    assert audit["population_rows_missing_income_group"] == 1
    assert audit["population_rows_missing_priority_group"] == 0

    highlights = md["researcher_detail_highlights"]
    assert len(highlights["any_low_income_affiliated_country"]) == 2
    assert len(highlights["missing_income_group"]) == 1
    assert len(highlights["four_or_more_countries"]) == 1
    assert highlights["missing_income_group"][0]["researcher_name"] == "Zero, Sel"
    assert highlights["four_or_more_countries"][0]["researcher_name"] == "FourPlus, Sel"

    after = duckdb.connect(str(db_path), read_only=True)
    try:
        after_counts = {
            OUTERDICT_STUB_TABLE: _row_count(after, OUTERDICT_STUB_TABLE),
            XLSX_INNERDICT_TABLE: _row_count(after, XLSX_INNERDICT_TABLE),
            PARQUET_INNERDICT_TABLE: _row_count(after, PARQUET_INNERDICT_TABLE),
        }
    finally:
        after.close()
    assert before_counts == after_counts == {
        OUTERDICT_STUB_TABLE: baseline_counts["outerdict_rows"],
        XLSX_INNERDICT_TABLE: baseline_counts["xlsx_innerdict_rows"],
        PARQUET_INNERDICT_TABLE: baseline_counts["ssn_innerdict_rows"],
    }


def test_detour_module_entrypoint(detour_fixture: tuple[Path, Path, dict[str, int]]) -> None:
    config_path, _db_path, _counts = detour_fixture
    cmd = [
        sys.executable,
        "-m",
        "src.detours.detour_mode0_econ_stats",
        "--config",
        str(config_path),
    ]
    env = {
        **os.environ,
        "PYTHONPATH": (
            str(REPO_ROOT)
            if not os.environ.get("PYTHONPATH")
            else str(REPO_ROOT) + os.pathsep + os.environ["PYTHONPATH"]
        ),
    }
    completed = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=config_path.parent,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    plain = _strip_ansi(completed.stdout)
    assert "Mode-0 Economy Stats Detour" in plain
    assert "Priority-Group Definitions" in plain
    assert "Mode-0 selected names" in plain
    assert "Execution Metrics" in plain


def test_detour_import_isolation() -> None:
    module_path = REPO_ROOT / "src" / "detours" / "detour_mode0_econ_stats.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imported_modules.add(name.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert "src.repl" not in imported_modules
    assert "src.steps" not in imported_modules
    assert "src.helpers.init" not in imported_modules
    assert "src.helpers.repl_runtime" not in imported_modules
    assert all(
        not name.startswith("src.detours.") or name == "src.detours.detour_mode0_econ_stats"
        for name in imported_modules
    )


def test_helpers_cover_normalization_and_exactness() -> None:
    assert _normalize_country_list(None) == []
    assert _normalize_country_list("   ") == []
    assert _normalize_country_list('["France", "France", "India"]') == ["France", "India"]
    assert _normalize_country_list(["India", "India", "France"]) == ["France", "India"]

    assert _is_exact_xlsx_match_payload(None) is True
    assert _is_exact_xlsx_match_payload("   ") is True
    assert _is_exact_xlsx_match_payload("not-json") is False
    assert _is_exact_xlsx_match_payload(_exact_xlsx_payload(["alpha"], "beta")) is True
    assert _is_exact_xlsx_match_payload(
        _non_exact_xlsx_payload(["alpha"], ["gamma"], "beta")
    ) is False
