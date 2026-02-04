from __future__ import annotations

import duckdb
import pytest

from src._vars import DOCX_FRAGMENT_COL, RIGHT_NAME_COL
from src.data_models import FragmentType, NameKey, OuterDict, ResourceGroup
from src.manual_docx.loader import load_docx_tables, normalize_docx_column_name
from src.manual_docx.matcher import match_docx
from src.utils.resources import register_resources
from tests.real_data_utils import extract_first_last, list_docx_files


def test_manual_docx_pipeline_real_data() -> None:
    docx_files = list_docx_files(limit=2)
    if not docx_files:
        pytest.skip("Real DOCX data not available.")

    resources = register_resources(
        docx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.DOCX_ROW,
    )
    docx_df = load_docx_tables(resources)
    if docx_df.empty:
        pytest.skip("No DOCX tables parsed from real data.")

    name_col = RIGHT_NAME_COL
    if name_col not in docx_df.columns:
        normalized = normalize_docx_column_name(RIGHT_NAME_COL)
        if normalized not in docx_df.columns:
            pytest.skip("DOCX name column not found in parsed tables.")
        name_col = normalized

    name_series = docx_df[name_col].dropna().astype(str)
    picked: list[NameKey] = []
    for value in name_series.head(10):
        parsed = extract_first_last(value)
        if parsed:
            first, last = parsed
            picked.append(NameKey(first_name=first, last_name=last))
        if len(picked) >= 3:
            break

    if not picked:
        pytest.skip("Could not extract candidate names from DOCX tables.")

    outer = OuterDict.from_name_keys(picked)

    conn = duckdb.connect()
    try:
        match_docx(conn, outer, docx_df, resources, fragment_col=DOCX_FRAGMENT_COL)
    finally:
        conn.close()

    assert any(inner_list for inner_list in outer.data.values())
