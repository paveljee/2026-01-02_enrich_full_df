from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import register_frame
from ..helpers.resources import (
    PipelineResources,
    configured_hcr_xlsx_paths,
    discover_docx_files,
    register_pipeline_resources,
)
from ..helpers.schema import REGISTERED_RESOURCES_TABLE
from ..helpers.vars import STEP_REGISTER_RESOURCES


def _resource_registry_frame(resources: PipelineResources) -> pd.DataFrame:
    all_resources = (
        list(resources.parquet_resources.values())
        + list(resources.xlsx_resources.values())
        + [resources.world_bank_resource]
        + list(resources.docx_resources.values())
    )
    all_resources.append(resources.openalex_author_search_log_resource)
    all_resources.append(resources.openalex_paper_title_log_resource)
    rows = [
        {
            "resource_name": res.name,
            "resource_hash": res.hash,
            "resource_group": res.group.value,
            "fragment_type": res.fragment_type.value,
            "resource_description": res.description,
            "resource_url": str(res.url) if res.url is not None else None,
        }
        for res in all_resources
    ]
    return pd.DataFrame(rows)


def run(context: PipelineContext) -> StepResult:
    xlsx_files = configured_hcr_xlsx_paths(context.config)
    if not xlsx_files:
        raise FileNotFoundError("No configured HCR XLSX files found in files_config.")

    docx_files = discover_docx_files(context.config.docx_dir)

    def log(message: str) -> None:
        if context.log is not None:
            context.log(message, "cyan")

    resources = register_pipeline_resources(
        context.config,
        conn=context.conn,
        log=log,
    )
    context.resources = resources
    resources_df = _resource_registry_frame(resources)
    register_frame(context.conn, "registered_resources_frame", resources_df)
    context.conn.execute(
        f"""
        CREATE OR REPLACE TABLE {REGISTERED_RESOURCES_TABLE} AS
        SELECT * FROM registered_resources_frame
        """
    )
    context.conn.execute("DROP TABLE IF EXISTS registered_resources_frame")

    xlsx_names = [path.name for path in xlsx_files if not path.name.startswith("~$")]
    docx_names = [path.name for path in docx_files]
    parquet_names = list(resources.parquet_resources.keys())

    messages = [
        f"Registered XLSX resources: {len(xlsx_names)}",
        f"Registered DOCX resources: {len(docx_names)}",
        f"Registered parquet resources: {len(parquet_names)}",
    ]
    messages.extend(resources.messages)

    diagnostics = [
        f"XLSX files: {len(xlsx_names)}",
        f"DOCX files: {len(docx_names)}",
        f"Parquet files: {len(parquet_names)}",
    ]
    diagnostics.extend(resources.messages)
    if xlsx_names:
        diagnostics.append(f"Example XLSX: {', '.join(xlsx_names[:5])}")
    if docx_names:
        diagnostics.append(f"Example DOCX: {', '.join(docx_names[:5])}")
    if parquet_names:
        diagnostics.append(f"Example parquet: {', '.join(parquet_names[:5])}")

    return StepResult(
        step_id=STEP_REGISTER_RESOURCES,
        artifacts={
            "xlsx_files": [Path(p) for p in xlsx_files],
            "docx_files": [Path(p) for p in docx_files],
        },
        messages=messages,
        diagnostics=diagnostics,
    )
