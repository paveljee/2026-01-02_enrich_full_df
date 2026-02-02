from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pandas as pd

from src.hcr_xlsx.loader import normalize_hcr_header

WORKSHOP_BASE = Path(
    "/Volumes/Users/Anonymous/Workshop/202504161200UTC-4_Nancy_Baxter_Andrea_Tricco_collabs"
)
ANALYSIS_BASE = WORKSHOP_BASE / "analyses/2026-01-02_enrich_full_df/data"
HCR_XLSX_DIR = WORKSHOP_BASE / "2024-Historical-Highly-Cited-Researchers-lists - final"
DOCX_DIR = ANALYSIS_BASE / "manual_extractions"
SAMPLES_DIR = ANALYSIS_BASE / "samples"
WORLD_BANK_XLSX = ANALYSIS_BASE / "OGHIST_2025_07_01.xlsx"

SCISCINET_BASE = Path("/Volumes/home/anonymous/sciscinet/v2/hf/xet")
SCISCINET_AUTHOR_DETAILS = SCISCINET_BASE / "sciscinet_author_details.parquet"
SCISCINET_AUTHORS_PAPER = SCISCINET_BASE / "sciscinet_authors_paperid.parquet"
SCISCINET_HIT_LEVEL0 = SCISCINET_BASE / "hit_papers_level0.parquet"
SCISCINET_HIT_LEVEL1 = SCISCINET_BASE / "hit_papers_level1.parquet"
SCISCINET_FIELDS = SCISCINET_BASE / "sciscinet_fields.parquet"


def _filter_existing(paths: Iterable[Path]) -> list[Path]:
    return [path for path in paths if path.exists()]


def list_hcr_xlsx_files(limit: int | None = None) -> list[Path]:
    if not HCR_XLSX_DIR.exists():
        return []
    files = sorted(
        path for path in HCR_XLSX_DIR.glob("*.xlsx") if not path.name.startswith("~$")
    )
    return files[:limit] if limit else files


def list_docx_files(limit: int | None = None) -> list[Path]:
    if not DOCX_DIR.exists():
        return []
    files = sorted(path for path in DOCX_DIR.glob("*.docx"))
    return files[:limit] if limit else files


def list_sample_csv_files(limit: int | None = None) -> list[Path]:
    if not SAMPLES_DIR.exists():
        return []
    files = sorted(path for path in SAMPLES_DIR.glob("*.csv"))
    return files[:limit] if limit else files


def infer_name_columns_from_xlsx(path: Path) -> tuple[str, str] | None:
    df = pd.read_excel(path, engine="openpyxl")
    normalized = [normalize_hcr_header(str(col).lower()) for col in df.columns]

    def pick(candidates: list[str]) -> str | None:
        for cand in candidates:
            for col in normalized:
                if cand in col:
                    return col
        return None

    first = pick([
        "first_name",
        "firstname",
        "first name",
        "first",
    ])
    last = pick([
        "last_name",
        "lastname",
        "last name",
        "family_name",
        "familyname",
        "surname",
        "last",
    ])

    if not first or not last or first == last:
        return None
    return first, last


def extract_first_last(name: str) -> tuple[str, str] | None:
    if not isinstance(name, str):
        return None
    cleaned = re.sub(r"[^A-Za-z0-9\s]+", " ", name).strip()
    parts = [p for p in cleaned.split() if p]
    if len(parts) < 2:
        return None
    return parts[0], parts[-1]


def required_real_paths_exist() -> bool:
    paths = _filter_existing(
        [
            WORLD_BANK_XLSX,
            SCISCINET_AUTHOR_DETAILS,
            SCISCINET_AUTHORS_PAPER,
            SCISCINET_HIT_LEVEL0,
            SCISCINET_HIT_LEVEL1,
        ]
    )
    return (
        HCR_XLSX_DIR.exists()
        and DOCX_DIR.exists()
        and SAMPLES_DIR.exists()
        and len(paths) == 5
    )
