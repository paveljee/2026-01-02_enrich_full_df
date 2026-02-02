from __future__ import annotations

import argparse
import json
import signal
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import psutil
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from ._vars import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    KTP_ECONOMIES_COL,
    KTP_FILENAME_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_SOURCE_KEY_COL,
)
from .cards import build_cards, write_cards_zip
from .config import PipelineConfig
from .data_models import FragmentType, RegisteredResource, ResourceGroup
from .hcr_xlsx.indexer import index_samples
from .hcr_xlsx.loader import build_population_table
from .hcr_xlsx.matcher import match_population
from .hcr_xlsx.preprocessor import load_high_income_economies
from .hcr_xlsx.sampler import sample_pilot, sample_population
from .manual_docx.loader import load_docx_tables
from .manual_docx.matcher import match_docx
from .sciscinet_parquet.matcher import match_parquet
from .utils.files import find_files_by_extension
from .utils.resources import register_resource, register_resources

console = Console()


@dataclass
class PipelineResources:
    parquet_resources: dict[str, RegisteredResource]
    xlsx_resources: dict[str, RegisteredResource]
    world_bank_resource: RegisteredResource
    docx_resources: dict[str, RegisteredResource]


class ResourceMonitor:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.running = False
        self.peak_memory = 0
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._monitor, daemon=True)
        self.thread.start()

    def _monitor(self) -> None:
        while self.running:
            mem = self.process.memory_info().rss
            if mem > self.peak_memory:
                self.peak_memory = mem
            time.sleep(0.1)

    def stop(self) -> float:
        self.running = False
        if self.thread:
            self.thread.join()
        return self.peak_memory / (1024**3)


class PipelineManager:
    def __init__(self, state_file: Path, db_file: Path) -> None:
        self.state_file = state_file
        self.db_file = db_file
        self.state = self._load_state()
        self.conn: duckdb.DuckDBPyConnection | None = None

    def _load_state(self) -> dict[str, list[str]]:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        return {"steps_completed": []}

    def save_state(self, step_name: str) -> None:
        if step_name not in self.state["steps_completed"]:
            self.state["steps_completed"].append(step_name)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state), encoding="utf-8")

    def is_done(self, step_name: str) -> bool:
        return step_name in self.state["steps_completed"]

    def connect_db(self) -> duckdb.DuckDBPyConnection:
        if self.conn is None:
            self.conn = duckdb.connect(str(self.db_file))
            self.conn.execute("SET memory_limit='20GB'")
        return self.conn

    def close(self) -> None:
        if self.conn:
            self.conn.close()


