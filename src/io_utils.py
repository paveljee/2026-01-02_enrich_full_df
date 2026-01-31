from __future__ import annotations

from pathlib import Path

import pandas as pd


def find_files_by_extension(directory: Path, extension: str, recursive: bool = False) -> list[Path]:
    pattern = f"*.{extension}"
    if recursive:
        return list(directory.rglob(pattern))
    return list(directory.glob(pattern))


def validate_csv_headers(csv_files: list[Path]) -> bool:
    if not csv_files:
        return False

    first_df = pd.read_csv(csv_files[0], nrows=0)
    expected_cols = set(first_df.columns)

    for csv_path in csv_files[1:]:
        df = pd.read_csv(csv_path, nrows=0)
        if set(df.columns) != expected_cols:
            return False

    return True
