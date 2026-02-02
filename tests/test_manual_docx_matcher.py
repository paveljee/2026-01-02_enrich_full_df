from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from src._vars import DOCX_FRAGMENT_COL
from src.data_models import FragmentType, NameKey, OuterDict, ResourceGroup
from src.manual_docx.matcher import match_docx
from src.utils.resources import register_resource


def test_match_docx_missing_name_column(tmp_path) -> None:
    docx_path = tmp_path / "missing.docx"
    docx_path.write_text("stub", encoding="utf-8")
    resources = {
        docx_path.name: register_resource(
            docx_path,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.DOCX_ROW,
        )
    }

    outer = OuterDict.from_name_keys([NameKey(first_name="Ada", last_name="Lovelace")])
    docx_df = pd.DataFrame(
        [{"Some Column": "Ada Lovelace", DOCX_FRAGMENT_COL: "table0_row0"}]
    )

    conn = duckdb.connect()
    try:
        with pytest.raises(ValueError, match="does not contain expected name column"):
            match_docx(conn, outer, docx_df, resources, fragment_col=DOCX_FRAGMENT_COL)
    finally:
        conn.close()
