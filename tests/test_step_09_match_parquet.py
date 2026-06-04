from __future__ import annotations

import json

import duckdb

from src.helpers.schema import (
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
    PARQUET_AUTHOR_PAPERS_TABLE,
)
from src.helpers.vars import (
    KTP_SSN_TOP_OLDEST_PAPERS_COL,
    KTP_SSNP_PAPERID_URL_COL,
    SSNAD_AUTHORID_COL,
    SSNP_PAPERID_COL,
    SSNP_YEAR_COL,
    TOP_K_WORKS,
)
from src.steps.step_09_match_parquet import _top_oldest_papers_ctes_sql


def test_top_oldest_papers_sql_orders_truncates_urls_and_omits_null_year() -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_PAPERS_TABLE} (
                name_key VARCHAR,
                authorid VARCHAR,
                paperid VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} (
                name_key VARCHAR,
                "{SSNAD_AUTHORID_COL}" VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE ssn_sciscinet_papers (
                "{SSNP_PAPERID_COL}" VARCHAR,
                "{SSNP_YEAR_COL}" BIGINT
            )
            """
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_PAPERS_TABLE} VALUES (?, ?, ?)",
            [
                ("ada", "A1", "W7"),
                ("ada", "A1", "W2"),
                ("ada", "A1", "W1"),
                ("ada", "A1", "W3"),
                ("ada", "A1", "W4"),
                ("ada", "A1", "W5"),
                ("ada", "A1", "W6"),
                ("ada", "A2", "W0"),
            ],
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} VALUES (?, ?)",
            [("ada", "A1")],
        )
        conn.executemany(
            "INSERT INTO ssn_sciscinet_papers VALUES (?, ?)",
            [
                ("W7", 2012),
                ("W2", 1999),
                ("W1", 1999),
                ("W3", 2001),
                ("W4", None),
                ("W5", 2010),
                ("W6", 2011),
                ("W0", 1800),
            ],
        )

        ctes = _top_oldest_papers_ctes_sql(
            author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
            selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
            papers_table="ssn_sciscinet_papers",
            author_id_col=SSNAD_AUTHORID_COL,
            paperid_col=SSNP_PAPERID_COL,
            year_col=SSNP_YEAR_COL,
            top_k_works=TOP_K_WORKS,
        )
        row = conn.execute(
            f"""
            WITH {ctes}
            SELECT "{KTP_SSN_TOP_OLDEST_PAPERS_COL}"
            FROM top_oldest_papers
            WHERE name_key = 'ada' AND authorid = 'A1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    payload = json.loads(row[0])
    assert payload == [
        {SSNP_YEAR_COL: 1999, KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W1"},
        {SSNP_YEAR_COL: 1999, KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W2"},
        {SSNP_YEAR_COL: 2001, KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W3"},
        {SSNP_YEAR_COL: 2010, KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W5"},
        {SSNP_YEAR_COL: 2011, KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W6"},
    ]
