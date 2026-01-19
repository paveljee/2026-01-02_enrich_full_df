import pandas as pd

from ._vars import (
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_FIRST_NAME_ORIG_COLNAME_COL,
    KTP_LAST_NAME_ORIG_COLNAME_COL,
)

def unify_first_last(row: pd.Series) -> tuple[dict[str, str], dict[str, str]]:
    """
    Return (first_name, last_name) from a row, agnostic of output column names.
    """
    expected_cols = ['hcr.firstname_middlename', 'hcr.lastname', 'hcr.familyname', 'hcr.first_name', 'hcr.last_name', 'hcr.firstname']
    
    found_names = {
        col: row[col] for col in expected_cols
             if col in row.index and row.get(col) is not None
    }

    if ((k := len(found_names.items())) == 0):
        raise ValueError(f"[unify_names] Expected columns not found in dataframe: {expected_cols}")
    elif k > 2:
        raise ValueError(f"[unify_names] More than two col names per row ({found_names}):\n{row}")
    elif k < 2:
        raise ValueError(f"[unify_names] Fewer than two col names per row ({found_names}):\n{row}")
    else:
        first = next(
            {
                KTP_FIRST_NAME_ORIG_COLNAME_COL: col,
                KTP_FIRST_NAME_COL: val,
            } for col, val in found_names.items() if 'first' in str(col)
        )
        last = next(
            {
                KTP_LAST_NAME_ORIG_COLNAME_COL: col,
                KTP_LAST_NAME_COL: val,
            } for col, val in found_names.items() if col != first[KTP_FIRST_NAME_ORIG_COLNAME_COL]
        )

    return first, last