def register_pipeline_resources(
    config: PipelineConfig,
    xlsx_files: list[Path],
) -> PipelineResources:
    files = config.files_config
    parquet_resources = {
        Path(files["author_details"]["path"]).name: register_resource(
            Path(files["author_details"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
            description=files["author_details"]["desc"],
            expected_hash=files["author_details"]["sha256"],
        ),
        Path(files["authors_paper"]["path"]).name: register_resource(
            Path(files["authors_paper"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description=files["authors_paper"]["desc"],
            expected_hash=files["authors_paper"]["sha256"],
        ),
        Path(files["hit_papers_0"]["path"]).name: register_resource(
            Path(files["hit_papers_0"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description=files["hit_papers_0"]["desc"],
            expected_hash=files["hit_papers_0"]["sha256"],
        ),
        Path(files["hit_papers_1"]["path"]).name: register_resource(
            Path(files["hit_papers_1"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description=files["hit_papers_1"]["desc"],
            expected_hash=files["hit_papers_1"]["sha256"],
        ),
        Path(files["fields"]["path"]).name: register_resource(
            Path(files["fields"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PARQUET_ROW,
            description=files["fields"]["desc"],
            expected_hash=files["fields"]["sha256"],
        ),
    }

    xlsx_resources = register_resources(
        xlsx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.EXCEL_ROW,
        description="HCR XLSX inputs",
    )
    world_bank_resource = register_resource(
        config.world_bank_xlsx,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.EXCEL_ROW,
        description="World Bank country list",
    )
    docx_files = find_files_by_extension(config.docx_dir, "docx", recursive=False)
    docx_resources = register_resources(
        docx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.DOCX_ROW,
        description="KTP DOCX inputs",
    )

    return PipelineResources(
        parquet_resources=parquet_resources,
        xlsx_resources=xlsx_resources,
        world_bank_resource=world_bank_resource,
        docx_resources=docx_resources,
    )


def run_reproduction(config: PipelineConfig | None = None, *, use_live: bool = True) -> Path:
    config = config or PipelineConfig()
    monitor = ResourceMonitor()
    monitor.start()

    pm = PipelineManager(config.state_file, config.db_file)
    conn = pm.connect_db()
    cards: dict[str, str] | None = None
    zip_path: Path | None = None

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["header"].update(Panel("KTP Pipeline", style="bold white on blue"))
    layout["footer"].update(Panel("Preparing cards", style="italic grey50"))

    live: Live | None = None
    peak_ram: float | None = None
    try:
        if use_live:
            live = Live(layout, refresh_per_second=4, console=console, transient=True)
            live.start()

        def log(msg: str, style: str = "white") -> None:
            if use_live:
                layout["body"].update(Panel(msg, style=style, title="Current Task"))
            else:
                console.print(f"[{style}]{msg}[/{style}]")

        log("Discovering XLSX inputs...", style="cyan")
        xlsx_files = find_files_by_extension(config.xlsx_dir, "xlsx", recursive=False)
        if not xlsx_files:
            raise FileNotFoundError(f"No XLSX files found in {config.xlsx_dir}")

        log("Registering resources...", style="cyan")
        resources = register_pipeline_resources(config, xlsx_files)

        log("Loading population table into DuckDB...", style="yellow")
        build_population_table(
            conn,
            resources.xlsx_resources,
            table_name="population",
            filename_col=HCR_FILENAME_COL,
            row_col=HCR_ROW_COL,
        )

        log("Preprocessing world bank economies...", style="yellow")
        economies = load_high_income_economies(resources.world_bank_resource)

        log("Sampling XLSX population...", style="yellow")
        if sum(config.sample_draw_sizes) != 300:
            raise ValueError(
                "Sample draw sizes must total 300 before pilot samples. "
                f"Got {sum(config.sample_draw_sizes)} from {config.sample_draw_sizes}."
            )
        sample_population(
            conn,
            population_table="population",
            samples_table="samples",
            draw_sizes=config.sample_draw_sizes,
            seed=config.sample_seed,
            economies=economies,
        )
        sample_pilot(
            conn,
            population_table="population",
            samples_table="samples",
            pilot_filename=config.pilot_xlsx_name,
            economies=economies,
        )

        log("Indexing samples for name keys...", style="yellow")
        outer_dict = index_samples(conn, samples_table="samples")

        log("Matching population rows...", style="magenta")
        match_population(
            conn,
            outer_dict,
            population_table="population",
            resources=resources.xlsx_resources,
        )

        log("Loading DOCX tables...", style="magenta")
        docx_df = load_docx_tables(resources.docx_resources)

        log("Matching DOCX rows...", style="magenta")
        match_docx(
            conn,
            outer_dict,
            docx_df,
            resources.docx_resources,
            fragment_col=DOCX_FRAGMENT_COL,
        )

        log("Matching parquet data...", style="magenta")
        files = config.files_config
        match_parquet(
            conn,
            outer_dict,
            conn.execute("SELECT * FROM samples").df(),
            resources.parquet_resources,
            author_details_path=files["author_details"]["path"],
            authors_paper_path=files["authors_paper"]["path"],
            hit_papers_level0_path=files["hit_papers_0"]["path"],
            hit_papers_level1_path=files["hit_papers_1"]["path"],
        )

        log("Rendering cards...", style="green")
        excluded_cols = {
            KTP_FILENAME_COL,
            KTP_SOURCE_KEY_COL,
            CSV_ROW_INDEX_COL,
            DOCX_TABLE_INDEX_COL,
            DOCX_ROW_INDEX_COL,
            DOCX_FRAGMENT_COL,
            KTP_ECONOMIES_COL,
            KTP_PRIORITY_COL,
            KTP_PRIORITY_GROUP_COL,
        }
        cards = build_cards(
            outer_dict,
            total_draws=config.total_draws,
            intro_date=datetime.now(ZoneInfo("America/Toronto")).strftime("%B %d, %Y"),
            excluded_cols=excluded_cols,
        )
        zip_path = write_cards_zip(
            cards,
            config.output_dir,
            f"{config.xlsx_dir.name}_combined_cards.zip",
            output_format=config.output_format,
            reference_docx=config.reference_docx,
        )
    finally:
        if live is not None:
            live.stop()
        peak_ram = monitor.stop()
        pm.close()

    m_table = Table(title="Execution Metrics", box=box.SIMPLE)
    m_table.add_column("Metric", style="cyan")
    m_table.add_column("Value", style="magenta")
    if peak_ram is not None:
        m_table.add_row("Peak RAM Usage", f"{peak_ram:.2f} GB")
    else:
        m_table.add_row("Peak RAM Usage", "n/a")
    if cards is not None:
        m_table.add_row("Cards", str(len(cards)))

    console.print(m_table)
    if zip_path is None:
        raise RuntimeError("Pipeline did not produce output zip.")
    console.print(f"[bold green]Success! Output saved to: {zip_path}[/bold green]")
    return zip_path


def signal_handler(sig, frame) -> None:
    console.print("\n[bold red]Process Interrupted! State saved. Run again to resume.[/bold red]")
    sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="KTP pipeline runner.")
    parser.add_argument("--config", type=Path, help="Path to JSON config file.")
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disable the rich live UI and print log lines instead.",
    )
    args = parser.parse_args()
    if args.config:
        config = PipelineConfig.from_json(args.config)
    else:
        config = PipelineConfig()
    run_reproduction(config, use_live=not args.non_interactive)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    try:
        main()
    except Exception:
        console.print_exception()
        sys.exit(1)
