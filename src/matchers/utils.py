from __future__ import annotations

import pandas as pd

from .._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from ..data_models import NameKey, OuterDict

NAME_KEY_COL = "name_key"


def build_name_key_frame(outer_dict: OuterDict) -> pd.DataFrame:
    rows = []
    for key in outer_dict.data:
        name_key = NameKey.from_json_key(key)
        rows.append(
            {
                NAME_KEY_COL: key,
                KTP_FIRST_NAME_COL: name_key.first_name,
                KTP_LAST_NAME_COL: name_key.last_name,
            }
        )
    return pd.DataFrame(rows, columns=[NAME_KEY_COL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL])
