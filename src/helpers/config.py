from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

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
    "authors": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_authors.parquet",
        "sha256": "17669bf36ddfe2c6fcebd759bdbc292269d3651292792babe0211a6161ae492e",
        "desc": "Authors",
    },
    "fields": {
        "path": "/Volumes/home/anonymous/sciscinet/v2/hf/xet/sciscinet_fields.parquet",
        "sha256": "f78b1fc5287de26aee57665943a50c95aa980420449d7c099c351600cd584c7a",
        "desc": "Field Definitions",
    },
}


@dataclass
class PipelineConfig:
    files_config: dict[str, dict[str, str]] = field(default_factory=lambda: FILES_CONFIG.copy())
    db_file: Path = Path("data/scisci_process.duckdb")
    state_file: Path = Path("data/pipeline_state.json")
    output_dir: Path = Path("data/output")
    output_format: str = "txt"
    pandoc_reference_docx: Path = Path("resources/pandoc-custom-reference.docx")
    docx_dir: Path = Path("data/manual_extractions")
    timezone: str = "America/Toronto"
    sample_seed: int = 42
    sample_draw_sizes: list[int] = field(default_factory=lambda: [20] + [40] * 7)
    pilot_xlsx_name: str = "2024_HCR.xlsx"
    total_draws: int = 310

    @classmethod
    def from_json(cls, path: Path) -> "PipelineConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        config = cls()
        for key, value in raw.items():
            if hasattr(config, key):
                setattr(config, key, value)
        if isinstance(config.files_config, dict) and config.files_config:
            config.files_config = config.files_config
        config.db_file = Path(config.db_file)
        config.state_file = Path(config.state_file)
        config.output_dir = Path(config.output_dir)
        if hasattr(config, "reference_docx"):
            config.pandoc_reference_docx = Path(getattr(config, "reference_docx"))
            delattr(config, "reference_docx")
        config.pandoc_reference_docx = Path(config.pandoc_reference_docx)
        config.docx_dir = Path(config.docx_dir)
        return config
