from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sampling.xlsx_sampler import SamplePlan


@dataclass(frozen=True)
class PipelinePaths:
    xlsx_dir: Path
    csv_dir: Path
    docx_dir: Path
    output_dir: Path
    parquet_author_details: Path
    parquet_authors_paper: Path
    parquet_hit_papers_0: Path
    parquet_hit_papers_1: Path


@dataclass(frozen=True)
class PipelineConfig:
    paths: PipelinePaths
    output_format: str
    pandoc_reference_docx: Path
    sample_plan: SamplePlan
    pilot_triples: list[tuple[str, str, str]]
    total_draws: int


def default_config() -> PipelineConfig:
    root = Path(__file__).resolve().parents[1]
    return PipelineConfig(
        paths=PipelinePaths(
            xlsx_dir=root / "data" / "xlsx",
            csv_dir=root / "data" / "csv",
            docx_dir=root / "data" / "docx",
            output_dir=root / "output",
            parquet_author_details=root / "data" / "parquet" / "sciscinet_author_details.parquet",
            parquet_authors_paper=root / "data" / "parquet" / "sciscinet_authors_paperid.parquet",
            parquet_hit_papers_0=root / "data" / "parquet" / "hit_papers_level0.parquet",
            parquet_hit_papers_1=root / "data" / "parquet" / "hit_papers_level1.parquet",
        ),
        output_format="txt",
        pandoc_reference_docx=root / "resources" / "pandoc-custom-reference.docx",
        sample_plan=SamplePlan(seed=42, draw_sizes=[20] * 8 + [40] * 7, affiliation_sort=True),
        pilot_triples=[
            ("Bin", "Gao", "Cross-Field"),
            ("Beatriz Roldan", "Cuenya", "Chemistry"),
            ("Lizhi", "Zhang", "Chemistry"),
            ("Rudolf A.", "de Boer", "Clinical Medicine"),
            ("Hidenori", "Arai", "Cross-Field"),
            ("Mark A.", "Bradford", "Cross-Field"),
            ("Salim", "Yusuf", "Clinical Medicine"),
            ("Nicholas C.", "Turner", "Clinical Medicine"),
            ("Osman M.", "Bakr", "Chemistry"),
            ("Rainer", "Blatt", "Physics"),
        ],
        total_draws=310,
    )
