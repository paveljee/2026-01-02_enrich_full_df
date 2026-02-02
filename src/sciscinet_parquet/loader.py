from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParquetPaths:
    author_details: Path
    authors_paper: Path
    hit_papers_level0: Path
    hit_papers_level1: Path
    fields: Path
