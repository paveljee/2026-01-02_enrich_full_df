from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.data_models import FragmentType

FILES_CONFIG = {
    "hit_papers_0": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level0.parquet",
        "sha256": "453bf5e5fe4bd2427b467c35aaea36a9d5c1b8b61d1e01d84496fd7fd5e6d6aa",
        "desc": "Hit Papers Level 0",
    },
    "hit_papers_1": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/hit_papers_level1.parquet",
        "sha256": "f79ddf6e417e9d601ae04e6c898c72bc7b60118d3967cb03fe6fc708eab953ae",
        "desc": "Hit Papers Level 1",
    },
    "authors_paper": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_authors_paperid.parquet",
        "sha256": "c97f4552f22d8e05b1c2bb70746b5a16f29c41c2807738d3c49f3852573910f2",
        "desc": "Authors -> Paper IDs",
    },
    "author_details": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_author_details.parquet",
        "sha256": "62c373c747d74879585c3b1cfbbe70971c86927ec4fbc601482d3c2513ad9c1a",
        "desc": "Author Details (Names)",
    },
    "fields": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_fields.parquet",
        "sha256": "f78b1fc5287de26aee57665943a50c95aa980420449d7c099c351600cd584c7a",
        "desc": "Field Definitions",
    },
}

PARQUET_FRAGMENT_OVERRIDES = {
    "author_details": FragmentType.AUTHOR_ID,
    "authors_paper": FragmentType.AUTHOR_ID,
}

REFERENCE_METRICS = {
    "peak_ram_gb": 8.47,
    "total_time_s": 27.3,
}

DB_FILE = Path("data/scisci_process.duckdb")
STATE_FILE = Path("data/pipeline_state.json")


@dataclass(frozen=True)
class KtpPaths:
    xlsx_dir: Path
    csv_dir: Path
    docx_dir: Path
    output_dir: Path
    output_format: str
    pilot_xlsx_path: Path
    pilot_schema_dir: Path


DEFAULT_KTP_PATHS = KtpPaths(
    xlsx_dir=Path("data/xlsx"),
    csv_dir=Path("data/samples"),
    docx_dir=Path("data/manual_extractions"),
    output_dir=Path("output"),
    output_format="txt",
    pilot_xlsx_path=Path("data/xlsx/2024_HCR.xlsx"),
    pilot_schema_dir=Path("data/xlsx"),
)
