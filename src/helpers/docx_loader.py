from __future__ import annotations

from pathlib import Path

import pandas as pd

from .._vars import KTP_FILENAME_COL
from ..data_models import RegisteredResource
from ..manual_docx.loader import normalize_docx_column_name
from ..parse_docx import parse_docx_table


DOCX_ROW_NUMBER_COL = "ktp.table_1_row_number"


def load_single_table_docx(resources: dict[str, RegisteredResource]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for resource in resources.values():
        path = Path(resource.__fspath__())
        tables = parse_docx_table(path)
        if len(tables) != 1:
            raise ValueError(
                f"Expected exactly one table in DOCX '{path.name}', got {len(tables)}"
            )
        table = tables[0].copy()
        table.columns = [normalize_docx_column_name(col) for col in table.columns]
        table[KTP_FILENAME_COL] = path.name
        table[DOCX_ROW_NUMBER_COL] = range(1, len(table) + 1)
        frames.append(table)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


__all__ = ["load_single_table_docx", "normalize_docx_column_name", "DOCX_ROW_NUMBER_COL"]
