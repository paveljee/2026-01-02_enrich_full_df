from __future__ import annotations

from pathlib import Path

from ..helpers.context import PipelineContext, StepResult
from ..helpers.resources import (
    discover_docx_files,
    discover_xlsx_files,
    register_pipeline_resources,
)
from ..helpers.vars import STEP_REGISTER_RESOURCES


def run(context: PipelineContext) -> StepResult:
    xlsx_files = [
        p
        for p in discover_xlsx_files(context.config.xlsx_dir)
        if not p.name.startswith("~$")
    ]
    if not xlsx_files:
        raise FileNotFoundError(f"No XLSX files found in {context.config.xlsx_dir}")

    docx_files = discover_docx_files(context.config.docx_dir)

    resources = register_pipeline_resources(context.config)
    context.resources = resources

    xlsx_names = [path.name for path in xlsx_files if not path.name.startswith("~$")]
    docx_names = [path.name for path in docx_files]
    parquet_names = list(resources.parquet_resources.keys())

    messages = [
        f"Registered XLSX resources: {len(xlsx_names)}",
        f"Registered DOCX resources: {len(docx_names)}",
        f"Registered parquet resources: {len(parquet_names)}",
    ]

    diagnostics = [
        f"XLSX files: {len(xlsx_names)}",
        f"DOCX files: {len(docx_names)}",
        f"Parquet files: {len(parquet_names)}",
    ]
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
