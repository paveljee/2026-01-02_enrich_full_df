from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src._vars import (
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    KTP_FILENAME_COL,
    RIGHT_NAME_COL,
)
from src.parse_docx import parse_docx_table


def normalize_docx_column_name(column: str) -> str:
    if re.match(r"^[\w_]+\.", str(column)):
        return str(column)
    normalized = re.sub(r"[^\w\s]", "_", str(column).lower())
    normalized = re.sub(r"\s", "_", normalized)
    normalized = f"ktp.table_1_{normalized}"
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def load_docx_tables(docx_files: list[Path]) -> pd.DataFrame:
    all_frames = []
    for docx_path in docx_files:
        tables = parse_docx_table(docx_path)
        for table_index, df in enumerate(tables):
            df = df.copy()
            df.columns = [normalize_docx_column_name(col) for col in df.columns]
            df[KTP_FILENAME_COL] = docx_path.name
            df[DOCX_TABLE_INDEX_COL] = table_index
            df[DOCX_ROW_INDEX_COL] = range(len(df))
            df[DOCX_FRAGMENT_COL] = [
                f"table{table_index}_row{row_index}" for row_index in range(len(df))
            ]
            all_frames.append(df)
    if not all_frames:
        return pd.DataFrame()
    return pd.concat(all_frames, ignore_index=True)


def resolve_docx_name_column(docx_df: pd.DataFrame) -> str:
    if RIGHT_NAME_COL in docx_df.columns:
        return RIGHT_NAME_COL
    normalized = normalize_docx_column_name(RIGHT_NAME_COL)
    if normalized in docx_df.columns:
        return normalized
    raise ValueError(
        f"Docx data does not contain expected name column '{RIGHT_NAME_COL}' "
        f"or normalized '{normalized}'."
    )
