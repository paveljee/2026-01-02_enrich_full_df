from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src import _vars
from src._vars import HCR_FILENAME_COL, KTP_POPULATION_INDEX_COL
from src.data_models import FragmentType, ResourceGroup
from src.hcr_xlsx.loader import build_population_table
from src.hcr_xlsx.preprocessor import load_high_income_economies
from src.hcr_xlsx.sampler import sample_pilot, sample_population
from src.utils.resources import register_resource, register_resources
from tests.real_data_utils import (
    infer_name_columns_from_xlsx,
)


def test_csv_rows_match_samples(tmp_path: Path) -> None:
    data_dir = Path("data")
    xlsx_dir = data_dir / "2024-Historical-Highly-Cited-Researchers-lists - final"
    csv_dir = data_dir / "samples"
    world_bank = data_dir / "OGHIST_2025_07_01.xlsx"

    if not xlsx_dir.exists() or not csv_dir.exists() or not world_bank.exists():
        pytest.skip("Sample data not available for CSV validation.")

    xlsx_files = sorted(xlsx_dir.glob("*.xlsx"))
    if not xlsx_files:
        pytest.skip("No XLSX files available for CSV validation.")

    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        pytest.skip("No CSV files available for CSV validation.")

    conn = duckdb.connect()
    xlsx_resources = register_resources(
        xlsx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.EXCEL_ROW,
    )
    world_bank_resource = register_resource(
        world_bank,
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

    economies = load_high_income_economies(world_bank_resource)
    sample_population(
        conn,
        population_table="population",
        samples_table="samples",
        draw_sizes=[20] + [40] * 7,
        seed=42,
        economies=economies,
    )
    pilot_path = xlsx_dir / "2024_HCR.xlsx"
    if not pilot_path.exists():
        pytest.skip("Pilot XLSX not available for CSV validation.")
    mapping = infer_name_columns_from_xlsx(pilot_path)
    if not mapping:
        pytest.skip("Could not infer pilot name columns for CSV validation.")

    original = dict(_vars.HCR_XLSX_NAME_COLS)
    _vars.HCR_XLSX_NAME_COLS.clear()
    _vars.HCR_XLSX_NAME_COLS.update({pilot_path.name: mapping})
    try:
        sample_pilot(
            conn,
            population_table="population",
            samples_table="samples",
            pilot_filename="2024_HCR.xlsx",
            economies=economies,
        )
    finally:
        _vars.HCR_XLSX_NAME_COLS.clear()
        _vars.HCR_XLSX_NAME_COLS.update(original)

    csv_df = pd.concat([pd.read_csv(path) for path in csv_files], ignore_index=True)
    csv_df["__csv_id"] = range(len(csv_df))
    sample_df = conn.execute("SELECT * FROM samples").df()

    shared_columns = [col for col in csv_df.columns if col in sample_df.columns]
    if not shared_columns:
        pytest.skip("No shared columns between CSV and samples tables.")

    conn.register("csv_data", csv_df)
    conn.execute("CREATE OR REPLACE TABLE csv_data AS SELECT * FROM csv_data")

    join_conditions = " AND ".join([f'c."{col}" = s."{col}"' for col in shared_columns])
    mismatches = conn.execute(
        f"""
        SELECT c.__csv_id, COUNT(*) AS match_count
        FROM csv_data c
        LEFT JOIN samples s ON {join_conditions}
        GROUP BY c.__csv_id
        HAVING COUNT(*) != 1
        """
    ).df()

    conn.close()

    assert mismatches.empty, "CSV rows do not uniquely match samples table."
