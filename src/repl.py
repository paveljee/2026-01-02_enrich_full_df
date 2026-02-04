from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

import pandas as pd
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from .data_models import OuterDict
from .helpers import init_pipeline
from .helpers.context import PipelineContext, StepResult
from .helpers.step_ids import STEP_BUILD_CARDS
from .steps import STEP_REGISTRY

console = Console()


def _confirm_reset(interactive: bool) -> bool:
    if not interactive:
        return False
    response = console.input("Reset pipeline state and database? [y/N] ").strip().lower()
    return response == "y"


def _dump_artifacts(context: PipelineContext, step_id: str, artifacts: dict) -> list[Path]:
    dumped: list[Path] = []
    context.artifacts_dir.mkdir(parents=True, exist_ok=True)

    parquet_names = artifacts.get("parquet_view_names")
    parquet_dfs = artifacts.get("parquet_match_dfs")
    if isinstance(parquet_names, list) and isinstance(parquet_dfs, list) and len(parquet_names) == len(parquet_dfs):
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


def _run_step(
    step_id: str,
    step_fn,
    context: PipelineContext,
    *,
    log,
    verbose: bool,
) -> StepResult:
    if context.manager.is_done(step_id):
        return StepResult(step_id=step_id, messages=[f"Skipped {step_id} (already done)."])

    log(f"Running step: {step_id}", style="cyan")
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

    dumped = _dump_artifacts(context, step_id, result.artifacts)
    if dumped:
        result.messages.append(f"Artifacts dumped: {', '.join(str(p) for p in dumped[:5])}")
        if len(dumped) > 5:
            result.messages.append(f"...and {len(dumped) - 5} more artifact files.")
    return result


def run_pipeline(args: argparse.Namespace) -> Path | None:
    interactive = not args.non_interactive
    reset_confirmed = args.yes or _confirm_reset(interactive) if args.new else False

    init_result = init_pipeline(
        args,
        interactive=interactive,
        reset_confirmed=reset_confirmed,
    )
    context = init_result.context
    steps_to_run = init_result.steps_to_run
    monitor = init_result.monitor

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["header"].update(Panel("KTP Pipeline", style="bold white on blue"))
    layout["footer"].update(Panel("Running steps", style="italic grey50"))

    live: Live | None = None
    zip_path: Path | None = None
    card_count: int | None = None

    def log(msg: str, style: str = "white") -> None:
        if interactive:
            layout["body"].update(Panel(msg, style=style, title="Current Task"))
        else:
            console.print(f"[{style}]{msg}[/{style}]")

    context.log = log

    try:
        if interactive:
            live = Live(layout, refresh_per_second=4, console=console, transient=True)
            live.start()

        for step_id in steps_to_run:
            step_fn = STEP_REGISTRY.get(step_id)
            if step_fn is None:
                raise ValueError(f"Unknown step: {step_id}")
            result = _run_step(step_id, step_fn, context, log=log, verbose=not args.quiet)
            for line in result.messages:
                log(line, style="green")
            if step_id == STEP_BUILD_CARDS:
                zip_path = result.artifacts.get("zip_path")
                cards = result.artifacts.get("cards")
                if isinstance(cards, dict):
                    card_count = len(cards)
    finally:
        if live is not None:
            live.stop()
        peak_ram = monitor.stop()
        context.manager.close()

    m_table = Table(title="Execution Metrics", box=box.SIMPLE)
    m_table.add_column("Metric", style="cyan")
    m_table.add_column("Value", style="magenta")
    m_table.add_row("Peak RAM Usage", f"{peak_ram:.2f} GB")
    if card_count is not None:
        m_table.add_row("Cards", str(card_count))
    console.print(m_table)
    console.print(f"[bold cyan]Diagnostics report saved to: {context.diagnostics.path}[/bold cyan]")

    if zip_path is not None:
        console.print(f"[bold green]Success! Output saved to: {zip_path}[/bold green]")
    return zip_path


def signal_handler(sig, frame) -> None:
    console.print("\n[bold red]Process Interrupted![/bold red]")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="KTP pipeline runner.")
    parser.add_argument("--config", type=Path, required=True, help="Path to JSON config file.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--new", action="store_true", help="Start a new pipeline run.")
    mode.add_argument("--resume", action="store_true", help="Resume from the last saved step.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm reset when starting a new pipeline (non-interactive).",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable the rich live UI and print log lines instead.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce diagnostic output (still writes report file).",
    )
    args = parser.parse_args()

    try:
        run_pipeline(args)
    except Exception:
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    main()
