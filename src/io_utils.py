from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.console import Console

console = Console()


def find_files_by_extension(directory: Path, extension: str, recursive: bool = False) -> list[Path]:
    """Find all files with given extension in directory."""
    pattern = f"*.{extension}"
    if recursive:
        return list(directory.rglob(pattern))
    return list(directory.glob(pattern))


def validate_csv_headers(csv_files: list[Path]) -> bool:
    """Validate that all CSV files have the same column names."""
    if not csv_files:
        return False

    first_df = pd.read_csv(csv_files[0], nrows=0)
    expected_cols = set(first_df.columns)

    for csv_path in csv_files[1:]:
        df = pd.read_csv(csv_path, nrows=0)
        if set(df.columns) != expected_cols:
            console.print(f"[red]Column mismatch in {csv_path.name}[/red]")
            console.print(f"Expected: {sorted(expected_cols)}")
            console.print(f"Got: {sorted(df.columns)}")
            return False

    return True
