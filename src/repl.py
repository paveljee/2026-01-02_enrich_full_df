from __future__ import annotations

import json
import signal
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import psutil
from rich.console import Console

from ._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from .cards import build_cards_archive
from .config import PipelineConfig, default_config
from .csv_loader import load_csv_files
from .data_models import FragmentType, NameKey, OuterDict, ResourceGroup
from .docx_loader import load_docx_tables
from .io_utils import find_files_by_extension, validate_csv_headers
from .matchers import CsvDuckdbMatcher, DocxDuckdbMatcher, ParquetMatcher, XlsxDuckdbMatcher
from .matchers.parquet_matcher import ParquetPaths
from .name_utils import apply_unify_first_last
from .resource_registry import register_resources
from .sampling.xlsx_sampler import load_population_from_xlsx, sample_fixed_seed, select_pilot_sample

console = Console()


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
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> dict[str, list[str]]:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        return {"steps_completed": []}

    def save_state(self, step_name: str) -> None:
        if step_name not in self.state["steps_completed"]:
            self.state["steps_completed"].append(step_name)
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def is_done(self, step_name: str) -> bool:
        return step_name in self.state["steps_completed"]


def build_outer_dict(sample_df: pd.DataFrame) -> OuterDict:
    name_keys = [
        NameKey(first_name=row[KTP_FIRST_NAME_COL], last_name=row[KTP_LAST_NAME_COL])
        for row in sample_df.to_dict("records")
    ]
    return OuterDict.from_name_keys(name_keys)


def run_reproduction(config: PipelineConfig) -> None:
    console.print("[bold cyan]KTP Enrichment Pipeline[/bold cyan]")
    monitor = ResourceMonitor()
    monitor.start()

    state_file = config.paths.output_dir / "pipeline_state.json"
    pm = PipelineManager(state_file)

    # STEP 1: Locate XLSX resources and build population dataframe
    if not pm.is_done("load_population"):
        xlsx_files = find_files_by_extension(config.paths.xlsx_dir, "xlsx", recursive=True)
        console.print(f"[green]Found {len(xlsx_files)} XLSX file(s)[/green]")
        xlsx_resources = register_resources(
            xlsx_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
            description="KTP XLSX population files",
        )
        population_df = load_population_from_xlsx(xlsx_files)
        pm.save_state("load_population")
    else:
        xlsx_files = find_files_by_extension(config.paths.xlsx_dir, "xlsx", recursive=True)
        xlsx_resources = register_resources(
            xlsx_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
            description="KTP XLSX population files",
        )
        population_df = load_population_from_xlsx(xlsx_files)

    # STEP 2: Sample main draws + pilot draws
    if not pm.is_done("sample"):
        draw_dfs = sample_fixed_seed(
            population_df,
            seed=config.sample_plan.seed,
            draw_sizes=config.sample_plan.draw_sizes,
            affiliation_sort=config.sample_plan.affiliation_sort,
        )
        pilot_df = select_pilot_sample(population_df, config.pilot_triples, affiliation_sort=False)
        sample_df = pd.concat([*draw_dfs, pilot_df], ignore_index=True)
        pm.save_state("sample")
    else:
        draw_dfs = sample_fixed_seed(
            population_df,
            seed=config.sample_plan.seed,
            draw_sizes=config.sample_plan.draw_sizes,
            affiliation_sort=config.sample_plan.affiliation_sort,
        )
        pilot_df = select_pilot_sample(population_df, config.pilot_triples, affiliation_sort=False)
        sample_df = pd.concat([*draw_dfs, pilot_df], ignore_index=True)

    # STEP 3: Normalize names & build outer dict
    if not pm.is_done("prepare_outer_dict"):
        sample_df = apply_unify_first_last(sample_df)
        outer_dict = build_outer_dict(sample_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]])
        pm.save_state("prepare_outer_dict")
    else:
        sample_df = apply_unify_first_last(sample_df)
        outer_dict = build_outer_dict(sample_df[[KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL]])

    # STEP 4: XLSX match (population -> inner dicts)
    if not pm.is_done("match_xlsx"):
        XlsxDuckdbMatcher(outer_dict, xlsx_resources).match(population_df)
        pm.save_state("match_xlsx")

    # STEP 5: CSV match (validate + duplicate check)
    if not pm.is_done("match_csv"):
        csv_files = find_files_by_extension(config.paths.csv_dir, "csv", recursive=True)
        console.print(f"[green]Found {len(csv_files)} CSV file(s)[/green]")
        if not validate_csv_headers(csv_files):
            raise ValueError("CSV headers mismatch")
        csv_resources = register_resources(
            csv_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.CSV_ROW,
            description="KTP CSV enrichment files",
        )
        csv_df = load_csv_files(csv_files)
        csv_df = apply_unify_first_last(csv_df)
        CsvDuckdbMatcher(outer_dict, csv_resources).match(csv_df)
        pm.save_state("match_csv")

    # STEP 6: DOCX match
    if not pm.is_done("match_docx"):
        docx_files = find_files_by_extension(config.paths.docx_dir, "docx", recursive=True)
        console.print(f"[green]Found {len(docx_files)} DOCX file(s)[/green]")
        docx_resources = register_resources(
            docx_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.DOCX_ROW,
            description="KTP DOCX enrichment files",
        )
        docx_df = load_docx_tables(docx_files)
        DocxDuckdbMatcher(outer_dict, docx_resources).match(docx_df)
        pm.save_state("match_docx")

    # STEP 7: Parquet enrichment
    if not pm.is_done("match_parquet"):
        parquet_paths = ParquetPaths(
            author_details=str(config.paths.parquet_author_details),
            authors_paper=str(config.paths.parquet_authors_paper),
            hit_papers_0=str(config.paths.parquet_hit_papers_0),
            hit_papers_1=str(config.paths.parquet_hit_papers_1),
        )
        _parquet_resources = register_resources(
            [
                config.paths.parquet_authors_paper,
                config.paths.parquet_hit_papers_0,
                config.paths.parquet_hit_papers_1,
            ],
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PARQUET_ROW,
            description="SciSciNet parquet data",
        )
        author_resource = register_resources(
            [config.paths.parquet_author_details],
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
            description="SciSciNet author details",
        )[config.paths.parquet_author_details.name]
        ParquetMatcher(outer_dict, author_resource, parquet_paths).match()
        pm.save_state("match_parquet")

    # STEP 8: Build cards
    if not pm.is_done("build_cards"):
        build_cards_archive(
            outer_dict,
            output_dir=config.paths.output_dir,
            output_format=config.output_format,
            total_draws=config.total_draws,
            reference_docx=config.pandoc_reference_docx,
            archive_stem=config.paths.csv_dir.name,
        )
        pm.save_state("build_cards")

    peak_ram = monitor.stop()
    console.print(f"[bold green]Pipeline complete. Peak RAM: {peak_ram:.2f} GB[/bold green]")
    console.print(f"[dim]Config used:[/dim] {json.dumps(asdict(config), default=str, indent=2)}")


def signal_handler(sig, frame):
    console.print("\n[bold red]Process Interrupted! State saved. Run again to resume.[/bold red]")
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    run_reproduction(default_config())
