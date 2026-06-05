from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
from collections.abc import Generator
from copy import deepcopy
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.detours.detour_step4_breakdown import DETOUR_STEPS, run_detour
from src.helpers.config import PipelineConfig
from src.helpers.context import PipelineContext
from src.helpers.diagnostics import DiagnosticsReport
from src.helpers.pipeline_manager import PipelineManager
from src.helpers.repl_runtime import run_step
from src.helpers.schema import POPULATION_ECON_VIEW, SAMPLES_TABLE
from src.helpers.vars import (
    HCR_XLSX_KEY_PREFIX,
    OPENALEX_PAPER_TITLE_LOG_KEY,
    REQUIRED_FILES_CONFIG_KEYS,
    STEP_ADD_ECONOMY_PRIORITY,
    STEP_INFER_NAMES,
    STEP_LOAD_XLSX,
    STEP_REGISTER_RESOURCES,
)
from src.steps import STEP_REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[2]

STEPS_TO_DEVIATION = [
    STEP_REGISTER_RESOURCES,
    STEP_LOAD_XLSX,
    STEP_INFER_NAMES,
    STEP_ADD_ECONOMY_PRIORITY,
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_world_bank_xlsx(path: Path) -> None:
    df = pd.DataFrame(
        [
            ["meta", "meta", "FY26"],
            ["", "Canada", "H"],
            ["", "United States", "H"],
            ["", "Brazil", "UM"],
        ]
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            sheet_name="Country Analytical History",
            index=False,
            header=False,
        )


def _write_hcr_xlsx(path: Path) -> None:
    df = pd.DataFrame(
        {
            "First Name": ["Alice", "Bob", "Carol"],
            "Last Name": ["Smith", "Jones", "Lee"],
            "Category": ["Physics", "Chemistry", "Biology"],
            "Primary Affiliation": [
                "University of Toronto, Canada",
                "University of Sao Paulo, Brazil",
                "Unknown Institute",
            ],
            "Secondary Affiliation": ["", "", ""],
        }
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)


def _write_author_details_parquet(path: Path) -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            f"""
            COPY (
                SELECT
                    'A1' AS authorid,
                    'Alice Smith' AS display_name,
                    '["A. Smith"]' AS display_name_alternatives
            ) TO '{path}' (FORMAT PARQUET)
            """
        )
    finally:
        conn.close()


def _base_config_dict(tmp_path: Path) -> dict[str, object]:
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    hcr_path = data_dir / "2024_HCR.xlsx"
    world_bank_path = data_dir / "OGHIST_2025_07_01.xlsx"
    _write_hcr_xlsx(hcr_path)
    _write_world_bank_xlsx(world_bank_path)

    dummy_dir = data_dir / "dummy"
    dummy_dir.mkdir(parents=True, exist_ok=True)

    files_config: dict[str, dict[str, str]] = {}
    for key in sorted(REQUIRED_FILES_CONFIG_KEYS):
        if key == "world_bank_xlsx":
            files_config[key] = {
                "path": str(world_bank_path),
                "sha256": _sha256(world_bank_path),
                "desc": "World Bank country list",
            }
            continue
        if key == OPENALEX_PAPER_TITLE_LOG_KEY:
            dummy_path = dummy_dir / f"{key}.jsonl"
            dummy_path.write_text("", encoding="utf-8")
            files_config[key] = {
                "path": str(dummy_path),
                "sha256": _sha256(dummy_path),
                "desc": f"Dummy file for {key}",
            }
            continue
        dummy_path = dummy_dir / f"{key}.parquet"
        if key == "author_details":
            _write_author_details_parquet(dummy_path)
        else:
            dummy_path.write_text(f"dummy-{key}", encoding="utf-8")
        files_config[key] = {
            "path": str(dummy_path),
            "sha256": _sha256(dummy_path),
            "desc": f"Dummy file for {key}",
        }

    files_config[f"{HCR_XLSX_KEY_PREFIX}2024"] = {
        "path": str(hcr_path),
        "sha256": _sha256(hcr_path),
        "desc": "HCR XLSX 2024",
    }

    docx_dir = data_dir / "docx"
    docx_dir.mkdir(parents=True, exist_ok=True)

    reference_doc = data_dir / "reference.docx"
    reference_doc.write_text("stub", encoding="utf-8")

    return {
        "files_config": files_config,
        "db_file": str(data_dir / "main_pipeline.duckdb"),
        "state_file": str(data_dir / "main_pipeline_state.json"),
        "output_dir": str(data_dir / "output"),
        "output_format": "txt",
        "pandoc_reference_docx": str(reference_doc),
        "docx_dir": str(docx_dir),
        "timezone": "America/Toronto",
        "sample_seed": 42,
        "sample_draw_sizes": [20] + [40] * 7,
        "pilot_xlsx_name": "2024_HCR.xlsx",
        "total_draws": 310,
        "card_subset_mode": 0,
    }


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    config = _base_config_dict(tmp_path)
    path = tmp_path / "config.detour.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _isolate_hcr_name_cols() -> Generator[None, None, None]:
    from src.helpers.vars import HCR_XLSX_NAME_COLS

    prior = dict(HCR_XLSX_NAME_COLS)
    HCR_XLSX_NAME_COLS.clear()
    try:
        yield
    finally:
        HCR_XLSX_NAME_COLS.clear()
        HCR_XLSX_NAME_COLS.update(prior)


