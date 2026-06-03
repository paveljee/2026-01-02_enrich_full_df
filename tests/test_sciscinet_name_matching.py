from __future__ import annotations

import json
import re
from collections.abc import Sequence
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.helpers.duckdb_extensions import load_duckdb_extension_from_config_path
from src.helpers.name_matching import (
    sciscinet_author_alt_name_key_exprs_sql,
    sciscinet_author_name_norm_sql,
    sciscinet_ktp_name_norm_sql,
)
from src.helpers.openalex import (
    check_openalex_author,
    openalex_author_search_query,
    parse_openalex_top_author_id,
)
from src.helpers.schema import (
    PARQUET_AUTHOR_HIT_AGG_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_PRE_OPENALEX_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
    PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW,
    PARQUET_AUTHOR_MATCH_TABLE,
)
from src.helpers.ssn_hit_selection import (
    ssn_hit_metadata_select_sql,
    ssn_hit_openalex_check_insert_sql,
    ssn_hit_openalex_check_table_sql,
    ssn_hit_openalex_selected_view_sql,
    ssn_hit_selected_view_sql,
    ssn_hit_v2_candidate_metrics_table_sql,
    ssn_hit_v2_selection_breakdown_sql,
    ssn_nonzero_hit_view_sql,
)
from src.helpers.vars import (
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_OPENALEX_MATCH_COL,
    KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL,
    KTP_OPENALEX_RESPONSE_CODE_COL,
    KTP_OPENALEX_REUSED_COL,
    KTP_OPENALEX_TOP_AUTHOR_ID_COL,
    KTP_SOURCE_KEY_COL,
    KTP_SSN_HIT_CITED_BY_COUNT_IS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_RULE_KEY,
    KTP_SSN_HIT_RULE_V2,
    KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_WORKS_COUNT_IS_TUKEY_OUTLIER_COL,
    KTP_SSN_HIT_WORKS_COUNT_RAW_COL,
    KTP_SSN_SUM_HIT_1PCT_COL,
    KTP_SSNAD_MATCH_COL,
    OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION,
    SSNAD_AUTHORID_COL,
    SSNAP_FILENAME_COL,
)

MANUAL_BEST_FIXTURE_PATH = Path(
    "tasks/tasks-20260526-match-patch/context/"
    "duckdb_ui_20260601T1750Z_export_edit_done.xlsx"
)
MANUAL_BEST_RAW_EXPORT_PATH = Path(
    "tasks/tasks-20260526-match-patch/context/duckdb_ui_20260601T1750Z_export.csv"
)
SUBSET1_FIXTURE_DIR = Path(
    "tmp/hcr_cards_subset1_20260602T1624Z_v2_ssn_hit_v2_per_namekey_Tukey"
)
SUBSET2_FIXTURE_DIR = Path(
    "tmp/hcr_cards_subset2_20260602T1754Z_v2_ssn_hit_v2_per_namekey_Tukey"
)


def _connect() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    load_duckdb_extension_from_config_path(conn, "splink_udfs")
    return conn


def _matches(
    *,
    rule_version: int,
    first_name: str,
    last_name: str,
    author_name: str,
) -> bool:
    conn = _connect()
    ktp_norm = sciscinet_ktp_name_norm_sql(
        "n.first_name",
        "n.last_name",
        rule_version=rule_version,
    )
    author_norm = sciscinet_author_name_norm_sql(
        "p.author_name",
        rule_version=rule_version,
    )
    row = conn.execute(
        f"""
        WITH names(first_name, last_name) AS (VALUES (?, ?)),
        authors(author_name) AS (VALUES (?))
        SELECT {author_norm} = {ktp_norm} AS matched
        FROM names n
        CROSS JOIN authors p
        """,
        [first_name, last_name, author_name],
    ).fetchone()
    assert row is not None
    return bool(row[0])


def test_v1_preserves_exact_normalized_name_and_unaccent_behavior() -> None:
    assert _matches(
        rule_version=1,
        first_name="Ada",
        last_name="Lovelace",
        author_name="Ada Lovelace",
    )
    assert _matches(
        rule_version=1,
        first_name="José",
        last_name="García",
        author_name="Jose Garcia",
    )


def test_v1_rejects_leading_or_trailing_spaces() -> None:
    assert not _matches(
        rule_version=1,
        first_name="Ada",
        last_name="Lovelace",
        author_name=" Ada Lovelace ",
    )


