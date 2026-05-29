from __future__ import annotations

from pathlib import Path

import duckdb

from src.helpers.name_matching import (
    sciscinet_author_alt_name_key_exprs_sql,
    sciscinet_author_name_norm_sql,
    sciscinet_ktp_name_norm_sql,
)
from src.helpers.schema import (
    PARQUET_AUTHOR_HIT_AGG_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
    PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW,
    PARQUET_AUTHOR_MATCH_TABLE,
)
from src.helpers.ssn_hit_selection import (
    ssn_hit_metadata_select_sql,
    ssn_hit_selected_view_sql,
    ssn_hit_v2_candidate_metrics_table_sql,
    ssn_hit_v2_selection_breakdown_sql,
    ssn_nonzero_hit_view_sql,
)
from src.helpers.vars import (
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
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
    SSNAD_AUTHORID_COL,
    SSNAP_FILENAME_COL,
)


def _connect() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
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
    rows: list[tuple[str, int, int]],
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


def test_ssn_hit_v2_selects_tukey_max_work_and_falls_back_to_v1(
    tmp_path: Path,
) -> None:
    conn = _connect()
    author_details_path = tmp_path / "author_details.parquet"
    nonzero_rows: list[tuple[str, str]] = [
        ("fallback", "A100"),
        ("fallback", "A101"),
        ("unique", "A200"),
        ("unique", "A201"),
        ("unique", "A202"),
        ("tie", "A300"),
        ("tie", "A301"),
    ]
    nonzero_rows.extend((f"background-{idx}", f"A4{idx:02d}") for idx in range(20))
    hit_rows = [
        ("fallback", "A100", 1),
        ("fallback", "A101", 1),
        ("unique", "A200", 1),
        ("unique", "A201", 1000),
        ("unique", "A202", 1001),
        ("tie", "A300", 1002),
        ("tie", "A301", 1003),
    ]
    hit_rows.extend((f"background-{idx}", f"A4{idx:02d}", 1) for idx in range(20))
    details_rows = [
        ("A100", 10, 1),
        ("A101", 11, 1),
        ("A200", 12, 1),
        ("A201", 50, 1),
        ("A202", 40, 1),
        ("A300", 70, 1),
        ("A301", 70, 1),
    ]
    details_rows.extend((f"A4{idx:02d}", 20 + idx, 1) for idx in range(20))
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
            WHERE name_key IN ('fallback', 'unique', 'tie')
            ORDER BY name_key, "{SSNAD_AUTHORID_COL}"
            '''
        ).fetchall()
    finally:
        conn.close()

    assert selected_rows == [
        ("fallback", "A100", KTP_SSN_HIT_RULE_V2, False, False, 10, True),
        ("fallback", "A101", KTP_SSN_HIT_RULE_V2, False, False, 11, True),
        ("tie", "A300", KTP_SSN_HIT_RULE_V2, True, True, 70, False),
        ("tie", "A301", KTP_SSN_HIT_RULE_V2, True, True, 70, False),
        ("unique", "A201", KTP_SSN_HIT_RULE_V2, True, True, 50, False),
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
    nonzero_rows.extend((f"background-{idx}", f"A6{idx:02d}") for idx in range(40))
    hit_rows = [(source_key, "A5101447280", 1), (source_key, "A5101447281", 1000)]
    hit_rows.extend((f"background-{idx}", f"A6{idx:02d}", 1) for idx in range(40))
    details_rows = [("A5101447280", 55, 100), ("A5101447281", 30, 100)]
    details_rows.extend((f"A6{idx:02d}", 20 + idx, 100) for idx in range(40))
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
        42,
        41,
        42,
        1,
        0,
        0,
        1,
        1,
        40,
        41,
        41,
        41,
        1,
        40,
        1,
        0,
        41,
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
                    false AS "{KTP_SSN_HIT_FALLBACK_NO_TUKEY_OUTLIER_COL}"
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