def _noop_log(_: str, __: str = "white") -> None:
    return None


def _ensure_clean_run_files(config: PipelineConfig) -> None:
    if config.db_file.exists():
        config.db_file.unlink()
    if config.state_file.exists():
        config.state_file.unlink()


def _make_context(config: PipelineConfig, diagnostics_dir: Path) -> PipelineContext:
    _ensure_clean_run_files(config)

    manager = PipelineManager(
        state_file=config.state_file,
        db_file=config.db_file,
        duckdb_extensions=config.duckdb_extensions,
    )
    conn = manager.connect_db()
    diagnostics = DiagnosticsReport(diagnostics_dir)
    return PipelineContext(
        config=config,
        manager=manager,
        conn=conn,
        diagnostics=diagnostics,
        interactive=False,
        artifacts_dir=diagnostics_dir / "artifacts",
    )


def _object_schema(conn: duckdb.DuckDBPyConnection, object_name: str) -> list[tuple[str, str]]:
    rows = conn.execute(f'DESCRIBE "{object_name}"').fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _object_frame(conn: duckdb.DuckDBPyConnection, object_name: str) -> pd.DataFrame:
    return conn.execute(f'SELECT * FROM "{object_name}"').df()


def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    null_sentinel = "__DET0UR_NULL_SENTINEL__"
    norm = df.copy()
    for col in norm.columns:
        norm[col] = norm[col].astype("string").fillna(null_sentinel)
    norm = norm.sort_values(by=list(norm.columns), kind="mergesort").reset_index(drop=True)
    return norm


def _assert_object_identical(
    conn_a: duckdb.DuckDBPyConnection,
    conn_b: duckdb.DuckDBPyConnection,
    object_name: str,
) -> None:
    assert _object_schema(conn_a, object_name) == _object_schema(conn_b, object_name)

    frame_a = _normalize_frame(_object_frame(conn_a, object_name))
    frame_b = _normalize_frame(_object_frame(conn_b, object_name))
    pd.testing.assert_frame_equal(frame_a, frame_b, check_dtype=False)


def _object_exists(conn: duckdb.DuckDBPyConnection, object_name: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
        [object_name],
    ).fetchone()
    return bool(row and row[0] > 0)


def _artifact_hashes_for_step(artifacts_dir: Path, step_id: str) -> dict[str, str]:
    files = sorted(artifacts_dir.glob(f"{step_id}_*"))
    return {file.name: _sha256(file) for file in files if file.is_file()}


def _breakdown_block(stdout: str) -> str:
    start = stdout.find("=== Detour Breakdown (Steps 1-4) ===")
    if start == -1:
        return ""
    end = stdout.find("Execution Metrics", start)
    if end == -1:
        return stdout[start:].strip()
    return stdout[start:end].strip()


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", text)


