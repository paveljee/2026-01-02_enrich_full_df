from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from ._vars import KTP_FILENAME_COL
from .parse_docx import parse_docx_table

CSV_ROW_INDEX_COL = "ktp.csv_row_index"
DOCX_TABLE_INDEX_COL = "ktp.docx_table_index"
DOCX_ROW_INDEX_COL = "ktp.docx_row_index"
DOCX_FRAGMENT_COL = "ktp.docx_fragment"


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


def normalize_docx_column_name(column: str) -> str:
    if re.match(r"^[\w_]+\.", str(column)):
        return str(column)
    normalized = re.sub(r"[^\w\s]", "_", str(column).lower())
    normalized = re.sub(r"\s", "_", normalized)
    normalized = f"ktp.table_1_{normalized}"
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def load_csv_files(csv_files: list[Path]) -> pd.DataFrame:
    frames = []
    for csv_path in csv_files:
        df = pd.read_csv(csv_path)
        df = df.reset_index(drop=False).rename(columns={"index": CSV_ROW_INDEX_COL})
        df[KTP_FILENAME_COL] = csv_path.name
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_docx_tables(docx_files: list[Path]) -> pd.DataFrame:
    frames = []
    for docx_path in docx_files:
        tables = parse_docx_table(docx_path)
        for table_index, df in enumerate(tables):
            table = df.copy()
            table.columns = [normalize_docx_column_name(col) for col in table.columns]
            table[KTP_FILENAME_COL] = docx_path.name
            table[DOCX_TABLE_INDEX_COL] = table_index
            table[DOCX_ROW_INDEX_COL] = range(len(table))
            table[DOCX_FRAGMENT_COL] = [
                f"table{table_index}_row{row_index}" for row_index in range(len(table))
            ]
            frames.append(table)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