def test_v2_normalizes_punctuation_and_whitespace_to_spaces() -> None:
    assert _matches(
        rule_version=2,
        first_name=" Ada",
        last_name="Lovelace ",
        author_name=" Ada Lovelace ",
    )
    assert _matches(
        rule_version=2,
        first_name="Ada",
        last_name="Lovelace",
        author_name="Ada  Lovelace",
    )
    assert _matches(
        rule_version=2,
        first_name="Ada",
        last_name="Lovelace",
        author_name="Ada-Lovelace",
    )
    assert _matches(
        rule_version=2,
        first_name="Claire M",
        last_name="Fraser",
        author_name="Claire M. Fraser",
    )


def test_v2_author_unnest_keys_include_original_and_punctuation_space_forms() -> None:
    conn = _connect()
    key_exprs = sciscinet_author_alt_name_key_exprs_sql("author_name", rule_version=2)
    selects = " UNION ALL ".join(
        f"SELECT {expr} AS match_key FROM authors" for expr in key_exprs
    )
    rows = conn.execute(
        f"""
        WITH authors(author_name) AS (VALUES ('Claire M. Fraser'))
        SELECT DISTINCT match_key
        FROM ({selects})
        ORDER BY match_key
        """
    ).fetchall()

    assert [row[0] for row in rows] == ["claire m fraser", "claire m. fraser"]


def _create_nonzero_hit_tables(
    conn: duckdb.DuckDBPyConnection,
    rows: list[tuple[str, str]],
) -> None:
    conn.execute(
        f"""
        CREATE TABLE {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} (
            name_key VARCHAR,
            "{KTP_FIRST_NAME_COL}" VARCHAR,
            "{KTP_LAST_NAME_COL}" VARCHAR,
            "{SSNAD_AUTHORID_COL}" VARCHAR,
            "{KTP_SSNAD_MATCH_COL}" VARCHAR
        )
        """
    )
    conn.executemany(
        f"""
        INSERT INTO {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW}
        VALUES (?, 'First', 'Last', ?, '{{}}')
        """,
        rows,
    )


def _create_author_match_table(
    conn: duckdb.DuckDBPyConnection,
    rows: list[tuple[str, str]],
) -> None:
    conn.execute(
        f"""
        CREATE TABLE {PARQUET_AUTHOR_MATCH_TABLE} (
            name_key VARCHAR,
            "{KTP_FIRST_NAME_COL}" VARCHAR,
            "{KTP_LAST_NAME_COL}" VARCHAR,
            "{SSNAD_AUTHORID_COL}" VARCHAR,
            "{KTP_SSNAD_MATCH_COL}" VARCHAR
        )
        """
    )
    conn.executemany(
        f"""
        INSERT INTO {PARQUET_AUTHOR_MATCH_TABLE}
        VALUES (?, 'First', 'Last', ?, '{{}}')
        """,
        rows,
    )


def _write_hit_selection_author_details(
    conn: duckdb.DuckDBPyConnection,
    path: Path,
    rows: Sequence[tuple[str, int | None, int | None]],
) -> None:
    conn.execute(
        """
        CREATE TABLE author_details_for_hit_selection (
            authorid VARCHAR,
            works_count BIGINT,
            cited_by_count BIGINT
        )
        """
    )
    conn.executemany(
        "INSERT INTO author_details_for_hit_selection VALUES (?, ?, ?)",
        rows,
    )
    conn.execute(f"COPY author_details_for_hit_selection TO '{path}' (FORMAT PARQUET)")


def _create_hit_agg_table(
    conn: duckdb.DuckDBPyConnection,
    rows: list[tuple[str, str, int]],
) -> None:
    conn.execute(
        f"""
        CREATE TABLE {PARQUET_AUTHOR_HIT_AGG_TABLE} (
            name_key VARCHAR,
            authorid VARCHAR,
            "{KTP_SSN_SUM_HIT_1PCT_COL}" BIGINT
        )
        """
    )
    conn.executemany(
        f"INSERT INTO {PARQUET_AUTHOR_HIT_AGG_TABLE} VALUES (?, ?, ?)",
        rows,
    )


def _create_v2_hit_selected_view(
    conn: duckdb.DuckDBPyConnection,
    author_details_path: Path,
) -> None:
    conn.execute(
        ssn_hit_v2_candidate_metrics_table_sql(
            author_details_path=str(author_details_path),
            author_id_col=SSNAD_AUTHORID_COL,
        )
    )
    conn.execute(
        ssn_hit_selected_view_sql(
            author_id_col=SSNAD_AUTHORID_COL,
            hit_rule_version=2,
        )
    )


