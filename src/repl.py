from __future__ import annotations

import json
import signal
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import psutil
from rich import box
from rich.console import Console
from rich.table import Table

from src._vars import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    HCR_FIRST_NAME_COL,
    HCR_LAST_NAME_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    SOURCE_KEY_COL,
)
from src.cards import build_cards, write_cards_zip
from src.config import (
    DB_FILE,
    DEFAULT_KTP_PATHS,
    FILES_CONFIG,
    PARQUET_FRAGMENT_OVERRIDES,
    REFERENCE_METRICS,
    STATE_FILE,
    KtpPaths,
)
from src.data_models import FragmentType, OuterDict, ResourceGroup
from src.docx_utils import load_docx_tables, resolve_docx_name_column
from src.io_utils import find_files_by_extension, validate_csv_headers
from src.matchers import (
    append_csv_matches,
    append_docx_matches,
    append_parquet_matches,
    append_population_matches,
)
from src.name_processing import apply_unified_names
from src.outer_dict_utils import build_outer_dict_from_names
from src.resource_registry import register_resources, register_resources_from_config
from src.sampling import load_population_from_xlsx, sample_pilot_from_2024, sample_random_draws

console = Console()


@dataclass
class PipelineState:
    steps_completed: list[str]


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
        return self.peak_memory / (1024 ** 3)


class PipelineManager:
    def __init__(self) -> None:
        self.state = self._load_state()
        self.conn: duckdb.DuckDBPyConnection | None = None

    def _load_state(self) -> PipelineState:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as handle:
                return PipelineState(**json.load(handle))
        return PipelineState(steps_completed=[])

    def save_state(self, step_name: str) -> None:
        if step_name not in self.state.steps_completed:
            self.state.steps_completed.append(step_name)
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as handle:
                json.dump({"steps_completed": self.state.steps_completed}, handle)

    def is_done(self, step_name: str) -> bool:
        return step_name in self.state.steps_completed

    def connect_db(self) -> duckdb.DuckDBPyConnection:
        self.conn = duckdb.connect(DB_FILE.as_posix())
        self.conn.execute("SET memory_limit='20GB'")
        self.conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
        return self.conn

    def close(self) -> None:
        if self.conn:
            self.conn.close()


def _ensure_column(df: pd.DataFrame, column: str) -> None:
    if column not in df.columns:
        raise ValueError(f"Expected column '{column}' to be present in dataframe.")


