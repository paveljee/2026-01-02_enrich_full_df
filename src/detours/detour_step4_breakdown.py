from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from src.helpers.config import PipelineConfig
from src.helpers.init_pipeline import init_pipeline
from src.helpers.repl_runtime import run_step
from src.helpers.schema import POPULATION_ECON_VIEW
from src.helpers.vars import (
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_FIRST_NAME_COL,
    KTP_HCR_FILENAME_COL,
    KTP_LAST_NAME_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    STEP_ADD_ECONOMY_PRIORITY,
    STEP_INFER_NAMES,
    STEP_LOAD_XLSX,
    STEP_REGISTER_RESOURCES,
)
from src.steps import STEP_REGISTRY

console = Console()

DETOUR_ID = "step4-breakdown"
DETOUR_NAME = "Step 4 Breakdown"
DETOUR_DESCRIPTION = (
    "Run steps 1-4 identically to main flow, then print a comprehensive data breakdown."
)
DETOUR_STEPS = [
    STEP_REGISTER_RESOURCES,
    STEP_LOAD_XLSX,
    STEP_INFER_NAMES,
    STEP_ADD_ECONOMY_PRIORITY,
]


@dataclass
class DetourResult:
    success: bool
    steps_completed: list[str]
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _detour_db_path(path: Path) -> Path:
    suffix = path.suffix or ".duckdb"
    stem = path.stem if path.suffix else path.name
    return path.with_name(f"{stem}__detour_{DETOUR_ID}{suffix}")


def _detour_state_path(path: Path) -> Path:
    suffix = path.suffix or ".json"
    stem = path.stem if path.suffix else path.name
    return path.with_name(f"{stem}__detour_{DETOUR_ID}{suffix}")


def _detourized_config(config: PipelineConfig) -> PipelineConfig:
    return config.model_copy(
        update={
            "db_file": _detour_db_path(config.db_file),
            "state_file": _detour_state_path(config.state_file),
        }
    )


def _serialize_config(path: Path, config: PipelineConfig) -> None:
    path.write_text(json.dumps(config.model_dump(mode="json"), indent=2), encoding="utf-8")


def _breakdown(conn) -> tuple[list[str], dict[str, Any]]:
    total_rows = int(conn.execute(f"SELECT COUNT(*) FROM {POPULATION_ECON_VIEW}").fetchone()[0])

    per_file_df = conn.execute(
        f'''
        SELECT "{KTP_HCR_FILENAME_COL}" AS filename, COUNT(*) AS row_count
        FROM {POPULATION_ECON_VIEW}
        GROUP BY 1
        ORDER BY 1
        '''
    ).df()
    per_file = per_file_df.to_dict(orient="records")

    key_cols = [
        KTP_FIRST_NAME_COL,
        KTP_LAST_NAME_COL,
        KTP_ECONOMIES_COL,
        KTP_PRIORITY_COL,
        KTP_PRIORITY_GROUP_COL,
    ]
    null_stats: list[dict[str, Any]] = []
    for col in key_cols:
        row = conn.execute(
            f'''
            SELECT
                SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END) AS null_count,
                SUM(CASE WHEN TRIM(CAST(COALESCE("{col}", '') AS VARCHAR)) = '' THEN 1 ELSE 0 END)
                    AS empty_count
            FROM {POPULATION_ECON_VIEW}
            '''
        ).fetchone()
        null_stats.append(
            {
                "column": col,
                "null_count": int(row[0]),
                "empty_count": int(row[1]),
            }
        )

    priority_df = conn.execute(
        f'''
        SELECT "{KTP_PRIORITY_COL}" AS priority, COUNT(*) AS row_count
        FROM {POPULATION_ECON_VIEW}
        GROUP BY 1
        ORDER BY 1
        '''
    ).df()
    priority_dist = priority_df.to_dict(orient="records")

    priority_group_df = conn.execute(
        f'''
        SELECT "{KTP_PRIORITY_GROUP_COL}" AS priority_group, COUNT(*) AS row_count
        FROM {POPULATION_ECON_VIEW}
        GROUP BY 1
        ORDER BY 1
        '''
    ).df()
    priority_group_dist = priority_group_df.to_dict(orient="records")

    income_group_df = conn.execute(
        f'''
        SELECT "{KTP_ECONOMIES_INCOME_GROUP_COL}" AS income_group, COUNT(*) AS row_count
        FROM {POPULATION_ECON_VIEW}
        GROUP BY 1
        ORDER BY 1
        '''
    ).df()
    income_group_dist = income_group_df.to_dict(orient="records")

    name_pair_expr = (
        f"COALESCE(\"{KTP_FIRST_NAME_COL}\", '') || '||' || "
        f"COALESCE(\"{KTP_LAST_NAME_COL}\", '')"
    )
    uniqueness_row = conn.execute(
        f'''
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT {name_pair_expr}) AS unique_name_pairs
        FROM {POPULATION_ECON_VIEW}
        '''
    ).fetchone()
    total_for_unique = int(uniqueness_row[0])
    unique_names = int(uniqueness_row[1])
    duplicate_rows = total_for_unique - unique_names

    metadata: dict[str, Any] = {
        "total_rows": total_rows,
        "rows_by_filename": per_file,
        "null_or_empty_stats": null_stats,
        "priority_distribution": priority_dist,
        "priority_group_distribution": priority_group_dist,
        "income_group_distribution": income_group_dist,
        "integrity": {
            "total_rows": total_for_unique,
            "unique_name_pairs": unique_names,
            "duplicate_name_rows": duplicate_rows,
        },
    }

    lines = [
        "=== Detour Breakdown (Steps 1-4) ===",
        f"Total rows: {total_rows}",
        "",
        "Rows by ktp.hcr_filename:",
    ]
    for row in per_file:
        lines.append(f"- {row['filename']}: {row['row_count']}")

    lines.append("")
    lines.append("Null/empty stats:")
    for row in null_stats:
        lines.append(
            f"- {row['column']}: null={row['null_count']}, empty={row['empty_count']}"
        )

    lines.append("")
    lines.append("Priority distribution:")
    for row in priority_dist:
        lines.append(f"- {row['priority']}: {row['row_count']}")

    lines.append("")
    lines.append("Priority group distribution:")
    for row in priority_group_dist:
        lines.append(f"- {row['priority_group']}: {row['row_count']}")

    lines.append("")
    lines.append("Income group distribution:")
    for row in income_group_dist:
        lines.append(f"- {row['income_group']}: {row['row_count']}")

    lines.append("")
    lines.append("Integrity summary:")
    lines.append(f"- Unique name pairs: {unique_names}")
    lines.append(f"- Duplicate name rows: {duplicate_rows}")

    return lines, metadata


