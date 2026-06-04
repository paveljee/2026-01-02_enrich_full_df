from __future__ import annotations

import json

import duckdb

from src.helpers.openalex import OpenAlexWorkTitleResult
from src.helpers.schema import (
    PARQUET_ALL_HITS_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
    PARQUET_AUTHOR_PAPERS_TABLE,
)
from src.helpers.vars import (
    KTP_SSN_TOP_OLDEST_PAPERS_COL,
    KTP_SSN_TOP_PAPERS_HIT_1PCT_COL,
    KTP_SSNP_PAPERID_URL_COL,
    OPENALEX_TITLE_COL,
    SSNAD_AUTHORID_COL,
    SSNP_DATE_COL,
    SSNP_PAPERID_COL,
    TOP_K_WORKS,
)
from src.steps.step_09_match_parquet import (
    _openalex_work_title_log_message,
    _top_oldest_papers_ctes_sql,
    _top_papers_hit_ctes_sql,
)


def test_openalex_work_title_log_message_includes_each_lookup_details() -> None:
    result = OpenAlexWorkTitleResult(
        paperid="W123",
        query="select=title&per_page=1&api_key=REDACTED",
        response_code=200,
        title="A Fine Paper",
        reused=False,
        received_at_unix_usec=123456,
        duration_usec=789,
    )

    assert _openalex_work_title_log_message(result) == (
        "OpenAlex work-title check fetched: paperid=W123, status=200, "
        "title=title, received_at_unix_usec=123456."
    )


def test_top_oldest_papers_sql_orders_by_date_truncates_and_omits_null_date() -> None:
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
                "{SSNP_DATE_COL}" VARCHAR
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE openalex_work_titles (
                paperid VARCHAR,
                title VARCHAR
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
                ("W7", "2012-01-01"),
                ("W2", "1999-05-20"),
                ("W1", "1999-05-20"),
                ("W3", "1999-05-19"),
                ("W4", None),
                ("W5", "2010-01-01"),
                ("W6", "2011-01-01"),
                ("W0", "1800-01-01"),
            ],
        )
        conn.executemany(
            "INSERT INTO openalex_work_titles VALUES (?, ?)",
            [
                ("W1", "Old W1"),
                ("W2", "Old W2"),
                ("W3", "Old W3"),
                ("W5", "Old W5"),
                ("W6", "Old W6"),
                ("W7", "Old W7"),
            ],
        )

        ctes = _top_oldest_papers_ctes_sql(
            author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
            selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
            papers_table="ssn_sciscinet_papers",
            title_table="openalex_work_titles",
            author_id_col=SSNAD_AUTHORID_COL,
            paperid_col=SSNP_PAPERID_COL,
            date_col=SSNP_DATE_COL,
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
        {
            SSNP_DATE_COL: "1999-05-19",
            OPENALEX_TITLE_COL: "Old W3",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W3",
        },
        {
            SSNP_DATE_COL: "1999-05-20",
            OPENALEX_TITLE_COL: "Old W1",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W1",
        },
        {
            SSNP_DATE_COL: "1999-05-20",
            OPENALEX_TITLE_COL: "Old W2",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W2",
        },
        {
            SSNP_DATE_COL: "2010-01-01",
            OPENALEX_TITLE_COL: "Old W5",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W5",
        },
        {
            SSNP_DATE_COL: "2011-01-01",
            OPENALEX_TITLE_COL: "Old W6",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W6",
        },
    ]


def test_top_hit_papers_sql_preserves_hit_order_and_includes_titles() -> None:
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
            CREATE TABLE {PARQUET_ALL_HITS_TABLE} (
                paperid VARCHAR,
                hit_1pct BIGINT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE openalex_work_titles (
                paperid VARCHAR,
                title VARCHAR
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
            f"INSERT INTO {PARQUET_ALL_HITS_TABLE} VALUES (?, ?)",
            [
                ("W7", 1),
                ("W2", 5),
                ("W1", 5),
                ("W3", 3),
                ("W5", 2),
                ("W6", 1),
                ("W0", 99),
            ],
        )
        conn.executemany(
            "INSERT INTO openalex_work_titles VALUES (?, ?)",
            [
                ("W1", "Hit W1"),
                ("W2", "Hit W2"),
                ("W3", "Hit W3"),
                ("W5", "Hit W5"),
                ("W6", "Hit W6"),
                ("W7", "Hit W7"),
            ],
        )

        ctes = _top_papers_hit_ctes_sql(
            author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
            all_hits_table=PARQUET_ALL_HITS_TABLE,
            selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
            title_table="openalex_work_titles",
            author_id_col=SSNAD_AUTHORID_COL,
            top_k_works=TOP_K_WORKS,
        )
        row = conn.execute(
            f"""
            WITH {ctes}
            SELECT "{KTP_SSN_TOP_PAPERS_HIT_1PCT_COL}"
            FROM top_papers
            WHERE name_key = 'ada' AND authorid = 'A1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    payload = json.loads(row[0])
    assert payload == [
        {
            OPENALEX_TITLE_COL: "Hit W1",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W1",
        },
        {
            OPENALEX_TITLE_COL: "Hit W2",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W2",
        },
        {
            OPENALEX_TITLE_COL: "Hit W3",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W3",
        },
        {
            OPENALEX_TITLE_COL: "Hit W5",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W5",
        },
        {
            OPENALEX_TITLE_COL: "Hit W6",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W6",
        },
    ]
