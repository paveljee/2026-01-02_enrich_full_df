from __future__ import annotations

import duckdb
import pytest

from src import _vars
from src._vars import HCR_FILENAME_COL, KTP_POPULATION_INDEX_COL
from src.data_models import FragmentType, ResourceGroup
from src.hcr_xlsx.indexer import index_samples
from src.hcr_xlsx.loader import build_population_table
from src.hcr_xlsx.matcher import match_population
from src.hcr_xlsx.preprocessor import load_high_income_economies
from src.hcr_xlsx.sampler import sample_pilot, sample_population
from src.utils.resources import register_resource, register_resources
from tests.real_data_utils import (
    WORLD_BANK_XLSX,
    infer_name_columns_from_xlsx,
    list_hcr_xlsx_files,
)


def test_hcr_xlsx_pipeline_real_data(monkeypatch: pytest.MonkeyPatch) -> None:
    xlsx_files = list_hcr_xlsx_files(limit=2)
    if not xlsx_files or not WORLD_BANK_XLSX.exists():
        pytest.skip("Real HCR XLSX or World Bank data not available.")

    name_mapping: dict[str, tuple[str, str]] = {}
    for path in xlsx_files:
        mapping = infer_name_columns_from_xlsx(path)
        if mapping is None:
            pytest.skip(f"Could not infer name columns for {path.name}")
        name_mapping[path.name] = mapping

    original = dict(_vars.HCR_XLSX_NAME_COLS)
    _vars.HCR_XLSX_NAME_COLS.clear()
    _vars.HCR_XLSX_NAME_COLS.update(name_mapping)

    conn = duckdb.connect()
    try:
        xlsx_resources = register_resources(
            xlsx_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        )
        wb_resource = register_resource(
            WORLD_BANK_XLSX,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        )

        build_population_table(
            conn,
            xlsx_resources,
            table_name="population",
            filename_col=HCR_FILENAME_COL,
            row_col="hcr.row_number",
            population_index_col=KTP_POPULATION_INDEX_COL,
        )

        economies = load_high_income_economies(wb_resource)
        sample_population(
            conn,
            population_table="population",
            samples_table="samples",
            draw_sizes=[5],
            seed=42,
            economies=economies,
        )
        if any(path.name == "2024_HCR.xlsx" for path in xlsx_files):
            sample_pilot(
                conn,
                population_table="population",
                samples_table="samples",
                pilot_filename="2024_HCR.xlsx",
                economies=economies,
            )

        outer = index_samples(conn, samples_table="samples")
        match_population(conn, outer, population_table="population", resources=xlsx_resources)
    finally:
        conn.close()
        _vars.HCR_XLSX_NAME_COLS.clear()
        _vars.HCR_XLSX_NAME_COLS.update(original)

    assert outer.data
    assert any(inner_list for inner_list in outer.data.values())