def test_ssn_nonzero_hit_view_keeps_nonzero_and_missing_hit_rows() -> None:
    conn = _connect()
    try:
        _create_author_match_table(
            conn,
            [
                ("drop-zero", "A0"),
                ("keep-nonzero", "A1"),
                ("keep-missing", "A2"),
            ],
        )
        _create_hit_agg_table(
            conn,
            [
                ("drop-zero", "A0", 0),
                ("keep-nonzero", "A1", 3),
            ],
        )

        conn.execute(ssn_nonzero_hit_view_sql(author_id_col=SSNAD_AUTHORID_COL))

        rows = conn.execute(
            f'''
            SELECT name_key, "{SSNAD_AUTHORID_COL}"
            FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW}
            ORDER BY name_key
            '''
        ).fetchall()
    finally:
        conn.close()

    assert rows == [("keep-missing", "A2"), ("keep-nonzero", "A1")]


def test_ssn_hit_v1_selected_view_is_exact_nonzero_hit_alias() -> None:
    conn = _connect()
    try:
        _create_nonzero_hit_tables(conn, [("name-a", "A1"), ("name-b", "A2")])

        conn.execute(
            ssn_hit_selected_view_sql(
                author_id_col=SSNAD_AUTHORID_COL,
                hit_rule_version=1,
            )
        )

        nonzero_columns = [
            row[1]
            for row in conn.execute(
                f"PRAGMA table_info('{PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW}')"
            ).fetchall()
        ]
        selected_columns = [
            row[1]
            for row in conn.execute(
                f"PRAGMA table_info('{PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}')"
            ).fetchall()
        ]
        nonzero_rows = conn.execute(
            f'SELECT * FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} ORDER BY name_key'
        ).fetchall()
        selected_rows = conn.execute(
            f'SELECT * FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} ORDER BY name_key'
        ).fetchall()
    finally:
        conn.close()

    assert selected_columns == nonzero_columns
    assert selected_rows == nonzero_rows


def test_ssn_hit_v2_selects_singletons_unique_max_and_review_fallbacks(
    tmp_path: Path,
) -> None:
    conn = _connect()
    author_details_path = tmp_path / "author_details.parquet"
    nonzero_rows: list[tuple[str, str]] = [
        ("singleton-missing", "A010"),
        ("fallback", "A100"),
        ("fallback", "A101"),
        ("unique", "A200"),
        ("unique", "A201"),
        ("unique", "A202"),
        ("tie", "A300"),
        ("tie", "A301"),
        ("multi-missing", "A400"),
        ("multi-missing", "A401"),
    ]
    hit_rows = [
        ("singleton-missing", "A010", 1),
        ("fallback", "A100", 1),
        ("fallback", "A101", 1),
        ("unique", "A200", 1),
        ("unique", "A201", 1),
        ("unique", "A202", 1),
        ("tie", "A300", 1),
        ("tie", "A301", 1),
        ("multi-missing", "A400", 1),
        ("multi-missing", "A401", 1),
    ]
    details_rows = [
        ("A010", None, 1),
        ("A100", 10, 1),
        ("A101", 11, 1),
        ("A200", 12, 1),
        ("A201", 50, 1),
        ("A202", 40, 1),
        ("A300", 70, 1),
        ("A301", 70, 1),
        ("A400", None, 1),
        ("A401", 15, 1),
    ]
    try:
        _create_nonzero_hit_tables(conn, nonzero_rows)
        _create_hit_agg_table(conn, hit_rows)
        _write_hit_selection_author_details(conn, author_details_path, details_rows)

        _create_v2_hit_selected_view(conn, author_details_path)

        selected_rows = conn.execute(
            f'''
            SELECT
                name_key,
                "{SSNAD_AUTHORID_COL}",
                "{KTP_SSN_HIT_RULE_KEY}",
                "{KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL}",
                "{KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL}",
                "{KTP_SSN_HIT_WORKS_COUNT_RAW_COL}",
                "{KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL}"
            FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}
            WHERE name_key IN (
                'fallback',
                'multi-missing',
                'singleton-missing',
                'tie',
                'unique'
            )
            ORDER BY name_key, "{SSNAD_AUTHORID_COL}"
            '''
        ).fetchall()
    finally:
        conn.close()

    assert selected_rows == [
        ("fallback", "A101", KTP_SSN_HIT_RULE_V2, False, False, 11, True),
        ("multi-missing", "A400", KTP_SSN_HIT_RULE_V2, False, False, None, True),
        ("multi-missing", "A401", KTP_SSN_HIT_RULE_V2, False, False, 15, True),
        ("singleton-missing", "A010", KTP_SSN_HIT_RULE_V2, False, False, None, True),
        ("tie", "A300", KTP_SSN_HIT_RULE_V2, False, False, 70, True),
        ("tie", "A301", KTP_SSN_HIT_RULE_V2, False, False, 70, True),
        ("unique", "A201", KTP_SSN_HIT_RULE_V2, False, False, 50, True),
    ]


