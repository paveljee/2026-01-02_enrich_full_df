from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from src import _vars
from src._vars import (
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    KTP_ECONOMIES_COL,
    KTP_FILENAME_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_SOURCE_KEY_COL,
)
from src.cards import build_cards, write_cards_zip
from src.data_models import FragmentType, RegisteredResource, ResourceGroup
from src.hcr_xlsx.indexer import index_samples
from src.hcr_xlsx.loader import build_population_table
from src.hcr_xlsx.matcher import match_population
from src.hcr_xlsx.preprocessor import load_high_income_economies
from src.hcr_xlsx.sampler import sample_pilot, sample_population
from src.manual_docx.loader import load_docx_tables
from src.manual_docx.matcher import match_docx
from src.sciscinet_parquet.matcher import match_parquet
from src.utils.name_keys import NAME_KEY_COL
from src.utils.resources import register_resource, register_resources
from tests.real_data_utils import (
    SCISCINET_AUTHOR_DETAILS,
    SCISCINET_AUTHORS_PAPER,
    SCISCINET_HIT_LEVEL0,
    SCISCINET_HIT_LEVEL1,
    WORLD_BANK_XLSX,
    infer_name_columns_from_xlsx,
    list_docx_files,
    list_hcr_xlsx_files,
)


def test_full_pipeline_real_data(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    xlsx_files = list_hcr_xlsx_files(limit=2)
    docx_files = list_docx_files(limit=2)
    if not xlsx_files or not docx_files or not WORLD_BANK_XLSX.exists():
        pytest.skip("Real HCR/DOCX/World Bank data not available.")

    if not (
        SCISCINET_AUTHOR_DETAILS.exists()
        and SCISCINET_AUTHORS_PAPER.exists()
        and SCISCINET_HIT_LEVEL0.exists()
        and SCISCINET_HIT_LEVEL1.exists()
    ):
        pytest.skip("SciSciNet parquet files not available.")

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
        conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
        xlsx_resources = register_resources(
            xlsx_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        )
        docx_resources = register_resources(
            docx_files,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.DOCX_ROW,
        )
        wb_resource = register_resource(
            WORLD_BANK_XLSX,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        )

        build_population_table(conn, xlsx_resources, table_name="population")
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

        docx_df = load_docx_tables(docx_resources)
        match_docx(conn, outer, docx_df, docx_resources, fragment_col=DOCX_FRAGMENT_COL)

        samples = conn.execute("SELECT * FROM samples").df()
        if NAME_KEY_COL not in samples.columns:
            pytest.skip("Samples table missing name_key column.")

        author_resource = RegisteredResource(
            name=SCISCINET_AUTHOR_DETAILS.name,
            hash="skip",
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
            url=SCISCINET_AUTHOR_DETAILS.resolve().as_uri(),
            verify_hash_on_init=False,
        )

        match_parquet(
            conn,
            outer,
            samples,
            {author_resource.name: author_resource},
            author_details_path=str(SCISCINET_AUTHOR_DETAILS),
            authors_paper_path=str(SCISCINET_AUTHORS_PAPER),
            hit_papers_level0_path=str(SCISCINET_HIT_LEVEL0),
            hit_papers_level1_path=str(SCISCINET_HIT_LEVEL1),
        )

        excluded_cols = {
            KTP_FILENAME_COL,
            KTP_SOURCE_KEY_COL,
            CSV_ROW_INDEX_COL,
            DOCX_TABLE_INDEX_COL,
            DOCX_ROW_INDEX_COL,
            DOCX_FRAGMENT_COL,
            KTP_ECONOMIES_COL,
            KTP_PRIORITY_COL,
            KTP_PRIORITY_GROUP_COL,
        }
        total_draws = len(samples)
        cards = build_cards(
            outer,
            total_draws=total_draws,
            intro_date="2026-02-02",
            excluded_cols=excluded_cols,
        )

        zip_path = write_cards_zip(
            cards,
            tmp_path,
            "cards_realdata.zip",
            output_format="txt",
            reference_docx=Path("resources/pandoc-custom-reference.docx"),
        )
    finally:
        conn.close()
        _vars.HCR_XLSX_NAME_COLS.clear()
        _vars.HCR_XLSX_NAME_COLS.update(original)

    assert cards
    assert zip_path.exists()
