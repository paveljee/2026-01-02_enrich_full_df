import re

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
    csv_names: pd.DataFrame,
    docx_names: pd.Series,
    max_error_rows: int = 10,
) -> pd.Series:
    """
    Match CSV first/last names to DOCX combined-name strings using literal
    substring checks (case-insensitive), after stripping non-alphanumeric chars
    from each compared string.

    For each row in `csv_names`, find DOCX rows whose `docx_names` value contains
    BOTH the first-name substring and the last-name substring. If exactly one
    DOCX row matches, return that DOCX index for the CSV row; otherwise mark as
    unmatched (NA). After scanning all rows, raise if any CSV row did not have
    exactly one match.

    Parameters
    ----------
    csv_names : pd.DataFrame
        DataFrame with exactly two columns: [first_name, last_name] in that order.
        Must be a real DataFrame (use double brackets upstream). The index is
        preserved and used as the index of the returned Series.
    docx_names : pd.Series
        Series of DOCX combined-name strings to search (index are DOCX row indices).
    max_error_rows : int, optional
        Maximum number of failing CSV rows to include in the error message if
        matching fails. Defaults to 10.

    Returns
    -------
    pd.Series
        Series aligned to `csv_names.index` whose values are matching DOCX indices.

    Raises
    ------
    ValueError
        If any CSV row has zero matches or multiple matches in `docx_names`.
    """

    if not isinstance(csv_names, pd.DataFrame):
        raise TypeError("csv_names must be a DataFrame with two columns [first, last].")
    if csv_names.shape[1] != 2:
        raise ValueError("csv_names must have exactly two columns: [first, last].")

    # Read-only views; do not mutate inputs.
    first_col = csv_names.columns[0]
    last_col = csv_names.columns[1]

    first = csv_names[first_col]
    last = csv_names[last_col]

    # Ensure we're searching strings; keep NA safe behavior.
    # (astype(str) would turn NaN into 'nan', so avoid that.)
    docx = docx_names

    # Pre-clean once for speed / clarity; still no mutation.
    # - Strip non-alphanumerics
    # - Casefold for robust case-insensitivity
    non_alnum_anywhere = re.compile(r"[^0-9A-Za-z]+")

    def _clean(s: pd.Series) -> pd.Series:
        s2 = s.astype("string")
        return (
            s2.str.replace(non_alnum_anywhere, "", regex=True)
              .str.casefold()
        )

    docx_clean = _clean(docx)
    docx_index = docx.index

    first_clean = _clean(first)
    last_clean = _clean(last)

    matched: list[object | None] = []
    failures: list[tuple[object, object, str, list[object] | None]] = []

    # Why not fully vectorized (single op)? A true all-at-once solution requires a
    # cross-product between CSV rows and DOCX rows (or complex regex construction),
    # which is usually memory-expensive and harder to reason about. This approach
    # pre-cleans once and then uses vectorized `.str.contains(..., regex=False)`
    # per CSV row, avoiding inner Python loops over DOCX rows.
    for csv_idx, f, l in zip(csv_names.index, first_clean.values, last_clean.values):
        if pd.isna(f) or pd.isna(l) or f == "" or l == "":
            failures.append((csv_idx, None, "NO_MATCH (missing first/last)", None))
            matched.append(pd.NA)
            continue

        # Literal substring check, case-insensitive, after edge-cleaning.
        mask = docx_clean.str.contains(f, na=False, regex=False) & docx_clean.str.contains(l, na=False, regex=False)
        hits = docx_index[mask].tolist()

        if len(hits) == 1:
            matched.append(hits[0])
        elif len(hits) == 0:
            failures.append((csv_idx, f, l, "NO_MATCH", None))
            matched.append(pd.NA)
        else:
            failures.append((csv_idx, f, l, "MULTIPLE_MATCHES", hits))
            matched.append(pd.NA)

    if failures:
        lines = []
        for (csv_idx, first_v, last_v, kind, hits) in failures[:max_error_rows]:
            name = f"{last_v}, {first_v}"
            if hits:
                lines.append(f"  {name} (csv_idx={csv_idx}) - {kind}: {hits}")
            else:
                lines.append(f"  {name} (csv_idx={csv_idx}) - {kind}")
        more = (
            ""
            if (n := len(failures)) <= max_error_rows
            else f"\n  ...(showing first {max_error_rows} of {n})"
        )
        raise ValueError(f"Could not uniquely match {n} CSV rows:\n" + "\n".join(lines) + more)

    return pd.Series(matched, index=csv_names.index, name="_docx_idx")
