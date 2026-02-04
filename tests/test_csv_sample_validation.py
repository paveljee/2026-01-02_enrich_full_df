from __future__ import annotations

from collections import Counter
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.helpers.config import PipelineConfig
from src.helpers.context import PipelineContext
from src.helpers.data_models import FragmentType, ResourceGroup
from src.helpers.diagnostics import DiagnosticsReport
from src.helpers.pipeline_manager import PipelineManager
from src.helpers.resources import (
    PipelineResources,
    register_resource,
    register_resources,
)
from src.helpers.vars import DRAW_LABEL, KTP_FILENAME_COL, KTP_FRAGMENT_COL
from src.steps.step_02_load_xlsx import run as run_load_xlsx
from src.steps.step_03_infer_names import run as run_infer_names
from src.steps.step_04_add_economy_priority import run as run_add_economy_priority
from src.steps.step_05_sampling import run as run_sampling


def test_csv_rows_match_samples(tmp_path: Path) -> None:
    data_dir = Path("data")
    xlsx_dir = data_dir / "2024-Historical-Highly-Cited-Researchers-lists - final"
    csv_dir = data_dir / "samples"
    world_bank = data_dir / "OGHIST_2025_07_01.xlsx"

    if not xlsx_dir.exists() or not csv_dir.exists():
        pytest.skip("Sample data not available for CSV validation.")

    xlsx_files = sorted(xlsx_dir.glob("*.xlsx"))
    if not xlsx_files:
        pytest.skip("No XLSX files available for CSV validation.")

    csv_files = sorted(csv_dir.glob("*.csv"))
    if not csv_files:
        pytest.skip("No CSV files available for CSV validation.")

    if not world_bank.exists():
        pytest.skip("World Bank file not available for CSV validation.")

    conn = duckdb.connect()
    try:
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
        config = PipelineConfig()
        config.sample_draw_sizes = [20] + [40] * 7
        config.sample_seed = 42
        config.pilot_xlsx_name = "2024_HCR.xlsx"

        manager = PipelineManager(
            state_file=tmp_path / "pipeline_state.json",
            db_file=tmp_path / "pipeline.duckdb",
        )
        diagnostics = DiagnosticsReport(tmp_path)
        context = PipelineContext(
            config=config,
            manager=manager,
            conn=conn,
            diagnostics=diagnostics,
            interactive=False,
            artifacts_dir=tmp_path / "artifacts",
        )
        context.resources = PipelineResources(
            parquet_resources={},
            xlsx_resources=xlsx_resources,
            world_bank_resource=world_bank_resource,
            docx_resources={},
        )

        run_load_xlsx(context)
        run_infer_names(context)
        run_add_economy_priority(context)
        run_sampling(context)

        sample_df = conn.execute(
            f"""
            SELECT "{KTP_FILENAME_COL}" AS "hcr.filename",
                   "{KTP_FRAGMENT_COL}" AS "hcr.row_number",
                   "{DRAW_LABEL}" AS "ktp.draw_number"
            FROM samples
            """
        ).df()

        csv_df = pd.concat([pd.read_csv(path) for path in csv_files], ignore_index=True)
        csv_df = csv_df[["hcr.filename", "hcr.row_number", "ktp.draw_number"]].copy()

        for col in ["hcr.filename", "hcr.row_number", "ktp.draw_number"]:
            sample_df[col] = sample_df[col].astype(str)
            csv_df[col] = csv_df[col].astype(str)

        sample_rows = Counter(
            zip(
                sample_df["hcr.filename"],
                sample_df["hcr.row_number"],
                sample_df["ktp.draw_number"],
            )
        )
        csv_rows = Counter(
            zip(
                csv_df["hcr.filename"],
                csv_df["hcr.row_number"],
                csv_df["ktp.draw_number"],
            )
        )

        assert sample_rows == csv_rows
    finally:
        conn.close()
