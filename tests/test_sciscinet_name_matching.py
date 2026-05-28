from __future__ import annotations

import duckdb

from src.helpers.name_matching import (
    sciscinet_author_alt_name_key_exprs_sql,
    sciscinet_author_name_norm_sql,
    sciscinet_ktp_name_norm_sql,
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
