from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._vars import DOCX_FRAGMENT_COL, DOCX_ROW_INDEX_COL, DOCX_TABLE_INDEX_COL, KTP_FILENAME_COL
from .matchers.docx_matcher import normalize_docx_column_name
from .parse_docx import parse_docx_table


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
