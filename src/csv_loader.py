from __future__ import annotations

from pathlib import Path

import pandas as pd

from ._vars import CSV_ROW_INDEX_COL, KTP_FILENAME_COL


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
