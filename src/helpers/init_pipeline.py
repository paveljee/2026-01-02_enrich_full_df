from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import PipelineConfig
from .context import PipelineContext
from .data_models import NameKey, OuterDict
from .diagnostics import DiagnosticsReport
from .duckdb_utils import append_innerdicts_from_jsonlines_table
from .pipeline_manager import PipelineManager
from .procedures import DocxMatchProcedure, ParquetMatchProcedure, XlsxMatchProcedure
from .resource_monitor import ResourceMonitor
from .resources import PipelineResources, register_pipeline_resources
from .schema import (
    DOCX_INNERDICT_TABLE,
    OUTERDICT_NAME_VIEW,
    OUTERDICT_STUB_TABLE,
    PARQUET_INNERDICT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from .vars import (
    KTP_NAMEKEY_COL,
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
        "registered_resources",
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
        "card_partitions",
        "card_partition_review_rows",
    ]
    views = [
        "population_with_names",
        "population_with_names_economy",
        "samples_with_context",
        "samples_with_names",
        OUTERDICT_NAME_VIEW,
        "xlsx_matches",
        "xlsx_output",
        "docx_matches",
        "docx_output",
        "card_partition_review",
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
    rows = conn.execute(
        f'SELECT "{KTP_NAMEKEY_COL}" FROM {table_name}'
    ).fetchall()
    name_keys = [NameKey.from_json_key(row[0]) for row in rows]
    return OuterDict.from_name_keys(name_keys)


def init_pipeline(
    args: argparse.Namespace,
    *,
    interactive: bool,
    reset_confirmed: bool,
) -> InitResult:
    if not args.config:
        raise ValueError("A JSON config file is required. Use --config <path>.")

    config = PipelineConfig.from_json(Path(args.config))
    manager = PipelineManager(
        config.state_file,
        config.db_file,
        duckdb_extensions=config.duckdb_extensions,
    )
    conn = manager.connect_db()
    monitor = ResourceMonitor()
    monitor.start()

    try:
        if args.new:
            if not reset_confirmed:
                raise ValueError("Pipeline reset confirmation required for --new.")
            _reset_pipeline(conn, manager)

        session_stamp = None
        if args.new:
            session_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            manager.set_session_dir(session_stamp)
        else:
            session_stamp = manager.get_session_dir()
            if session_stamp is None:
                session_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                manager.set_session_dir(session_stamp)

        diagnostics_dir = Path("data/diagnostics") / session_stamp
        diagnostics = DiagnosticsReport(diagnostics_dir)

        steps_to_run = STEP_ORDER if args.new else [s for s in STEP_ORDER if not manager.is_done(s)]

        resources: PipelineResources | None = None
        if manager.is_done(STEP_REGISTER_RESOURCES):
            resources = register_pipeline_resources(config, conn=conn)

        outer_dict: OuterDict | None = None
        if manager.is_done(STEP_BUILD_OUTERDICT):
            outer_dict = _load_outerdict_stub(conn, table_name=OUTERDICT_STUB_TABLE)
            if resources is None:
                resources = register_pipeline_resources(config, conn=conn)
            if manager.is_done(STEP_MATCH_XLSX):
                append_innerdicts_from_jsonlines_table(
                    conn,
                    table_name=XLSX_INNERDICT_TABLE,
                    outer_dict=outer_dict,
                    procedure=XlsxMatchProcedure(),
                )
            if manager.is_done(STEP_MATCH_DOCX):
                append_innerdicts_from_jsonlines_table(
                    conn,
                    table_name=DOCX_INNERDICT_TABLE,
                    outer_dict=outer_dict,
                    procedure=DocxMatchProcedure(),
                )
            if manager.is_done(STEP_MATCH_PARQUET):
                append_innerdicts_from_jsonlines_table(
                    conn,
                    table_name=PARQUET_INNERDICT_TABLE,
                    outer_dict=outer_dict,
                    procedure=ParquetMatchProcedure(),
                )

        context = PipelineContext(
            config=config,
            manager=manager,
            conn=conn,
            diagnostics=diagnostics,
            interactive=interactive,
            artifacts_dir=_artifact_dir(diagnostics_dir),
            resources=resources,
            outer_dict=outer_dict,
        )
        return InitResult(context=context, steps_to_run=steps_to_run, monitor=monitor)
    except Exception:
        monitor.stop()
        manager.close()
        raise