def test_ssn_hit_v2_does_not_take_max_works_outside_tukey_outliers(
    tmp_path: Path,
) -> None:
    conn = _connect()
    author_details_path = tmp_path / "author_details.parquet"
    source_key = '{"ktp.first_name": "Dabing", "ktp.last_name": "Zhang"}'
    nonzero_rows: list[tuple[str, str]] = [
        (source_key, "A5101447280"),
        (source_key, "A5101447281"),
    ]
    nonzero_rows.extend((source_key, f"A51014472{idx:02d}") for idx in range(82, 91))
    hit_rows = [(source_key, "A5101447280", 1), (source_key, "A5101447281", 1000)]
    hit_rows.extend((source_key, f"A51014472{idx:02d}", 1) for idx in range(82, 91))
    details_rows = [("A5101447280", 55, 100), ("A5101447281", 30, 100)]
    details_rows.extend((f"A51014472{idx:02d}", 50 + idx - 82, 100) for idx in range(82, 91))
    try:
        _create_nonzero_hit_tables(conn, nonzero_rows)
        _create_hit_agg_table(conn, hit_rows)
        _write_hit_selection_author_details(conn, author_details_path, details_rows)

        _create_v2_hit_selected_view(conn, author_details_path)

        selected_rows = conn.execute(
            f'''
            SELECT
                "{SSNAD_AUTHORID_COL}",
                "{KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL}",
                "{KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL}",
                "{KTP_SSN_HIT_WORKS_COUNT_RAW_COL}",
                "{KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL}"
            FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}
            WHERE name_key = ?
            ORDER BY "{SSNAD_AUTHORID_COL}"
            ''',
            [source_key],
        ).fetchall()
        breakdown_row = conn.execute(
            ssn_hit_v2_selection_breakdown_sql(author_id_col=SSNAD_AUTHORID_COL)
        ).fetchone()
    finally:
        conn.close()

    assert selected_rows == [("A5101447281", True, True, 30, False)]
    assert breakdown_row == (
        11,
        1,
        11,
        1,
        1,
        0,
        1,
        1,
        1,
        0,
        0,
        0,
        0,
        1,
        1,
        1,
        0,
        1,
        1,
        1,
        0,
        1,
        0,
        0,
        10,
        1,
        0,
        1,
    )


def test_ssn_hit_v2_metadata_select_is_parse_safe_before_next_column() -> None:
    conn = _connect()
    try:
        result = conn.execute(
            f'''
            SELECT
                m."{KTP_SSNAD_MATCH_COL}" AS "{KTP_SSNAD_MATCH_COL}"
                {ssn_hit_metadata_select_sql(hit_rule_version=2, table_alias="m")},
                'sciscinet_authors_paperid.parquet' AS "{SSNAP_FILENAME_COL}"
            FROM (
                SELECT
                    '{{}}' AS "{KTP_SSNAD_MATCH_COL}",
                    '{KTP_SSN_HIT_RULE_V2}' AS "{KTP_SSN_HIT_RULE_KEY}",
                    true AS "{KTP_SSN_HIT_SUM_HIT_1PCT_IS_TUKEY_OUTLIER_COL}",
                    false AS "{KTP_SSN_HIT_WORKS_COUNT_IS_TUKEY_OUTLIER_COL}",
                    false AS "{KTP_SSN_HIT_CITED_BY_COUNT_IS_TUKEY_OUTLIER_COL}",
                    true AS "{KTP_SSN_HIT_ROW_HAS_TUKEY_OUTLIER_COL}",
                    30 AS "{KTP_SSN_HIT_WORKS_COUNT_RAW_COL}",
                    false AS "{KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL}",
                    'A1' AS "{KTP_OPENALEX_TOP_AUTHOR_ID_COL}",
                    true AS "{KTP_OPENALEX_MATCH_COL}",
                    false AS "{KTP_OPENALEX_REUSED_COL}",
                    200 AS "{KTP_OPENALEX_RESPONSE_CODE_COL}",
                    123456 AS "{KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL}"
            ) m
            '''
        )
        row = result.fetchone()
        assert row is not None
        columns = [desc[0] for desc in result.description]
        assert columns[-1] == SSNAP_FILENAME_COL
        assert row[-1] == "sciscinet_authors_paperid.parquet"
    finally:
        conn.close()


