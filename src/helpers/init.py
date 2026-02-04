from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .config import PipelineConfig
from .context import PipelineContext
from .data_models import InnerDict, NameKey, OuterDict
from .diagnostics import DiagnosticsReport
from .jsonlines import loads_jsonlines
from .pipeline_manager import PipelineManager
from .procedures import DocxMatchProcedure, ParquetMatchProcedure, XlsxMatchProcedure
from .resource_monitor import ResourceMonitor
from .resources import PipelineResources, register_pipeline_resources
from .schema import (
    DOCX_INNERDICT_TABLE,
    OUTERDICT_STUB_TABLE,
    PARQUET_AUTHOR_OUTPUT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from .step_ids import (
    STEP_BUILD_OUTERDICT,
    STEP_MATCH_DOCX,
    STEP_MATCH_PARQUET,
    STEP_MATCH_XLSX,
    STEP_ORDER,
    STEP_REGISTER_RESOURCES,
)


@dataclass
class InitResult:
    context: PipelineContext
    steps_to_run: list[str]
    monitor: ResourceMonitor


def _artifact_dir(base: Path) -> Path:
    return base / "step_artifacts"


def _reset_pipeline(conn, manager: PipelineManager) -> None:
    tables = [
        "population",
        "population_names",
        "population_economy",
        "samples",
        "outerdict_stub",
        "xlsx_innerdicts",
        "docx_rows",
        "docx_innerdicts",
        "ssn_author_matches",
        "ssn_innerdicts",
    ]
    views = [
        "population_with_names",
        "population_with_names_economy",
        "samples_with_context",
        "samples_with_names",
        "outerdict_name_keys",
        "xlsx_matches",
        "xlsx_output",
        "docx_matches",
        "docx_output",
    ]
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    for view in views:
        conn.execute(f"DROP VIEW IF EXISTS {view}")

    # Drop any parquet-derived tables/views from prior runs.
    # Get all tables and views with their types
    objects = conn.execute("""
        SELECT table_name, table_type 
        FROM information_schema.tables
        WHERE table_name LIKE 'ssn_%'
    """).fetchall()
    for table_name, table_type in objects:
        if table_type == 'BASE TABLE':
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        elif table_type == 'VIEW':
            conn.execute(f"DROP VIEW IF EXISTS {table_name}")
    manager.reset_state()


def _load_outerdict_stub(conn, table_name: str) -> OuterDict:
    rows = conn.execute(f"SELECT name_key FROM {table_name}").fetchall()
    name_keys = [NameKey.from_json_key(row[0]) for row in rows]
    return OuterDict.from_name_keys(name_keys)


def _append_innerdicts_from_table(
    conn,
    *,
    table_name: str,
    outer_dict: OuterDict,
    procedure,
) -> None:
    rows = conn.execute(f"SELECT name_key, innerdicts FROM {table_name}").fetchall()
    for name_key, payload in rows:
        for record in loads_jsonlines(payload or ""):
            inner = InnerDict.from_mapping(record, procedure)
            outer_dict.add_inner_by_key(str(name_key), inner)


def _append_innerdicts_from_rows_table(
    conn,
    *,
    table_name: str,
    outer_dict: OuterDict,
    procedure,
) -> None:
    rel = conn.execute(f"SELECT * FROM {table_name}")
    cols = [desc[0] for desc in rel.description]
    try:
        name_idx = cols.index("name_key")
    except ValueError as exc:
        raise ValueError(f"Missing name_key column in {table_name}") from exc
    while True:
        rows = rel.fetchmany(5000)
        if not rows:
            break
        for row in rows:
            record = {col: row[i] for i, col in enumerate(cols) if i != name_idx}
            inner = InnerDict.from_mapping(record, procedure)
            outer_dict.add_inner_by_key(str(row[name_idx]), inner)


def init_pipeline(
    args: argparse.Namespace,
    *,
    interactive: bool,
    reset_confirmed: bool,
) -> InitResult:
    if not args.config:
        raise ValueError("A JSON config file is required. Use --config <path>.")

    config = PipelineConfig.from_json(Path(args.config))
    diagnostics = DiagnosticsReport(Path("data/diagnostics"))
    manager = PipelineManager(config.state_file, config.db_file)
    conn = manager.connect_db()

    monitor = ResourceMonitor()
    monitor.start()

    if args.new:
        if not reset_confirmed:
            raise ValueError("Pipeline reset confirmation required for --new.")
        _reset_pipeline(conn, manager)

    steps_to_run = STEP_ORDER if args.new else [s for s in STEP_ORDER if not manager.is_done(s)]

    resources: PipelineResources | None = None
    if manager.is_done(STEP_REGISTER_RESOURCES):
        resources = register_pipeline_resources(config)

    outer_dict: OuterDict | None = None
    if manager.is_done(STEP_BUILD_OUTERDICT):
        outer_dict = _load_outerdict_stub(conn, table_name=OUTERDICT_STUB_TABLE)
        if resources is None:
            resources = register_pipeline_resources(config)
        if manager.is_done(STEP_MATCH_XLSX):
            _append_innerdicts_from_table(
                conn,
                table_name=XLSX_INNERDICT_TABLE,
                outer_dict=outer_dict,
                procedure=XlsxMatchProcedure(),
            )
        if manager.is_done(STEP_MATCH_DOCX):
            _append_innerdicts_from_table(
                conn,
                table_name=DOCX_INNERDICT_TABLE,
                outer_dict=outer_dict,
                procedure=DocxMatchProcedure(),
            )
        if manager.is_done(STEP_MATCH_PARQUET):
            _append_innerdicts_from_rows_table(
                conn,
                table_name=PARQUET_AUTHOR_OUTPUT_TABLE,
                outer_dict=outer_dict,
                procedure=ParquetMatchProcedure(),
            )

    context = PipelineContext(
        config=config,
        manager=manager,
        conn=conn,
        diagnostics=diagnostics,
        interactive=interactive,
        artifacts_dir=_artifact_dir(Path("data/diagnostics")),
        resources=resources,
        outer_dict=outer_dict,
    )
    return InitResult(context=context, steps_to_run=steps_to_run, monitor=monitor)
