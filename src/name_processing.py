from __future__ import annotations

import pandas as pd

from src.name_utils import unify_first_last


def apply_unified_names(df: pd.DataFrame) -> pd.DataFrame:
    unified_names = df.apply(unify_first_last, axis=1, result_type="expand")
    first_data = pd.DataFrame(unified_names[0].tolist(), index=df.index)
    last_data = pd.DataFrame(unified_names[1].tolist(), index=df.index)
    for data in (first_data, last_data):
        for col in data.columns:
            df[col] = data[col]
    return df
