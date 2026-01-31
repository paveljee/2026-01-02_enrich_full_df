from __future__ import annotations

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
import pandas as pd
import psutil
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from ._vars import (
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
)
from .cards import build_cards, write_cards_zip
from .config import PipelineConfig
from .data_models import FragmentType, NameKey, RegisteredResource, ResourceGroup
from .dict_utils import NAME_KEY_COL, build_outer_dict_from_names
from .io_utils import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    find_files_by_extension,
    load_csv_files,
    load_docx_tables,
    validate_csv_headers,
)
from .matchers import (
    match_csv_df,
    match_docx_df,
    match_parquet_sources,
    match_population_df,
)
from .name_processing import apply_unify_first_last
from .resources_utils import register_resource, register_resources
from .sampling import (
    HCR_LIST_LABEL,
    build_pilot_sample,
    concat_dfs_from_file_list,
    sample_population_df,
)

console = Console()


@dataclass
class PipelineResources:
    parquet_resources: dict[str, RegisteredResource]
    xlsx_resources: dict[str, RegisteredResource]
    csv_resources: dict[str, RegisteredResource]
    docx_resources: dict[str, RegisteredResource]


class ResourceMonitor:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.running = False
        self.peak_memory = 0
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._monitor)
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
    parquet = config.parquet_config
    parquet_resources = {
        parquet.author_details_path.name: register_resource(
            parquet.author_details_path,
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
            description="Author details parquet",
            expected_hash=parquet.author_details_sha256,
        ),
        parquet.authors_paper_path.name: register_resource(
            parquet.authors_paper_path,
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description="Authors to paper IDs parquet",
            expected_hash=parquet.authors_paper_sha256,
        ),
        parquet.hit_papers_level0_path.name: register_resource(
            parquet.hit_papers_level0_path,
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description="Hit papers level 0",
            expected_hash=parquet.hit_papers_level0_sha256,
        ),
        parquet.hit_papers_level1_path.name: register_resource(
            parquet.hit_papers_level1_path,
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description="Hit papers level 1",
            expected_hash=parquet.hit_papers_level1_sha256,
        ),
        parquet.fields_path.name: register_resource(
            parquet.fields_path,
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PARQUET_ROW,
            description="Fields parquet",
            expected_hash=parquet.fields_sha256,
        ),
    }

    xlsx_resources = register_resources(
        xlsx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.EXCEL_ROW,
        description="HCR XLSX inputs",
    )

    return PipelineResources(
        parquet_resources=parquet_resources,
        xlsx_resources=xlsx_resources,
        csv_resources={},
        docx_resources={},
    )


