from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.helpers.data_models import FragmentType, ResourceGroup
from src.helpers.resources import register_resource
from src.helpers.vars import (
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    KTP_FILENAME_COL,
)
from src.steps.step_08_match_docx import load_docx_tables, normalize_docx_column_name


def test_normalize_docx_column_name_rules() -> None:
    assert normalize_docx_column_name("hcr.name") == "hcr.name"
    assert normalize_docx_column_name("Name (full)") == "ktp.table_1_name_full_"
    assert normalize_docx_column_name("  Mixed  Case ") == "ktp.table_1_mixed_case_"


def test_load_docx_tables_adds_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    docx_path = tmp_path / "sample.docx"
    docx_path.write_text("stub", encoding="utf-8")

    table = pd.DataFrame({"Researcher/author": ["Ada", "Grace"], "Notes": ["A", "B"]})

    def fake_parse_docx_table(_: Path) -> list[pd.DataFrame]:
        return [table]

    monkeypatch.setattr("src.steps.step_08_match_docx.parse_docx_table", fake_parse_docx_table)

    resources = {
        docx_path.name: register_resource(
            docx_path,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.DOCX_ROW,
        )
    }

    df = load_docx_tables(resources)

    assert len(df) == 2
    assert df[KTP_FILENAME_COL].unique().tolist() == [docx_path.name]
    assert df[DOCX_TABLE_INDEX_COL].tolist() == [0, 0]
    assert df[DOCX_ROW_INDEX_COL].tolist() == [0, 1]
    assert df[DOCX_FRAGMENT_COL].tolist() == ["table0_row0", "table0_row1"]
