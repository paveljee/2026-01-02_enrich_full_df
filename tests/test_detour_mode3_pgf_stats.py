from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from src.detours.detour_mode3_pgf_stats import (
    DETOUR_STEPS,
    _exact_binomial_inference,
    _is_exact_xlsx_match_payload,
    run_detour,
)
from src.helpers.config import PipelineConfig
from src.helpers.jsonlines import dumps_jsonlines
from src.helpers.schema import OUTERDICT_STUB_TABLE, PARQUET_INNERDICT_TABLE, XLSX_INNERDICT_TABLE
from src.helpers.vars import (
    HCR_XLSX_KEY_PREFIX,
    KTP_FILENAME_COL,
    KTP_FRAGMENT_COL,
    KTP_SOURCE_KEY_COL,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY,
    REQUIRED_FILES_CONFIG_KEYS,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _minimal_config_dict(db_path: Path) -> dict[str, object]:
    files_config: dict[str, dict[str, str]] = {}
    for key in sorted(REQUIRED_FILES_CONFIG_KEYS):
        files_config[key] = {
            "path": f"/placeholder/{key}",
            "sha256": "0" * 64,
            "desc": f"placeholder {key}",
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
        "card_subset_mode": 3,
    }


def _build_fixture_db(path: Path) -> dict[str, int]:
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE population_with_names_economy (id INTEGER)")
        con.execute("INSERT INTO population_with_names_economy SELECT * FROM range(0, 100)")

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
                "{KTP_SOURCE_KEY_COL}" VARCHAR,
                "ssnau.p_gf" DOUBLE,
                "ssnau.inference_counts" BIGINT,
                "ssnau.inference_sources" BIGINT
            )
            """
        )

        keys = {
            "sel_zero": _name_key("Sel", "Zero"),
            "sel_half": _name_key("Sel", "Half"),
            "sel_one": _name_key("Sel", "One"),
            "sel_q1": _name_key("Sel", "Quarter"),
            "sel_missing": _name_key("Sel", "Missing"),
            "sel_q3": _name_key("Sel", "ThreeQuarter"),
            "fail_multi_sciscinet": _name_key("Fail", "MultiSci"),
            "fail_no_xlsx_present": _name_key("Fail", "NoXlsxPresent"),
            "fail_non_exact_jsonl": _name_key("Fail", "Jsonl"),
            "fail_zero_sciscinet": _name_key("Fail", "ZeroSci"),
        }

        outer_rows = [(k, "") for k in keys.values()]
        con.executemany(f"INSERT INTO {OUTERDICT_STUB_TABLE} VALUES (?, ?)", outer_rows)

        def xrow(name_key: str, rows: list[dict[str, object]]) -> tuple[str, str]:
            return (name_key, dumps_jsonlines(rows))

        def match_row(*, filename: str, fragment: str, payload: object) -> dict[str, object]:
            return {
                KTP_FILENAME_COL: filename,
                KTP_FRAGMENT_COL: fragment,
                KTP_XLSX_MATCH_COL: payload,
            }

        def exact_rows(
            row_ids: list[tuple[str, str]],
            first_tokens: list[str],
            last_norm: str,
        ) -> list[dict[str, object]]:
            payload = _exact_xlsx_payload(first_tokens, last_norm)
            return [
                match_row(filename=filename, fragment=fragment, payload=payload)
                for filename, fragment in row_ids
            ]

        xlsx_rows = [
            xrow(
                keys["sel_zero"],
                exact_rows(
                    [("2019_HCR.xlsx", "10"), ("2019_HCR.xlsx", "10")],
                    ["sel"],
                    "zero",
                ),
            ),
            xrow(
                keys["sel_half"],
                # Intentionally overlap this persisted row identity with sel_zero to prove
                # population-row coverage is counted as a union across selected name keys.
                exact_rows([("2019_HCR.xlsx", "10")], ["sel"], "half"),
            ),
            xrow(
                keys["sel_one"],
                exact_rows([("2020_HCR.xlsx", "20")], ["sel"], "one"),
            ),
            xrow(
                keys["sel_q1"],
                exact_rows(
                    [("2021_HCR.xlsx", "30"), ("2021_HCR.xlsx", "30"), ("2021_HCR.xlsx", "31")],
                    ["sel"],
                    "quarter",
                ),
            ),
            xrow(
                keys["sel_missing"],
                exact_rows(
                    [("2022_HCR.xlsx", "40"), ("2022_HCR.xlsx", "40")],
                    ["sel"],
                    "missing",
                ),
            ),
            xrow(
                keys["sel_q3"],
                exact_rows([("2023_HCR.xlsx", "50")], ["sel"], "threequarter"),
            ),
            xrow(
                keys["fail_multi_sciscinet"],
                exact_rows([("2024_HCR.xlsx", "60")], ["fail"], "multisci"),
            ),
            xrow(
                keys["fail_no_xlsx_present"],
                [
                    match_row(filename="2024_HCR.xlsx", fragment="61", payload=None),
                    match_row(filename="2024_HCR.xlsx", fragment="61", payload="   "),
                ],
            ),
            # JSONL with first line exact and second line non-exact to prove
            # all-lines parsing matters.
            xrow(
                keys["fail_non_exact_jsonl"],
                [
                    match_row(
                        filename="2024_HCR.xlsx",
                        fragment="62",
                        payload=_exact_xlsx_payload(["fail"], "jsonl"),
                    ),
                    match_row(
                        filename="2024_HCR.xlsx",
                        fragment="62",
                        payload=_non_exact_xlsx_payload(["fail"], ["different"], "jsonl"),
                    ),
                ],
            ),
            xrow(
                keys["fail_zero_sciscinet"],
                exact_rows([("2024_HCR.xlsx", "63")], ["fail"], "zerosci"),
            ),
        ]
        con.executemany(f"INSERT INTO {XLSX_INNERDICT_TABLE} VALUES (?, ?)", xlsx_rows)

        ssn_rows = [
            (keys["sel_zero"], 0.0, 3, 2),
            (keys["sel_half"], 0.5, 4, 2),
            (keys["sel_one"], 1.0, 5, 3),
            (keys["sel_q1"], 0.25, 2, 1),
            (keys["sel_missing"], None, 0, 0),
            (keys["sel_q3"], 0.75, 6, 4),
            (keys["fail_multi_sciscinet"], 0.2, 7, 5),
            (keys["fail_multi_sciscinet"], 0.8, 8, 5),
            (keys["fail_no_xlsx_present"], 0.3, 2, 2),
            (keys["fail_non_exact_jsonl"], 0.4, 1, 1),
            # fail_zero_sciscinet intentionally absent
        ]
        con.executemany(
            (
                f'INSERT INTO {PARQUET_INNERDICT_TABLE} '
                f'("{KTP_SOURCE_KEY_COL}", "ssnau.p_gf", '
                f'"ssnau.inference_counts", "ssnau.inference_sources") '
                f"VALUES (?, ?, ?, ?)"
            ),
            ssn_rows,
        )

        return {
            "population_rows": 100,
            "outerdict_rows": len(outer_rows),
            "xlsx_innerdict_rows": len(xlsx_rows),
            "ssn_innerdict_rows": len(ssn_rows),
            "mode3_selected_population_rows": 6,
            "pgf_non_missing_population_rows": 5,
        }
    finally:
        con.close()


@pytest.fixture()
def detour_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, int]]:
    db_path = tmp_path / "fixture.duckdb"
    counts = _build_fixture_db(db_path)
    cfg_path = tmp_path / "config.detour_mode3.json"
    cfg_path.write_text(json.dumps(_minimal_config_dict(db_path), indent=2), encoding="utf-8")
    return cfg_path, db_path, counts


def test_detour_contract_and_mode3_stats_readonly(
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
    assert "Mode-3 p_gf Stats Detour" in plain
    assert "Selection Counts" in plain
    assert "Population rows containing mode-3 selected names" in plain
    assert "p_gf Buckets" in plain

    md = result.metadata
    assert md["mode"] == 3
    assert md["tables_used"] == [
        OUTERDICT_STUB_TABLE,
        XLSX_INNERDICT_TABLE,
        PARQUET_INNERDICT_TABLE,
    ]

    counts = md["counts"]
    assert counts["population_rows"] == baseline_counts["population_rows"]
    assert counts["outerdict_keys"] == baseline_counts["outerdict_rows"]
    assert counts["mode3_selected_names"] == 6
    assert counts["mode3_selected_population_rows"] == baseline_counts[
        "mode3_selected_population_rows"
    ]
    assert counts["mode3_selected_pct_of_population_rows"] == pytest.approx(6.0)
    assert counts["pgf_non_missing"] == 5
    assert counts["pgf_missing"] == 1
    assert counts["pgf_non_missing_population_rows"] == baseline_counts[
        "pgf_non_missing_population_rows"
    ]
    assert counts["pgf_non_missing_pct_of_population_rows"] == pytest.approx(5.0)

    rules = md["rule_counts"]
    assert rules["sciscinet_exactly_one_pass"] == 8  # all except multi and zero-sciscinet
    assert rules["sciscinet_exactly_one_fail"] == 2
    assert rules["xlsx_exact_pass"] == 8  # all except no-present and JSONL non-exact
    assert rules["xlsx_exact_fail"] == 2

    buckets = md["pgf_buckets"]
    assert buckets["missing"] == 1
    assert buckets["exact_0"] == 1
    assert buckets["exact_0_5"] == 1
    assert buckets["exact_1"] == 1
    assert buckets["between_0_and_0_5_exclusive"] == 1
    assert buckets["between_0_5_and_1_exclusive"] == 1

    dist = md["pgf_distribution"]
    assert dist["non_missing_n"] == 5
    assert dist["mean"] == pytest.approx(0.5, rel=0, abs=1e-12)
    assert dist["median"] == pytest.approx(0.5, rel=0, abs=1e-12)
    assert dist["q1"] == pytest.approx(0.25, rel=0, abs=1e-12)
    assert dist["q3"] == pytest.approx(0.75, rel=0, abs=1e-12)
    assert dist["min"] == pytest.approx(0.0, rel=0, abs=1e-12)
    assert dist["max"] == pytest.approx(1.0, rel=0, abs=1e-12)

    outliers = md["pgf_outliers_tukey"]
    assert outliers["total_outliers"] == 0

    missing_audit = md["missing_pgf_inference_audit"]
    assert missing_audit["missing_pgf_rows"] == 1
    assert missing_audit["inference_counts_zero"] == 1
    assert missing_audit["inference_counts_nonzero"] == 0
    assert missing_audit["inference_counts_null"] == 0
    assert missing_audit["inference_sources_zero"] == 1
    assert missing_audit["inference_sources_nonzero"] == 0
    assert missing_audit["inference_sources_null"] == 0
    assert missing_audit["both_zero"] == 1
    assert missing_audit["all_missing_pgf_have_both_zero"] is True

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


def test_detour_reports_exact_sign_test_inference(
    detour_fixture: tuple[Path, Path, dict[str, int]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path, _db_path, _baseline_counts = detour_fixture
    config = PipelineConfig.from_json(config_path)

    result = run_detour(config, interactive=False)
    plain = _strip_ansi(capsys.readouterr().out)

    assert "Exact Sign Test (Observed Complete-case Unique Names)" in plain

    sign_test = result.metadata["pgf_sign_test"]
    assert sign_test["null"] == "median p_gf = 0.5"
    assert sign_test["scope"] == "observed mode-3 complete-case unique names only"
    assert "Does not generalize to all unique names" in sign_test["caveat"]
    assert sign_test["estimand"] == "unique name keys as a person proxy, not Clarivate award rows"
    assert sign_test["ties_at_0_5_excluded"] == 1
    assert sign_test["non_tie_n"] == 4
    assert sign_test["above_0_5"] == 2
    assert sign_test["below_0_5"] == 2
    assert sign_test["proportion_above_0_5"] == pytest.approx(0.5, rel=0, abs=1e-12)
    assert sign_test["proportion_above_0_5_ci95_lo"] == pytest.approx(
        0.067586,
        rel=0,
        abs=1e-6,
    )
    assert sign_test["proportion_above_0_5_ci95_hi"] == pytest.approx(
        0.932414,
        rel=0,
        abs=1e-6,
    )
    assert sign_test["excess_above_0_5"] == pytest.approx(0.0, rel=0, abs=1e-12)
    assert sign_test["excess_above_0_5_ci95_lo"] == pytest.approx(
        -0.432414,
        rel=0,
        abs=1e-6,
    )
    assert sign_test["excess_above_0_5_ci95_hi"] == pytest.approx(
        0.432414,
        rel=0,
        abs=1e-6,
    )
    assert sign_test["exact_binomial_p_two_sided"] == pytest.approx(1.0, rel=0, abs=1e-12)
    assert sign_test["exact_binomial_p_two_sided_mantissa"] == pytest.approx(
        1.0,
        rel=0,
        abs=1e-12,
    )
    assert sign_test["exact_binomial_p_two_sided_exponent"] == 0
    assert sign_test["exact_binomial_p_two_sided_log10"] == pytest.approx(
        0.0,
        rel=0,
        abs=1e-12,
    )


def test_exact_binomial_inference_keeps_underflowed_p_value_in_scientific_parts() -> None:
    sign_test = _exact_binomial_inference(successes=1412, trials=6644)

    assert sign_test["p_two_sided"] == 0.0
    assert sign_test["p_two_sided_mantissa"] == pytest.approx(
        1.143782,
        rel=0,
        abs=1e-6,
    )
    assert sign_test["p_two_sided_exponent"] == -509
    assert sign_test["p_two_sided_log10"] == pytest.approx(
        -508.941657,
        rel=0,
        abs=1e-6,
    )


def test_detour_module_entrypoint(detour_fixture: tuple[Path, Path, dict[str, int]]) -> None:
    config_path, _db_path, _counts = detour_fixture
    cmd = [sys.executable, "-m", "src.detours.detour_mode3_pgf_stats", "--config", str(config_path)]
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
    assert "Mode-3 p_gf Stats Detour" in plain
    assert "Mode-3 selected names" in plain
    assert "Population rows containing mode-3 selected names" in plain
    assert "Execution Metrics" in plain


def test_detour_import_isolation() -> None:
    module_path = REPO_ROOT / "src" / "detours" / "detour_mode3_pgf_stats.py"
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
        not name.startswith("src.detours.") or name == "src.detours.detour_mode3_pgf_stats"
        for name in imported_modules
    )


def test_exact_xlsx_payload_helper_matches_expected_edge_cases() -> None:
    assert _is_exact_xlsx_match_payload(None) is True
    assert _is_exact_xlsx_match_payload("   ") is True
    assert _is_exact_xlsx_match_payload("not-json") is False
    assert _is_exact_xlsx_match_payload(
        _exact_xlsx_payload(["alpha"], "beta")
    ) is True
    assert _is_exact_xlsx_match_payload(
        _non_exact_xlsx_payload(["alpha"], ["gamma"], "beta")
    ) is False