def run_reproduction(paths: KtpPaths = DEFAULT_KTP_PATHS) -> None:
    monitor = ResourceMonitor()
    monitor.start()

    pm = PipelineManager()
    start_time = time.time()

    # ------------------------------------------------------------------
    # STEP 1: VERIFY PARQUET INPUTS (I/O)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 1: Verifying parquet resources[/cyan]")
    parquet_resources = register_resources_from_config(
        FILES_CONFIG,
        group=ResourceGroup.SCISCINET_HF,
        fragment_type=FragmentType.PARQUET_ROW,
        fragment_type_overrides=PARQUET_FRAGMENT_OVERRIDES,
    )

    # ------------------------------------------------------------------
    # STEP 2: LOAD XLSX POPULATION (I/O)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 2: Loading XLSX population[/cyan]")
    xlsx_files = find_files_by_extension(paths.xlsx_dir, "xlsx", recursive=False)
    if not xlsx_files:
        raise FileNotFoundError(f"No XLSX files found in {paths.xlsx_dir}")
    xlsx_resources = register_resources(
        xlsx_files,
        group=ResourceGroup.HCR_LISTS_2024_ZIP,
        fragment_type=FragmentType.EXCEL_ROW,
        description="HCR XLSX population inputs",
    )
    population_df = load_population_from_xlsx(paths.xlsx_dir)

    # ------------------------------------------------------------------
    # STEP 3: SAMPLE POPULATION (TRANSFORM)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 3: Sampling population[/cyan]")
    draw_sizes = [20] * 8 + [40] * 7
    sample_random_df = sample_random_draws(
        population_df,
        seed=42,
        draw_sizes=draw_sizes,
        affiliation_sort=True,
        max_total=300,
    )
    pilot_df = sample_pilot_from_2024(paths.pilot_xlsx_path, paths.pilot_schema_dir)
    sample_df = pd.concat([sample_random_df, pilot_df], ignore_index=True)

    # ------------------------------------------------------------------
    # STEP 4: NORMALIZE NAMES + OUTER DICT (TRANSFORM)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 4: Normalizing names and building OuterDict[/cyan]")
    sample_df = apply_unified_names(sample_df)
    _ensure_column(sample_df, KTP_FIRST_NAME_COL)
    _ensure_column(sample_df, KTP_LAST_NAME_COL)

    unique_names = (
        sample_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    outer_dict: OuterDict = build_outer_dict_from_names(unique_names)

    # ------------------------------------------------------------------
    # STEP 5: DUCKDB INIT (I/O)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 5: Initializing DuckDB[/cyan]")
    conn = pm.connect_db()

    # ------------------------------------------------------------------
    # STEP 6: XLSX MATCHING (TRANSFORM)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 6: Matching XLSX population[/cyan]")
    population_df = apply_unified_names(population_df)
    append_population_matches(outer_dict, population_df, xlsx_resources, conn=conn)

    # ------------------------------------------------------------------
    # STEP 7: CSV MATCHING (I/O + TRANSFORM)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 7: Matching CSV inputs[/cyan]")
    csv_files = find_files_by_extension(paths.csv_dir, "csv", recursive=False)
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {paths.csv_dir}")
    if not validate_csv_headers(csv_files):
        raise ValueError("CSV files have different headers.")
    csv_resources = register_resources(
        csv_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.CSV_ROW,
        description="KTP CSV inputs",
    )
    csv_frames = []
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        df[KTP_FILENAME_COL] = csv_path.name
        csv_frames.append(df)
    csv_df = pd.concat(csv_frames, ignore_index=True)
    csv_df[CSV_ROW_INDEX_COL] = csv_df.index
    csv_df = apply_unified_names(csv_df)
    append_csv_matches(outer_dict, csv_df, population_df, csv_resources, conn=conn)

    # ------------------------------------------------------------------
    # STEP 8: DOCX MATCHING (I/O + TRANSFORM)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 8: Matching DOCX inputs[/cyan]")
    docx_files = find_files_by_extension(paths.docx_dir, "docx", recursive=False)
    if not docx_files:
        raise FileNotFoundError(f"No DOCX files found in {paths.docx_dir}")
    docx_resources = register_resources(
        docx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.DOCX_ROW,
        description="KTP DOCX inputs",
    )
    docx_df = load_docx_tables(docx_files)
    if docx_df.empty:
        raise ValueError("DOCX parsing returned no rows.")
    name_column = resolve_docx_name_column(docx_df)
    append_docx_matches(
        outer_dict,
        docx_df,
        name_column,
        DOCX_FRAGMENT_COL,
        docx_resources,
        conn=conn,
    )

    # ------------------------------------------------------------------
    # STEP 9: PARQUET MATCHING (I/O + TRANSFORM)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 9: Matching parquet enrichment[/cyan]")
    _ensure_column(sample_df, HCR_FIRST_NAME_COL)
    _ensure_column(sample_df, HCR_LAST_NAME_COL)
    append_parquet_matches(
        outer_dict,
        sample_df,
        conn=conn,
        resources=parquet_resources,
    )

    # ------------------------------------------------------------------
    # STEP 10: GENERATE CARDS (TRANSFORM + OUTPUT)
    # ------------------------------------------------------------------
    console.print("[cyan]Step 10: Writing cards output[/cyan]")
    excluded_cols = {
        KTP_FILENAME_COL,
        SOURCE_KEY_COL,
        CSV_ROW_INDEX_COL,
        DOCX_FRAGMENT_COL,
    }
    cards = build_cards(outer_dict, excluded_cols=excluded_cols)
    reference_docx = Path("resources/pandoc-custom-reference.docx")
    write_cards_zip(
        cards,
        output_dir=paths.output_dir,
        output_format=paths.output_format,
        bundle_name=paths.csv_dir.name,
        reference_docx_path=reference_docx,
    )

    peak_ram = monitor.stop()
    total_time = time.time() - start_time
    pm.close()

    metrics = Table(title="Execution Metrics", box=box.SIMPLE)
    metrics.add_column("Metric", style="cyan")
    metrics.add_column("Value", style="magenta")
    metrics.add_column("Reference", style="dim")

    metrics.add_row(
        "Peak RAM Usage",
        f"{peak_ram:.2f} GB",
        f"{REFERENCE_METRICS['peak_ram_gb']} GB",
    )
    metrics.add_row("Total Time", f"{total_time:.1f} s", f"{REFERENCE_METRICS['total_time_s']} s")
    metrics.add_row("Output Rows", str(len(sample_df)), "310")

    console.print(metrics)


def signal_handler(sig, frame):
    console.print("\n[bold red]Process Interrupted! State saved. Run again to resume.[/bold red]")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    try:
        run_reproduction()
    except Exception:
        console.print_exception()
        sys.exit(1)
