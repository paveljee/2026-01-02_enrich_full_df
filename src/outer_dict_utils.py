from __future__ import annotations

import pandas as pd

from src.data_models import NameKey, OuterDict


def build_outer_dict_from_names(names: pd.DataFrame) -> OuterDict:
    name_keys = [
        NameKey(first_name=first, last_name=last)
        for first, last in names.itertuples(index=False, name=None)
    ]
    return OuterDict.from_name_keys(name_keys)
