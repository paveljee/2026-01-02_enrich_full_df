from __future__ import annotations

import pandas as pd

from .name_utils import unify_first_last


def apply_unify_first_last(df: pd.DataFrame) -> pd.DataFrame:
    unified = df.apply(unify_first_last, axis=1, result_type="expand")
    first_data = pd.DataFrame(unified[0].tolist(), index=df.index)
    last_data = pd.DataFrame(unified[1].tolist(), index=df.index)
    for data in (first_data, last_data):
        for col in data.columns:
            df[col] = data[col]
    return df
