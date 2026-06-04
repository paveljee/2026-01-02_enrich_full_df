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
from src.helpers.duckdb_extensions import load_duckdb_extension_from_config_path
from src.helpers.pipeline_manager import PipelineManager
from src.helpers.resources import (
    PipelineResources,
    register_resource,
    register_resources,
)
from src.helpers.vars import (
    DRAW_LABEL,
    HCR_XLSX_KEY_PREFIX,
    KTP_FILENAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_FILENAME_COL,
    KTP_HCR_FILENAME_COL_LEGACY,
    KTP_HCR_ROW_NUMBER_COL,
    KTP_HCR_ROW_NUMBER_COL_LEGACY,
    REQUIRED_FILES_CONFIG_KEYS,
)
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
        load_duckdb_extension_from_config_path(conn, "splink_udfs")
        xlsx_resources = register_resources(
            xlsx_files,
            group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.EXCEL_ROW,
        )
        world_bank_resource = register_resource(
            world_bank,
            group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.EXCEL_ROW,
        )
        openalex_log = tmp_path / "openalex_author_search_log.jsonl"
        openalex_log.write_text("", encoding="utf-8")
        openalex_resource = register_resource(
            openalex_log,
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=FragmentType.CSV_ROW,
        )
        openalex_title_log = tmp_path / "openalex_paper_title_log.jsonl"
        openalex_title_log.write_text("", encoding="utf-8")
        openalex_title_resource = register_resource(
            openalex_title_log,
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=FragmentType.CSV_ROW,
        )
        files_config = {
            key: {"path": "dummy", "sha256": "dummy", "desc": "dummy"}
            for key in REQUIRED_FILES_CONFIG_KEYS
        }
        files_config[f"{HCR_XLSX_KEY_PREFIX}dummy"] = {
            "path": "dummy",
            "sha256": "dummy",
            "desc": "dummy",
        }
        config = PipelineConfig(
            files_config=files_config,
            db_file=tmp_path / "pipeline.duckdb",
            state_file=tmp_path / "pipeline_state.json",
            output_dir=tmp_path / "output",
            output_format="txt",
            pandoc_reference_docx=tmp_path / "reference.docx",
            docx_dir=tmp_path,
            timezone="America/Toronto",
            sample_seed=42,
            sample_draw_sizes=[
                {"size": 20, "replace": True},
                {"size": 40, "replace": True},
                {"size": 40, "replace": True},
                {"size": 40, "replace": True},
                {"size": 40, "replace": True},
                {"size": 40, "replace": True},
                {"size": 40, "replace": True},
                {"size": 40, "replace": True},
            ],
            pilot_xlsx_name="2024_HCR.xlsx",
            total_draws=310,
            card_subset_mode=0,
        )

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
            openalex_author_search_log_resource=openalex_resource,
            openalex_paper_title_log_resource=openalex_title_resource,
        )

        run_load_xlsx(context)
        run_infer_names(context)
        run_add_economy_priority(context)
        run_sampling(context)

        sample_df = conn.execute(
            f"""
            SELECT "{KTP_FILENAME_COL}" AS "{KTP_HCR_FILENAME_COL}",
                   "{KTP_FRAGMENT_COL}" AS "{KTP_HCR_ROW_NUMBER_COL}",
                   "{DRAW_LABEL}" AS "ktp.draw_number"
            FROM samples
            """
        ).df()

        csv_df = pd.concat([pd.read_csv(path) for path in csv_files], ignore_index=True)
        csv_df = csv_df.rename(
            columns={
                KTP_HCR_FILENAME_COL_LEGACY: KTP_HCR_FILENAME_COL,
                KTP_HCR_ROW_NUMBER_COL_LEGACY: KTP_HCR_ROW_NUMBER_COL,
            }
        )
        csv_df = csv_df[[KTP_HCR_FILENAME_COL, KTP_HCR_ROW_NUMBER_COL, DRAW_LABEL]].copy()

        for col in [KTP_HCR_FILENAME_COL, KTP_HCR_ROW_NUMBER_COL, DRAW_LABEL]:
            sample_df[col] = sample_df[col].astype(str)
            csv_df[col] = csv_df[col].astype(str)

        sample_rows = Counter(
            zip(
                sample_df[KTP_HCR_FILENAME_COL],
                sample_df[KTP_HCR_ROW_NUMBER_COL],
                sample_df[DRAW_LABEL],
            )
        )
        csv_rows = Counter(
            zip(
                csv_df[KTP_HCR_FILENAME_COL],
                csv_df[KTP_HCR_ROW_NUMBER_COL],
                csv_df[DRAW_LABEL],
            )
        )

        assert sample_rows == csv_rows
    finally:
        conn.close()
