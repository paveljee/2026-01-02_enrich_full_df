from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParquetConfig:
    author_details_path: Path
    authors_paper_path: Path
    hit_papers_level0_path: Path
    hit_papers_level1_path: Path
    fields_path: Path
    author_details_sha256: str
    authors_paper_sha256: str
    hit_papers_level0_sha256: str
    hit_papers_level1_sha256: str
    fields_sha256: str


@dataclass
class PipelineConfig:
    xlsx_dir: Path = Path("data/xlsx")
    csv_dir: Path = Path("data/samples")
    docx_dir: Path = Path("data/manual_extractions")
    output_dir: Path = Path("data/output")
    state_file: Path = Path("data/pipeline_state.json")
    db_file: Path = Path("data/scisci_process.duckdb")
    sample_seed: int = 42
    sample_draw_sizes: list[int] = field(
        default_factory=lambda: [20] + [40] * 7
    )
    pilot_xlsx_name: str = "2024_HCR.xlsx"
    total_draws: int = 310
    parquet_config: ParquetConfig = ParquetConfig(
        author_details_path=Path(
            "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_author_details.parquet"
        ),
        authors_paper_path=Path(
            "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_authors_paperid.parquet"
        ),
        hit_papers_level0_path=Path(
            "/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level0.parquet"
        ),
        hit_papers_level1_path=Path(
            "/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level1.parquet"
        ),
        fields_path=Path(
            "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_fields.parquet"
        ),
        author_details_sha256="62c373c747d74879585c3b1cfbbe70971c86927ec4fbc601482d3c2513ad9c1a",
        authors_paper_sha256="c97f4552f22d8e05b1c2bb70746b5a16f29c41c2807738d3c49f3852573910f2",
        hit_papers_level0_sha256="453bf5e5fe4bd2427b467c35aaea36a9d5c1b8b61d1e01d84496fd7fd5e6d6aa",
        hit_papers_level1_sha256="f79ddf6e417e9d601ae04e6c898c72bc7b60118d3967cb03fe6fc708eab953ae",
        fields_sha256="f78b1fc5287de26aee57665943a50c95aa980420449d7c099c351600cd584c7a",
    )