def run_detour(
    config: PipelineConfig,
    interactive: bool = True,
    diagnostics: Any = None,
) -> DetourResult:
    del diagnostics

    detour_config = _detourized_config(config)
    detour_config.db_file.parent.mkdir(parents=True, exist_ok=True)
    detour_config.state_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        config_path = Path(handle.name)
    _serialize_config(config_path, detour_config)

    args = argparse.Namespace(
        config=config_path,
        new=True,
        resume=False,
        yes=True,
        non_interactive=not interactive,
        quiet=False,
    )

    init_result = init_pipeline(args, interactive=interactive, reset_confirmed=True)
    context = init_result.context
    monitor = init_result.monitor

    steps_completed: list[str] = []

    def _log(message: str, style: str = "white") -> None:
        console.print(f"[{style}]{message}[/{style}]")

    context.log = _log

    peak_ram = 0.0
    detour_result: DetourResult | None = None
    try:
        for step_id in DETOUR_STEPS:
            step_fn = STEP_REGISTRY.get(step_id)
            if step_fn is None:
                raise ValueError(f"Unknown step: {step_id}")
            result = run_step(step_id, step_fn, context, log=_log, verbose=True)
            for line in result.messages:
                _log(line, style="green")
            steps_completed.append(step_id)

        lines, metadata = _breakdown(context.conn)
        for line in lines:
            _log(line)

        metadata["detour_db_file"] = str(detour_config.db_file)
        metadata["detour_state_file"] = str(detour_config.state_file)
        metadata["diagnostics_path"] = str(context.diagnostics.path)
        metadata["steps_completed"] = list(steps_completed)

        detour_result = DetourResult(
            success=True,
            steps_completed=steps_completed,
            summary=(
                "Completed detour through step 4 with strict main-step equivalence "
                "and emitted comprehensive breakdown."
            ),
            metadata=metadata,
        )
    except Exception as exc:
        _log(f"Exited prematurely: {type(exc).__name__}: {exc}", style="red")
        raise
    finally:
        peak_ram = monitor.stop()
        context.manager.close()
        if config_path.exists():
            config_path.unlink()

    if detour_result is None:
        raise RuntimeError("Detour did not produce a result.")

    m_table = Table(title="Execution Metrics", box=box.SIMPLE)
    m_table.add_column("Metric", style="cyan")
    m_table.add_column("Value", style="magenta")
    m_table.add_row("Peak RAM Usage", f"{peak_ram:.2f} GB")
    console.print(m_table)
    _log("Execution Metrics", style="cyan")
    _log(f"Peak RAM Usage: {peak_ram:.2f} GB", style="magenta")
    _log(f"Diagnostics report saved to: {context.diagnostics.path}", style="cyan")

    return detour_result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run detour that executes steps 1-4 then prints a data breakdown."
    )
    parser.add_argument("--config", type=Path, required=True, help="Path to JSON config file.")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable rich-styled CLI output formatting.",
    )
    args = parser.parse_args()

    try:
        config = PipelineConfig.from_json(args.config)
        result = run_detour(config, interactive=not args.non_interactive)
        if not result.success:
            raise RuntimeError(result.summary)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        raise


if __name__ == "__main__":
    main()
