from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from .._vars import (
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    KTP_FILENAME_COL,
)
from ..data_models import RegisteredResource
from ..parse_docx import parse_docx_table


def normalize_docx_column_name(column: str) -> str:
    if re.match(r"^[\w_]+\.", str(column)):
        return str(column)
    normalized = re.sub(r"[^\w\s]", "_", str(column).lower())
    normalized = re.sub(r"\s", "_", normalized)
    normalized = f"ktp.table_1_{normalized}"
    normalized = re.sub(r"_+", "_", normalized)
    return normalized


def load_docx_tables(resources: dict[str, RegisteredResource]) -> pd.DataFrame:
    frames = []
    for resource in resources.values():
        path = Path(resource.__fspath__())
        tables = parse_docx_table(path)
        for table_index, df in enumerate(tables):
            table = df.copy()
            table.columns = [normalize_docx_column_name(col) for col in table.columns]
            table[KTP_FILENAME_COL] = path.name
            table[DOCX_TABLE_INDEX_COL] = table_index
            table[DOCX_ROW_INDEX_COL] = range(len(table))
            table[DOCX_FRAGMENT_COL] = [
                f"table{table_index}_row{row_index}" for row_index in range(len(table))
            ]
            frames.append(table)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