def _parse_snapshot(stdout: str) -> dict[str, object]:
    for line in reversed(stdout.splitlines()):
        if line.startswith("SNAPSHOT::"):
            return json.loads(line.removeprefix("SNAPSHOT::"))
    raise AssertionError(f"Missing SNAPSHOT line in subprocess stdout:\n{stdout}")


def _run_pipeline_subprocess(
    config_path: Path, mode: str
) -> tuple[subprocess.CompletedProcess[str], dict]:
    script = textwrap.dedent(
        """
        import argparse
        import hashlib
        import json
        import sys
        from pathlib import Path

        import duckdb
        import pandas as pd
        from src.helpers.config import PipelineConfig
        from src.helpers.init_pipeline import init_pipeline
        from src.helpers.repl_runtime import run_step
        from src.helpers.vars import (
            STEP_ADD_ECONOMY_PRIORITY,
            STEP_INFER_NAMES,
            STEP_LOAD_XLSX,
            STEP_REGISTER_RESOURCES,
        )
        from src.steps import STEP_REGISTRY

        STEPS = [
            STEP_REGISTER_RESOURCES,
            STEP_LOAD_XLSX,
            STEP_INFER_NAMES,
            STEP_ADD_ECONOMY_PRIORITY,
        ]

        def hash_file(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        def hashes_by_step(artifacts_dir: Path) -> dict[str, dict[str, str]]:
            result: dict[str, dict[str, str]] = {}
            for step_id in STEPS:
                files = sorted(artifacts_dir.glob(f"{step_id}_*"))
                result[step_id] = {
                    file.name: hash_file(file)
                    for file in files
                    if file.is_file()
                }
            return result

        def stable_frame_hash(df: pd.DataFrame) -> str:
            null_sentinel = "__DET0UR_NULL_SENTINEL__"
            if df.empty:
                payload = "__EMPTY__"
            else:
                norm = df.copy()
                for col in norm.columns:
                    norm[col] = norm[col].astype("string").fillna(null_sentinel)
                norm = norm.sort_values(by=list(norm.columns), kind="mergesort").reset_index(
                    drop=True
                )
                payload = norm.to_csv(index=False, lineterminator="\\n")
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()

        def db_objects_snapshot(conn) -> dict[str, dict[str, object]]:
            rows = conn.execute(
                '''
                SELECT table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                '''
            ).fetchall()
            snapshot: dict[str, dict[str, object]] = {}
            for table_name, table_type in rows:
                schema_rows = conn.execute(f'DESCRIBE "{table_name}"').fetchall()
                schema_payload = "\\n".join(
                    f"{str(row[0])}|{str(row[1])}" for row in schema_rows
                )
                frame = conn.execute(f'SELECT * FROM "{table_name}"').df()
                snapshot[str(table_name)] = {
                    "type": str(table_type),
                    "row_count": int(len(frame)),
                    "schema_hash": hashlib.sha256(schema_payload.encode("utf-8")).hexdigest(),
                    "data_hash": stable_frame_hash(frame),
                }
            return snapshot

        mode = sys.argv[1]
        config_path = Path(sys.argv[2])
        config = PipelineConfig.from_json(config_path)

        if mode == "detour":
            from src.detours.detour_step4_breakdown import run_detour

            result = run_detour(config, interactive=False)
            diagnostics_path = Path(str(result.metadata["diagnostics_path"]))
            detour_conn = duckdb.connect(str(result.metadata["detour_db_file"]))
            try:
                db_objects = db_objects_snapshot(detour_conn)
            finally:
                detour_conn.close()
            snapshot = {
                "mode": mode,
                "diagnostics_path": str(diagnostics_path),
                "db_file": str(result.metadata["detour_db_file"]),
                "artifact_hashes_by_step": hashes_by_step(
                    diagnostics_path.parent / "step_artifacts"
                ),
                "db_objects": db_objects,
            }
            print("SNAPSHOT::" + json.dumps(snapshot, sort_keys=True))
            raise SystemExit(0)

        if mode == "main":
            args = argparse.Namespace(
                config=config_path,
                new=True,
                resume=False,
                yes=True,
                non_interactive=True,
                quiet=False,
            )
            init_result = init_pipeline(args, interactive=False, reset_confirmed=True)
            context = init_result.context
            monitor = init_result.monitor
            try:
                for step_id in STEPS:
                    run_step(
                        step_id,
                        STEP_REGISTRY[step_id],
                        context,
                        log=lambda *_args, **_kwargs: None,
                        verbose=True,
                    )
                snapshot = {
                    "mode": mode,
                    "diagnostics_path": str(context.diagnostics.path),
                    "db_file": str(context.config.db_file),
                    "artifact_hashes_by_step": hashes_by_step(
                        context.diagnostics.path.parent / "step_artifacts"
                    ),
                    "db_objects": db_objects_snapshot(context.conn),
                }
                print("SNAPSHOT::" + json.dumps(snapshot, sort_keys=True))
            finally:
                monitor.stop()
                context.manager.close()
            raise SystemExit(0)

        raise ValueError(f"Unknown mode: {mode}")
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, mode, str(config_path)],
        check=False,
        capture_output=True,
        text=True,
        cwd=config_path.parent,
        env={
            **os.environ,
            "PYTHONPATH": (
                str(REPO_ROOT)
                if not os.environ.get("PYTHONPATH")
                else str(REPO_ROOT) + os.pathsep + os.environ["PYTHONPATH"]
            ),
        },
    )
    snapshot = _parse_snapshot(completed.stdout) if completed.returncode == 0 else {}
    return completed, snapshot


def test_detour_contract_entrypoint_isolation_and_db_separation(
    config_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(config_path.parent)

    module_path = REPO_ROOT / "src" / "detours" / "detour_step4_breakdown.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imported_modules.add(name.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    assert "src.cli" not in imported_modules
    assert all(
        not name.startswith("src.detours.") or name == "src.detours.detour_step4_breakdown"
        for name in imported_modules
    )

    config = PipelineConfig.from_json(config_path)
    result = run_detour(config, interactive=False)
    stdout = capsys.readouterr().out
    plain_stdout = _strip_ansi(stdout)

    assert result.success is True
    assert result.steps_completed == DETOUR_STEPS
    assert "Detour Breakdown (Steps 1-4)" in plain_stdout
    assert "Rows by ktp.hcr_filename:" in plain_stdout

    detour_db = Path(str(result.metadata["detour_db_file"]))
    detour_state = Path(str(result.metadata["detour_state_file"]))
    assert detour_db != config.db_file
    assert detour_state != config.state_file
    assert detour_db.exists()
    assert detour_state.exists()

    conn = duckdb.connect(str(detour_db))
    try:
        assert _object_exists(conn, POPULATION_ECON_VIEW)
        assert not _object_exists(conn, SAMPLES_TABLE)
    finally:
        conn.close()


def test_detour_step4_identicality_against_main_per_step(config_path: Path) -> None:
    from src.helpers.vars import HCR_XLSX_NAME_COLS

    main_config = PipelineConfig.from_json(config_path)
    detour_config = main_config.model_copy(
        update={
            "db_file": main_config.db_file.with_name("detour_compare.duckdb"),
            "state_file": main_config.state_file.with_name("detour_compare_state.json"),
        }
    )

    objects_after_step = {
        STEP_REGISTER_RESOURCES: ["registered_resources"],
        STEP_LOAD_XLSX: ["registered_resources", "population"],
        STEP_INFER_NAMES: [
            "registered_resources",
            "population",
            "population_names",
            "population_with_names",
        ],
        STEP_ADD_ECONOMY_PRIORITY: [
            "registered_resources",
            "population",
            "population_names",
            "population_with_names",
            "income_map",
            "population_economy",
            "population_with_names_economy",
        ],
    }

    prior_name_map = dict(HCR_XLSX_NAME_COLS)
    HCR_XLSX_NAME_COLS.clear()

    main_context = _make_context(main_config, config_path.parent / "diag_main")
    detour_context = _make_context(detour_config, config_path.parent / "diag_detour")

    try:
        for step_id in STEPS_TO_DEVIATION:
            main_fn = STEP_REGISTRY.get(step_id)
            detour_fn = STEP_REGISTRY.get(step_id)
            assert main_fn is not None and detour_fn is not None

            run_step(step_id, main_fn, main_context, log=_noop_log, verbose=True)
            run_step(step_id, detour_fn, detour_context, log=_noop_log, verbose=True)

            for object_name in objects_after_step[step_id]:
                _assert_object_identical(main_context.conn, detour_context.conn, object_name)

            # Artifact-level regression guard: for all artifacts produced by the step
            # that should be identical pre-deviation, enforce exact hash equality.
            main_hashes = _artifact_hashes_for_step(main_context.artifacts_dir, step_id)
            detour_hashes = _artifact_hashes_for_step(detour_context.artifacts_dir, step_id)
            assert main_hashes == detour_hashes

        assert _object_exists(main_context.conn, POPULATION_ECON_VIEW)
        assert _object_exists(detour_context.conn, POPULATION_ECON_VIEW)
    finally:
        HCR_XLSX_NAME_COLS.clear()
        HCR_XLSX_NAME_COLS.update(prior_name_map)
        main_context.manager.close()
        detour_context.manager.close()


def test_detour_module_entrypoint_and_reproducibility(config_path: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "src.detours.detour_step4_breakdown",
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

    first = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=config_path.parent,
        env=env,
    )
    assert first.returncode == 0, first.stderr
    assert "Detour Breakdown (Steps 1-4)" in first.stdout
    assert "Running step: 01_register_resources" in first.stdout
    assert "Execution Metrics" in first.stdout

    second = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        cwd=config_path.parent,
        env=env,
    )
    assert second.returncode == 0, second.stderr
    assert _breakdown_block(first.stdout) == _breakdown_block(second.stdout)


def test_pre_deviation_artifact_hash_parity_against_main(config_path: Path) -> None:
    main_run, main_snapshot = _run_pipeline_subprocess(config_path, mode="main")
    assert main_run.returncode == 0, main_run.stderr

    detour_run, detour_snapshot = _run_pipeline_subprocess(config_path, mode="detour")
    assert detour_run.returncode == 0, detour_run.stderr

    assert main_snapshot["artifact_hashes_by_step"] == detour_snapshot["artifact_hashes_by_step"]
    assert main_snapshot["db_objects"] == detour_snapshot["db_objects"]
    assert main_snapshot["db_file"] != detour_snapshot["db_file"]


def _resource_paths_from_config(config_path: Path) -> list[Path]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    paths: list[Path] = []
    files_config = cfg.get("files_config", {})
    for item in files_config.values():
        if isinstance(item, dict) and "path" in item:
            paths.append(Path(str(item["path"])))
    paths.append(Path(str(cfg.get("docx_dir", ""))))
    return [p for p in paths if str(p)]


def _write_slow_config(base_config_path: Path, out_path: Path) -> Path:
    raw = json.loads(base_config_path.read_text(encoding="utf-8"))
    cfg = deepcopy(raw)
    cfg["db_file"] = str(out_path.parent / "slow_main.duckdb")
    cfg["state_file"] = str(out_path.parent / "slow_main_state.json")
    cfg["output_dir"] = str(out_path.parent / "slow_output")
    out_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return out_path


@pytest.mark.slow
def test_slow_real_config_pre_deviation_full_equivalence(tmp_path: Path) -> None:
    base_config = Path("config.repl.json")
    if not base_config.exists():
        pytest.skip("config.repl.json not found.")

    missing_paths = [p for p in _resource_paths_from_config(base_config) if not p.exists()]
    if missing_paths:
        missing_preview = ", ".join(str(path) for path in missing_paths[:5])
        pytest.skip(
            "Real config resources unavailable: " + missing_preview
        )

    slow_config = _write_slow_config(base_config, tmp_path / "config.repl.slow.json")

    main_run, main_snapshot = _run_pipeline_subprocess(slow_config, mode="main")
    assert main_run.returncode == 0, main_run.stderr

    detour_run, detour_snapshot = _run_pipeline_subprocess(slow_config, mode="detour")
    assert detour_run.returncode == 0, detour_run.stderr

    assert main_snapshot["artifact_hashes_by_step"] == detour_snapshot["artifact_hashes_by_step"]
    assert main_snapshot["db_objects"] == detour_snapshot["db_objects"]
    assert main_snapshot["db_file"] != detour_snapshot["db_file"]
