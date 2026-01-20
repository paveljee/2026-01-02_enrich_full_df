from typing import Callable

import pandas as pd

from ._vars import (
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_FIRST_NAME_ORIG_COLNAME_COL,
    KTP_LAST_NAME_ORIG_COLNAME_COL,
    RIGHT_NAME_COL,
)

def unify_first_last(row: pd.Series) -> tuple[dict[str, str], dict[str, str]]:
    """
    Return (first_name, last_name) from a row, agnostic of output column names.
    """
    expected_cols = ['hcr.firstname_middlename', 'hcr.lastname', 'hcr.familyname', 'hcr.first_name', 'hcr.last_name', 'hcr.firstname']
    
    is_nonempty_str = lambda x: isinstance(x, str) and len(x) > 0  # to account for nan etc.
    found_names = {
        col: row[col] for col in expected_cols
             if col in row.index and is_nonempty_str(row.get(col))
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

def match_csv_docx_names(
    first_names: pd.Series,
    last_names: pd.Series,
    docx_names: pd.Series
) -> pd.Series:
    """
    Match CSV first/last names to DOCX combined names.
    
    This addresses the mismatch between CSV samples, which (sloppily)
    used the original `hcr.` colnames, separate for first, last name,
    and DOCX Table 1, which uses a single column combining the first
    and last name in a human-readable yet manual (non-deterministic) way.
    
    Parameters
    ----------
    first_names : pd.Series
        Series of first names from CSV (will be copied)
    last_names : pd.Series
        Series of last names from CSV (will be copied)
    docx_names : pd.Series
        Series of combined names from DOCX (will be copied)
    
    Returns
    -------
    pd.Series
        Series of matched DOCX indices (same length as first_names/last_names),
        with NaN for unmatched rows
    
    Raises
    ------
    ValueError
        If any rows have 0 or >1 matches
    """
    orig_index = first_names.index.copy()

    # Lambda to copy, reset index. Keeps original versions for error reporting
    orig: Callable[[pd.Series], pd.Series] = lambda s: s.copy().reset_index(drop=True)
    first_orig = orig(first_names)
    last_orig = orig(last_names)
    docx_orig = orig(docx_names)

    # Lambda to copy, reset index, and lowercase for matching
    # prep: Callable[[pd.Series], pd.Series] = lambda s: orig(s).str.lower()
    # to use above if non-lowercases doesn't work
    prep: Callable[[pd.Series], pd.Series] = lambda s: orig(s)
    first_prepped = prep(first_names)
    last_prepped = prep(last_names)
    docx_prepped = prep(docx_names)
    
    match_failures = []
    matched_indices = []
    
    for idx in range(len(first_prepped)):
        first = first_prepped.iloc[idx]
        last = last_prepped.iloc[idx]
        
        # Find docx rows where name contains both first and last
        mask = (
            docx_prepped.str.contains(first, na=False, regex=False) &
            docx_prepped.str.contains(last, na=False, regex=False)
        )
        matches = docx_orig[mask]
        
        if len(matches) == 0:
            match_failures.append((
                first_orig.iloc[idx],
                last_orig.iloc[idx],
                "NO_MATCH",
                None
            ))
            matched_indices.append(None)
        elif len(matches) > 1:
            match_failures.append((
                first_orig.iloc[idx],
                last_orig.iloc[idx],
                "MULTIPLE_MATCHES",
                matches.tolist()
            ))
            matched_indices.append(None)
        else:
            matched_indices.append(matches.index[0])
    
    # Raise exception if there were matching failures
    if match_failures:
        failure_msg = "\n".join([
            f"  {last}, {first} - {error}" + (f": {matches}" if matches else "")
            for first, last, error, matches in match_failures[:10]
        ])
        raise ValueError(
            f"Could not uniquely match {len(match_failures)} CSV rows:\n{failure_msg}\n"
            f"{'...(showing first 10 of ' + str(len(match_failures)) + ')' if len(match_failures) > 10 else ''}"
        )
    
    return pd.Series(matched_indices, index=orig_index)