def run_reproduction(config: PipelineConfig | None = None) -> Path:
    config = config or PipelineConfig()
    monitor = ResourceMonitor()
    monitor.start()

    pm = PipelineManager(config.state_file, config.db_file)

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["header"].update(Panel("KTP Pipeline", style="bold white on blue"))
    layout["footer"].update(Panel("Preparing cards", style="italic grey50"))

    with Live(layout, refresh_per_second=4, console=console):
        def log(msg: str, style: str = "white") -> None:
            layout["body"].update(Panel(msg, style=style, title="Current Task"))

        if not pm.is_done("discover_inputs"):
            log("Discovering XLSX files...", style="cyan")
            xlsx_files = find_files_by_extension(config.xlsx_dir, "xlsx", recursive=False)
            if not xlsx_files:
                raise FileNotFoundError(f"No XLSX files found in {config.xlsx_dir}")
            pm.save_state("discover_inputs")
        else:
            xlsx_files = find_files_by_extension(config.xlsx_dir, "xlsx", recursive=False)

        if not pm.is_done("register_resources"):
            log("Registering parquet and XLSX resources...", style="cyan")
            pipeline_resources = register_pipeline_resources(config, xlsx_files)
            pm.save_state("register_resources")
        else:
            pipeline_resources = register_pipeline_resources(config, xlsx_files)

        log("Loading population dataframe from XLSX...", style="yellow")
        population_df = concat_dfs_from_file_list(xlsx_files)
        population_df[KTP_FILENAME_COL] = population_df[HCR_LIST_LABEL]
        population_df = apply_unify_first_last(population_df)

        log("Sampling population dataframe...", style="yellow")
        if sum(config.sample_draw_sizes) != 300:
            raise ValueError(
                "Sample draw sizes must total 300 before pilot samples. "
                f"Got {sum(config.sample_draw_sizes)} from {config.sample_draw_sizes}."
            )
        sample_df = sample_population_df(
            population_df,
            draw_sizes=config.sample_draw_sizes,
            seed=config.sample_seed,
            affiliation_sort=True,
        )

        pilot_xlsx_path = config.xlsx_dir / config.pilot_xlsx_name
        pilot_df = build_pilot_sample(
            pilot_xlsx_path,
            config.xlsx_dir,
            affiliation_sort=False,
        )
        sample_df = pd.concat([sample_df, pilot_df], ignore_index=True)
        sample_df = apply_unify_first_last(sample_df)

        name_keys = sample_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]].drop_duplicates()
        outer_dict = build_outer_dict_from_names(name_keys)
        sample_df[NAME_KEY_COL] = [
            NameKey(
                first_name=row[KTP_FIRST_NAME_COL],
                last_name=row[KTP_LAST_NAME_COL],
            ).to_json_key()
            for row in sample_df.to_dict("records")
        ]

        conn = pm.connect_db()

        log("Matching population XLSX rows...", style="magenta")
        match_population_df(conn, outer_dict, population_df, pipeline_resources.xlsx_resources)

        log("Matching CSV rows...", style="magenta")
        csv_files = find_files_by_extension(config.csv_dir, "csv", recursive=False)
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in {config.csv_dir}")
        if not validate_csv_headers(csv_files):
            raise ValueError("CSV headers do not match.")
        pipeline_resources.csv_resources = register_resources(
            csv_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.CSV_ROW,
            description="KTP CSV inputs",
        )
        csv_df = load_csv_files(csv_files)
        csv_df = apply_unify_first_last(csv_df)
        match_csv_df(conn, outer_dict, csv_df, population_df, pipeline_resources.csv_resources)

        log("Matching DOCX rows...", style="magenta")
        docx_files = find_files_by_extension(config.docx_dir, "docx", recursive=False)
        if not docx_files:
            raise FileNotFoundError(f"No DOCX files found in {config.docx_dir}")
        pipeline_resources.docx_resources = register_resources(
            docx_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.DOCX_ROW,
            description="KTP DOCX inputs",
        )
        docx_df = load_docx_tables(docx_files)
        match_docx_df(conn, outer_dict, docx_df, pipeline_resources.docx_resources)

        log("Matching parquet data...", style="magenta")
        parquet = config.parquet_config
        match_parquet_sources(
            conn,
            outer_dict,
            sample_df,
            pipeline_resources.parquet_resources,
            author_details_path=str(parquet.author_details_path),
            authors_paper_path=str(parquet.authors_paper_path),
            hit_papers_level0_path=str(parquet.hit_papers_level0_path),
            hit_papers_level1_path=str(parquet.hit_papers_level1_path),
        )

        log("Rendering cards...", style="green")
        excluded_cols = {
            KTP_FILENAME_COL,
            "ktp.source_key",
            CSV_ROW_INDEX_COL,
            DOCX_TABLE_INDEX_COL,
            DOCX_ROW_INDEX_COL,
            DOCX_FRAGMENT_COL,
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
            f"{config.csv_dir.name}_combined_cards.zip",
        )
        pm.save_state("complete")

    peak_ram = monitor.stop()
    pm.close()

    m_table = Table(title="Execution Metrics", box=box.SIMPLE)
    m_table.add_column("Metric", style="cyan")
    m_table.add_column("Value", style="magenta")
    m_table.add_row("Peak RAM Usage", f"{peak_ram:.2f} GB")
    m_table.add_row("Cards", str(len(cards)))

    console.print(m_table)
    console.print(f"[bold green]Success! Output saved to: {zip_path}[/bold green]")
    return zip_path


def signal_handler(sig, frame) -> None:
    console.print("\n[bold red]Process Interrupted! State saved. Run again to resume.[/bold red]")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    try:
        run_reproduction()
    except Exception:
        console.print_exception()
        sys.exit(1)
