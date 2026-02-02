from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import duckdb
import pandas as pd
import pytest

from src import _vars
from src._vars import (
    DOCX_FRAGMENT_COL,
    DRAW_LABEL,
    HCR_FILENAME_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_SOURCE_KEY_COL,
    RIGHT_NAME_COL,
)
from src.cards import build_cards, write_cards_zip
from src.data_models import FragmentType, NameKey, ResourceGroup
from src.hcr_xlsx.indexer import index_samples
from src.hcr_xlsx.loader import build_population_table
from src.hcr_xlsx.matcher import match_population
from src.hcr_xlsx.sampler import sample_population
from src.manual_docx.matcher import match_docx
from src.sciscinet_parquet.matcher import match_parquet
from src.utils.name_keys import NAME_KEY_COL
from src.utils.resources import register_resource


def _write_xlsx(path: Path, df: pd.DataFrame) -> None:
    df.to_excel(path, index=False, engine="openpyxl")


def _write_parquet(path: Path, create_sql: str, insert_sql: str) -> None:
    conn = duckdb.connect()
    try:
        conn.execute(create_sql)
        conn.execute(insert_sql)
        conn.execute(f"COPY (SELECT * FROM input) TO '{path}' (FORMAT 'parquet')")
    finally:
        conn.close()


def test_repl_pipeline_minimal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xlsx_path = tmp_path / "2019_HCR.xlsx"
    _write_xlsx(
        xlsx_path,
        pd.DataFrame({"First Name": ["Ada"], "Last Name": ["Lovelace"]}),
    )

    monkeypatch.setitem(
        _vars.HCR_XLSX_NAME_COLS,
        xlsx_path.name,
        ("hcr.first_name", "hcr.last_name"),
    )

    xlsx_resources = {
        xlsx_path.name: register_resource(
            xlsx_path,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        )
    }

    conn = duckdb.connect()
    try:
        build_population_table(conn, xlsx_resources, table_name="population")
        sample_population(
            conn,
            population_table="population",
            samples_table="samples",
            draw_sizes=[1],
            seed=1,
            economies=[],
        )
        outer = index_samples(conn, samples_table="samples")

        match_population(conn, outer, population_table="population", resources=xlsx_resources)

        docx_path = tmp_path / "manual.docx"
        docx_path.write_text("stub", encoding="utf-8")
        docx_resources = {
            docx_path.name: register_resource(
                docx_path,
                group=ResourceGroup.KTP_PILOT_SAMPLE,
                fragment_type=FragmentType.DOCX_ROW,
            )
        }
        docx_df = pd.DataFrame(
            [
                {
                    RIGHT_NAME_COL: "Ada Lovelace",
                    KTP_FILENAME_COL: docx_path.name,
                    DOCX_FRAGMENT_COL: "table0_row0",
                }
            ]
        )
        match_docx(conn, outer, docx_df, docx_resources, fragment_col=DOCX_FRAGMENT_COL)

        author_details = tmp_path / "author_details.parquet"
        authors_paper = tmp_path / "authors_paper.parquet"
        hit0 = tmp_path / "hit_level0.parquet"
        hit1 = tmp_path / "hit_level1.parquet"

        _write_parquet(
            author_details,
            "CREATE TABLE input(authorid VARCHAR, display_name VARCHAR, display_name_alternatives VARCHAR)",
            "INSERT INTO input VALUES ('A1', 'Ada Lovelace', '[\"A. Lovelace\"]');",
        )
        _write_parquet(
            authors_paper,
            "CREATE TABLE input(authorid VARCHAR, paperid VARCHAR)",
            "INSERT INTO input VALUES ('A1', 'P1');",
        )
        _write_parquet(
            hit0,
            "CREATE TABLE input(paperid VARCHAR, fieldid VARCHAR, hit_1pct INTEGER)",
            "INSERT INTO input VALUES ('P1', 'F1', 1);",
        )
        _write_parquet(
            hit1,
            "CREATE TABLE input(paperid VARCHAR, fieldid VARCHAR, hit_1pct INTEGER)",
            "INSERT INTO input VALUES ('P1', 'F1', 1);",
        )

        parquet_resources = {
            author_details.name: register_resource(
                author_details,
                group=ResourceGroup.SCISCINET_HF,
                fragment_type=FragmentType.AUTHOR_ID,
            )
        }

        samples = conn.execute("SELECT * FROM samples").df()
        samples[NAME_KEY_COL] = samples.apply(
            lambda row: NameKey(
                first_name=str(row[KTP_FIRST_NAME_COL]),
                last_name=str(row[KTP_LAST_NAME_COL]),
            ).to_json_key(),
            axis=1,
        )

        match_parquet(
            conn,
            outer,
            samples,
            parquet_resources,
            author_details_path=str(author_details),
            authors_paper_path=str(authors_paper),
            hit_papers_level0_path=str(hit0),
            hit_papers_level1_path=str(hit1),
        )

        cards = build_cards(
            outer,
            total_draws=1,
            intro_date="2026-02-02",
            excluded_cols={KTP_FILENAME_COL, KTP_SOURCE_KEY_COL, DRAW_LABEL},
        )
        zip_path = write_cards_zip(
            cards,
            tmp_path,
            "cards.zip",
            output_format="txt",
            reference_docx=tmp_path / "ref.docx",
        )
    finally:
        conn.close()

    assert any(outer.data.values())
    assert zip_path.exists()
    with ZipFile(zip_path, "r") as zipf:
        assert zipf.namelist() == ["Ada_Lovelace.txt"]
