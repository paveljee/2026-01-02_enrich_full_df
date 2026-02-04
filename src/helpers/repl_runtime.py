from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from .context import PipelineContext, StepResult
from .data_models import OuterDict


def dump_artifacts(context: PipelineContext, step_id: str, artifacts: dict) -> list[Path]:
    dumped: list[Path] = []
    context.artifacts_dir.mkdir(parents=True, exist_ok=True)

    parquet_names = artifacts.get("parquet_view_names")
    parquet_dfs = artifacts.get("parquet_match_dfs")
    if (
        isinstance(parquet_names, list)
        and isinstance(parquet_dfs, list)
        and len(parquet_names) == len(parquet_dfs)
    ):
        for view_name, df in zip(parquet_names, parquet_dfs):
            if isinstance(df, pd.DataFrame):
                path = context.artifacts_dir / f"{step_id}_{view_name}.csv"
                df.to_csv(path, index=False)
                dumped.append(path)

    for name, artifact in artifacts.items():
        if name in {"parquet_view_names", "parquet_match_dfs"}:
            continue
        if isinstance(artifact, pd.DataFrame):
            path = context.artifacts_dir / f"{step_id}_{name}.csv"
            artifact.to_csv(path, index=False)
            dumped.append(path)
        elif isinstance(artifact, list) and all(isinstance(x, pd.DataFrame) for x in artifact):
            for idx, df in enumerate(artifact):
                path = context.artifacts_dir / f"{step_id}_{name}_{idx}.csv"
                df.to_csv(path, index=False)
                dumped.append(path)
        elif isinstance(artifact, OuterDict):
            path = context.artifacts_dir / f"{step_id}_{name}.json"
            artifact.dump_json(path)
            dumped.append(path)
        elif isinstance(artifact, Path):
            dumped.append(artifact)
    return dumped


def run_step(
    step_id: str,
    step_fn: Callable[[PipelineContext], StepResult],
    context: PipelineContext,
    *,
    log: Callable[[str, str], None],
    verbose: bool,
) -> StepResult:
    if context.manager.is_done(step_id):
        return StepResult(step_id=step_id, messages=[f"Skipped {step_id} (already done)."])

    log(f"Running step: {step_id}", "cyan")
    context.conn.execute("BEGIN")
    try:
        result: StepResult = step_fn(context)
        context.conn.execute("COMMIT")
        context.manager.save_state(step_id)
    except Exception as exc:
        context.conn.execute("ROLLBACK")
        context.diagnostics.add_section(
            f"{step_id} (failed)",
            [f"{type(exc).__name__}: {exc}"],
        )
        raise

    if verbose and result.diagnostics:
        context.diagnostics.add_section(step_id, result.diagnostics)
    elif verbose and result.messages:
        context.diagnostics.add_section(step_id, result.messages)

    dumped = dump_artifacts(context, step_id, result.artifacts)
    if dumped:
        result.messages.append(f"Artifacts dumped: {', '.join(str(p) for p in dumped[:5])}")
        if len(dumped) > 5:
            result.messages.append(f"...and {len(dumped) - 5} more artifact files.")
    return result


__all__ = ["dump_artifacts", "run_step"]