class _FakeOpenAlexResponse:
    def __init__(self, *, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


def test_openalex_author_check_reuses_jsonl_cache(tmp_path: Path) -> None:
    source_key = '{"ktp.first_name": "Ada", "ktp.last_name": "Lovelace"}'
    query = openalex_author_search_query(
        first_name="Ada",
        last_name="Lovelace",
        api_key="REDACTED",
    )
    log_path = tmp_path / "openalex.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "schema_version": OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION,
                "method": "GET",
                "scheme": "https",
                "host": "api.openalex.org",
                "path": "/authors",
                "query": query,
                "request_headers": {},
                "request_body": None,
                "response_code": 200,
                "response_headers": {},
                "response_body": '{"results":[{"id":"https://openalex.org/A123"}]}',
                "received_at_unix_usec": 111,
                "duration_usec": 222,
                KTP_SOURCE_KEY_COL: source_key,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_get(_url: str, *, timeout: float) -> _FakeOpenAlexResponse:
        raise AssertionError("cached OpenAlex response should have been reused")

    result = check_openalex_author(
        source_key=source_key,
        first_name="Ada",
        last_name="Lovelace",
        selected_author_id="A123",
        log_path=log_path,
        api_key="test-key",
        request_get=fail_get,
    )

    assert result.reused
    assert result.matched
    assert result.query == query
    assert result.top_author_id == "A123"
    assert result.received_at_unix_usec == 111


def test_openalex_author_check_appends_response_and_parses_mismatch(tmp_path: Path) -> None:
    source_key = '{"ktp.first_name": "Ada", "ktp.last_name": "Lovelace"}'
    log_path = tmp_path / "openalex.jsonl"
    seen_urls: list[str] = []

    def fake_get(url: str, *, timeout: float) -> _FakeOpenAlexResponse:
        seen_urls.append(url)
        assert timeout > 0
        return _FakeOpenAlexResponse(
            status_code=200,
            text='{"results":[{"id":"https://openalex.org/A999"}]}',
        )

    result = check_openalex_author(
        source_key=source_key,
        first_name="Ada",
        last_name="Lovelace",
        selected_author_id="A123",
        log_path=log_path,
        api_key="test-key",
        request_get=fake_get,
    )
    record = json.loads(log_path.read_text(encoding="utf-8"))

    assert len(seen_urls) == 1
    assert "search=Ada%20Lovelace" in seen_urls[0]
    assert "sort=relevance_score%3Adesc" in seen_urls[0]
    assert "api_key=test-key" in seen_urls[0]
    assert result.top_author_id == "A999"
    assert not result.matched
    assert not result.reused
    assert result.query == record["query"]
    assert record["schema_version"] == OPENALEX_AUTHOR_SEARCH_LOG_SCHEMA_VERSION
    assert record[KTP_SOURCE_KEY_COL] == source_key
    assert record["query"].endswith("api_key=REDACTED")
    assert "test-key" not in record["query"]
    assert record["openalex_top_author_id"] == "A999"
    assert record["openalex_match"] is False


def test_parse_openalex_top_author_id_handles_empty_or_malformed_results() -> None:
    assert parse_openalex_top_author_id('{"results":[]}') is None
    assert parse_openalex_top_author_id("not-json") is None


def test_ssn_hit_v2_openalex_mismatch_returns_full_nonzero_pool(tmp_path: Path) -> None:
    conn = _connect()
    author_details_path = tmp_path / "author_details.parquet"
    matched_key = '{"ktp.first_name": "Ada", "ktp.last_name": "Lovelace"}'
    failed_key = '{"ktp.first_name": "Grace", "ktp.last_name": "Hopper"}'
    try:
        _create_nonzero_hit_tables(
            conn,
            [
                (matched_key, "A101"),
                (matched_key, "A102"),
                (failed_key, "A201"),
                (failed_key, "A202"),
            ],
        )
        _create_hit_agg_table(
            conn,
            [
                (matched_key, "A101", 1),
                (matched_key, "A102", 1),
                (failed_key, "A201", 1),
                (failed_key, "A202", 1),
            ],
        )
        _write_hit_selection_author_details(
            conn,
            author_details_path,
            [
                ("A101", 10, 1),
                ("A102", 20, 1),
                ("A201", 10, 1),
                ("A202", 20, 1),
            ],
        )
        _create_v2_hit_selected_view(conn, author_details_path)
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE {PARQUET_AUTHOR_MATCH_HIT_SELECTED_PRE_OPENALEX_TABLE} AS
            SELECT *
            FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}
            """
        )
        conn.execute(ssn_hit_openalex_check_table_sql(author_id_col=SSNAD_AUTHORID_COL))
        conn.executemany(
            ssn_hit_openalex_check_insert_sql(author_id_col=SSNAD_AUTHORID_COL),
            [
                (matched_key, "A102", "A102", True, True, 200, 111),
                (failed_key, "A202", "A999", False, False, 200, 222),
            ],
        )
        conn.execute(ssn_hit_openalex_selected_view_sql(author_id_col=SSNAD_AUTHORID_COL))

        rows = conn.execute(
            f'''
            SELECT
                name_key,
                "{SSNAD_AUTHORID_COL}",
                "{KTP_OPENALEX_TOP_AUTHOR_ID_COL}",
                "{KTP_OPENALEX_MATCH_COL}"
            FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}
            ORDER BY name_key, "{SSNAD_AUTHORID_COL}"
            '''
        ).fetchall()
    finally:
        conn.close()

    assert rows == [
        (matched_key, "A102", "A102", True),
        (failed_key, "A201", "A999", False),
        (failed_key, "A202", "A999", False),
    ]


def _norm_name_part(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def _source_key_name_pair(source_key: str) -> tuple[str, str]:
    payload = json.loads(source_key)
    return (
        _norm_name_part(payload[KTP_FIRST_NAME_COL]),
        _norm_name_part(payload[KTP_LAST_NAME_COL]),
    )


def _card_title_name_pair(text: str) -> tuple[str, str] | None:
    match = re.search(r"^### Draw .*?: (?P<last>.*), (?P<first>.*)$", text, re.MULTILINE)
    if match is None:
        return None
    return (_norm_name_part(match.group("first")), _norm_name_part(match.group("last")))


def _card_author_ids(text: str) -> set[str]:
    return set(
        re.findall(
            r"\*\*ktp\.fragment\*\*: (A\d+)\n\n\*\*ktp\.fragment_type\*\*: author_id",
            text,
        )
    )


def _card_author_ids_by_name(root: Path) -> dict[tuple[str, str], set[str]]:
    rows: dict[tuple[str, str], set[str]] = {}
    for path in root.glob("*.txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        name_pair = _card_title_name_pair(text)
        if name_pair is None:
            continue
        rows.setdefault(name_pair, set()).update(_card_author_ids(text))
    return rows


def _json_list_cell(value: object) -> list[str]:
    if pd.isna(value):
        return []
    payload = json.loads(str(value))
    assert isinstance(payload, list)
    return [str(item) for item in payload]


def _source_key_payload(source_key: str) -> dict[str, str]:
    payload = json.loads(source_key)
    return {
        KTP_FIRST_NAME_COL: str(payload[KTP_FIRST_NAME_COL]),
        KTP_LAST_NAME_COL: str(payload[KTP_LAST_NAME_COL]),
    }


def _reviewed_export_max_works_pick(row: pd.Series[object]) -> tuple[str | None, str]:
    authorids = _json_list_cell(row["authorids_json"])
    outlier_pool: list[str] = []
    seen: set[str] = set()
    for column in (
        "ssn_sum_hit_1pct_tukey_fragments_json",
        "works_count_tukey_fragments_json",
        "cited_by_count_tukey_fragments_json",
    ):
        for author_id in _json_list_cell(row[column]):
            if author_id not in seen:
                seen.add(author_id)
                outlier_pool.append(author_id)

    pool = outlier_pool or authorids
    if not pool:
        return None, "empty"

    author_order = {author_id: idx for idx, author_id in enumerate(authorids)}
    return min(pool, key=lambda author_id: author_order.get(author_id, 10**9)), (
        "tukey" if outlier_pool else "fallback_all"
    )


def _manual_note_text(row: pd.Series[object]) -> str:
    value = row["manual_best_note"]
    return "" if pd.isna(value) else str(value)


def _old_author_id_from_manual_note(note: str) -> str | None:
    match = re.search(r"\b(?P<old_author_id>A\d+) has no ", note)
    if match is None:
        return None
    return match.group("old_author_id")


def _manual_note_category(note: str) -> str:
    if note == "":
        return "no_note"
    if note in {
        "max-works selection is correct, but need to\n"
        "allow fallback to total candidate list if no outliers.",
        "Again, correct but no fallback.",
    }:
        return "correct_no_outlier_fallback"
    if note == "Matched under SSN v2, and\nthere ktp.fragment matches manual_best.":
        return "matched_under_current_ssn_v2"
    if _old_author_id_from_manual_note(note) is not None:
        return "false_confident_old_ssn_pick"
    if note == (
        "Not found under SSN v2 subset 1, probably under subset 2 due to non-exact matches.\n"
        "Perhaps excluded under non-zero hit rule, as A5111904537, which is max works count, "
        "has count of 70 only."
    ):
        return "matched_current_subset1_despite_old_note"
    if note == (
        "Not found under SSN v2 subset 1, probably under subset 2 due to non-exact matches.\n"
        "Less likely to fall under zero top 1pct hits as A5035633946, which is max works "
        "count, has works count of 1035."
    ):
        return "xlsx_partition2_with_correct_ssn"
    raise AssertionError(f"Uncategorized manual_best_note: {note!r}")


def _workbook_note_category(note: str) -> str:
    if '"There are no results for this search"' in note:
        return "no_current_openalex_result"
    if note.startswith("overall feels like the following rule is sufficiently robust:"):
        return "summary_note"
    return _manual_note_category(note)


def test_manual_best_reviewed_fixture_outputs_select_expected_author_ids() -> None:
    assert MANUAL_BEST_FIXTURE_PATH.exists()
    assert MANUAL_BEST_RAW_EXPORT_PATH.exists()
    assert SUBSET1_FIXTURE_DIR.exists()
    assert SUBSET2_FIXTURE_DIR.exists()
    manual_df = pd.read_excel(MANUAL_BEST_FIXTURE_PATH, engine="openpyxl")
    raw_df = pd.read_csv(MANUAL_BEST_RAW_EXPORT_PATH)
    manual_rows = manual_df[manual_df["manual_best"].notna()]
    raw_by_source_key = raw_df.set_index(KTP_SOURCE_KEY_COL)
    subset1_author_ids = _card_author_ids_by_name(SUBSET1_FIXTURE_DIR)
    subset2_author_ids = _card_author_ids_by_name(SUBSET2_FIXTURE_DIR)
    assert len(raw_df) == 100
    assert len(manual_rows) == 34
    manual_best_source_keys = {
        str(row[KTP_SOURCE_KEY_COL])
        for _, row in manual_rows.iterrows()
        if str(row["manual_best"]).strip()
    }
    assert len(manual_best_source_keys) == len(manual_rows)
    nonempty_note_categories = [
        _workbook_note_category(str(note))
        for note in manual_df["manual_best_note"].dropna()
    ]
    assert {
        category: nonempty_note_categories.count(category)
        for category in set(nonempty_note_categories)
    } == {
        "correct_no_outlier_fallback": 14,
        "matched_under_current_ssn_v2": 6,
        "false_confident_old_ssn_pick": 4,
        "matched_current_subset1_despite_old_note": 1,
        "xlsx_partition2_with_correct_ssn": 1,
        "no_current_openalex_result": 2,
        "summary_note": 1,
    }

    computed_picks: dict[str, str | None] = {}
    computed_modes: dict[str, str] = {}
    empty_export_source_keys: set[str] = set()
    false_confident_old_author_ids: dict[str, str] = {}
    manual_note_categories: dict[str, str] = {}
    for _, row in manual_rows.iterrows():
        source_key = str(row[KTP_SOURCE_KEY_COL])
        manual_best = str(row["manual_best"]).strip()
        note = _manual_note_text(row)
        category = _manual_note_category(note)
        manual_note_categories[source_key] = category
        assert source_key in raw_by_source_key.index
        raw_row = raw_by_source_key.loc[source_key]
        for column in (
            "authorids_json",
            "ssn_sum_hit_1pct_tukey_fragments_json",
            "works_count_tukey_fragments_json",
            "cited_by_count_tukey_fragments_json",
        ):
            assert _json_list_cell(row[column]) == _json_list_cell(raw_row[column])
        computed_pick, computed_mode = _reviewed_export_max_works_pick(row)
        computed_picks[source_key] = computed_pick
        computed_modes[source_key] = computed_mode

        if not _json_list_cell(row["authorids_json"]):
            empty_export_source_keys.add(source_key)
        old_author_id = _old_author_id_from_manual_note(note)
        if old_author_id is not None:
            assert old_author_id != manual_best
            assert old_author_id in _json_list_cell(row["authorids_json"])
            false_confident_old_author_ids[source_key] = old_author_id

        if computed_pick is None:
            assert category in {
                "matched_under_current_ssn_v2",
                "matched_current_subset1_despite_old_note",
                "xlsx_partition2_with_correct_ssn",
            }
            continue
        if category != "false_confident_old_ssn_pick":
            assert computed_pick == manual_best, source_key
        else:
            assert computed_pick in {manual_best, old_author_id}, source_key

    assert {
        category: list(manual_note_categories.values()).count(category)
        for category in set(manual_note_categories.values())
    } == {
        "correct_no_outlier_fallback": 14,
        "matched_under_current_ssn_v2": 6,
        "no_note": 8,
        "false_confident_old_ssn_pick": 4,
        "matched_current_subset1_despite_old_note": 1,
        "xlsx_partition2_with_correct_ssn": 1,
    }
    assert set(manual_note_categories) == manual_best_source_keys
    assert set(computed_picks) == manual_best_source_keys

    assert {
        source_key for source_key, computed_pick in computed_picks.items() if computed_pick is None
    } == empty_export_source_keys

    no_current_openalex_result_keys = {
        _source_key_name_pair(str(row[KTP_SOURCE_KEY_COL]))
        for _, row in manual_df[manual_df["manual_best"].isna()].iterrows()
        if not pd.isna(row[KTP_SOURCE_KEY_COL])
        and '"There are no results for this search"' in _manual_note_text(row)
    }
    for name_pair in no_current_openalex_result_keys:
        assert name_pair not in subset1_author_ids
        assert subset2_author_ids.get(name_pair) == set()

    output_checked_source_keys: set[str] = set()
    for _, row in manual_rows.iterrows():
        source_key = str(row[KTP_SOURCE_KEY_COL])
        output_checked_source_keys.add(source_key)
        name_pair = _source_key_name_pair(source_key)
        manual_best = str(row["manual_best"]).strip()
        old_author_id = false_confident_old_author_ids.get(source_key)
        category = manual_note_categories[source_key]
        if category == "xlsx_partition2_with_correct_ssn":
            assert manual_best in subset2_author_ids.get(name_pair, set()), source_key
            assert name_pair not in subset1_author_ids, source_key
            continue
        if (
            category == "false_confident_old_ssn_pick"
            and computed_picks[source_key] == old_author_id
        ):
            assert old_author_id is not None
            assert old_author_id in subset1_author_ids.get(name_pair, set()), source_key
            assert manual_best not in subset1_author_ids.get(name_pair, set()), source_key
            assert name_pair not in subset2_author_ids, source_key
            continue
        if name_pair not in subset1_author_ids and manual_best in subset2_author_ids.get(
            name_pair, set()
        ):
            assert computed_picks[source_key] == manual_best, source_key
            assert category == "correct_no_outlier_fallback", source_key
            continue
        assert manual_best in subset1_author_ids.get(name_pair, set()), source_key
        assert name_pair not in subset2_author_ids, source_key
    assert output_checked_source_keys == manual_best_source_keys


@pytest.mark.slow
@pytest.mark.real_api
def test_real_api_openalex_identifies_known_false_confident_ssn_picks() -> None:
    manual_df = pd.read_excel(MANUAL_BEST_FIXTURE_PATH, engine="openpyxl")
    cases: list[tuple[str, str, str, list[str]]] = []
    for _, row in manual_df[manual_df["manual_best"].notna()].iterrows():
        note = _manual_note_text(row)
        old_selected_author_id = _old_author_id_from_manual_note(note)
        if old_selected_author_id is None:
            continue
        source_key = str(row[KTP_SOURCE_KEY_COL])
        manual_best = str(row["manual_best"]).strip()
        assert old_selected_author_id != manual_best
        authorids = _json_list_cell(row["authorids_json"])
        assert old_selected_author_id in authorids
        assert manual_best in authorids
        cases.append((source_key, old_selected_author_id, manual_best, authorids))

    assert cases

    stale_manual_best_messages: list[str] = []
    for source_key, old_selected_author_id, manual_best, authorids in cases:
        payload = _source_key_payload(source_key)
        try:
            result = check_openalex_author(
                source_key=source_key,
                first_name=payload[KTP_FIRST_NAME_COL],
                last_name=payload[KTP_LAST_NAME_COL],
                selected_author_id=old_selected_author_id,
            )
        except ValueError as exc:
            pytest.skip(str(exc))
        assert result.response_code == 200
        assert result.top_author_id is not None
        assert result.top_author_id != old_selected_author_id
        assert result.matched is False
        if result.top_author_id != manual_best:
            assert _source_key_name_pair(source_key) == ("yulin", "chen"), source_key
            assert result.top_author_id == "A5100398894"
            assert result.top_author_id in authorids
            stale_manual_best_messages.append(
                f"{source_key}: workbook manual_best {manual_best} is stale; "
                f"user re-reviewed and confirmed current OpenAlex top "
                f"{result.top_author_id} is correct."
            )

    if stale_manual_best_messages:
        pytest.xfail(" ".join(stale_manual_best_messages))
