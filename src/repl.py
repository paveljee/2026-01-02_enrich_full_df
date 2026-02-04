from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .helpers import init_pipeline
from .helpers.repl_runtime import run_step
from .helpers.step_ids import STEP_BUILD_CARDS
from .steps import STEP_REGISTRY

console = Console()


def run_reproduction(args: argparse.Namespace) -> Path | None:
    interactive = not args.non_interactive
    reset_confirmed = False

    if args.new:
        if args.yes:
            reset_confirmed = True
        elif interactive:
            response = console.input(
                "Reset pipeline state and database? [y/N] ",
                markup=False,
            ).strip().lower()
            reset_confirmed = response == "y"
        else:
            reset_confirmed = False

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

    log_history: list[tuple[str, str]] = []
    session_log_path = context.diagnostics.path.parent / "repl_session.log"
    if args.new and reset_confirmed and session_log_path.exists():
        session_log_path.unlink()

    if session_log_path.exists():
        for line in session_log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                style, msg = line.split("\t", 1)
            else:
                style, msg = "white", line
            log_history.append((style, msg))

    def render_history() -> Text:
        text = Text()
        for style, msg in log_history:
            text.append(msg, style=style)
            text.append("\n")
        return text

    def log(msg: str, style: str = "white") -> None:
        session_log_path.parent.mkdir(parents=True, exist_ok=True)
        with session_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{style}\t{msg}\n")
        if interactive:
            log_history.append((style, msg))
            layout["body"].update(Panel(render_history(), title="Current Task"))
        else:
            console.print(f"[{style}]{msg}[/{style}]")

    context.log = log

    try:
        if interactive:
            if log_history:
                layout["body"].update(
                    Panel(render_history(), title="Current Task")
                )
            live = Live(
                renderable=layout,
                refresh_per_second=4,
                console=console,
                transient=False,
            )
            live.start()

        if args.resume:
            if not args.yes:
                if interactive:
                    if live is not None:
                        live.stop()
                    layout["footer"].update(Panel("Resume pipeline from next step? [y/N]"))
                    console.print("Resume pipeline from next step? [y/N]", markup=False)
                    response = console.input("> ", markup=False).strip().lower()
                    layout["footer"].update(Panel("Running steps", style="italic grey50"))
                    if live is not None:
                        live.start()
                    if response != "y":
                        return zip_path
                else:
                    console.print(
                        "[yellow]Resume requested without --yes; showing last session report and exiting.[/yellow]"
                    )
                    console.print(
                        f"[bold cyan]Diagnostics report saved to: {context.diagnostics.path}[/bold cyan]"
                    )
                    return zip_path

        for step_id in steps_to_run:
            step_fn = STEP_REGISTRY.get(step_id)
            if step_fn is None:
                raise ValueError(f"Unknown step: {step_id}")
            result = run_step(step_id, step_fn, context, log=log, verbose=not args.quiet)
            for line in result.messages:
                log(line, style="green")
            if step_id == STEP_BUILD_CARDS:
                zip_path = result.artifacts.get("zip_path")
                cards = result.artifacts.get("cards")
                if isinstance(cards, dict):
                    card_count = len(cards)
            if interactive:
                if live is not None:
                    live.stop()
                layout["footer"].update(Panel("Continue to next step? [y/N]"))
                console.print("Continue to next step? [y/N]", markup=False)
                response = console.input("> ", markup=False).strip().lower()
                layout["footer"].update(Panel("Running steps", style="italic grey50"))
                if live is not None:
                    live.start()
                if response != "y":
                    break
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
        run_reproduction(args)
    except KeyboardInterrupt:
        console.print("\n[bold red]Process Interrupted![/bold red]")
        sys.exit(130)
    except Exception:
        console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    main()
