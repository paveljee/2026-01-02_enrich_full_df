from __future__ import annotations

import duckdb

from src.helpers.name_matching import (
    sciscinet_author_name_norm_sql,
    sciscinet_ktp_name_norm_sql,
)


def _connect() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
    return conn


def _matches(
    *,
    strip_tokens: bool,
    first_name: str,
    last_name: str,
    author_name: str,
) -> bool:
    conn = _connect()
    ktp_norm = sciscinet_ktp_name_norm_sql(
        "n.first_name",
        "n.last_name",
        strip_tokens=strip_tokens,
    )
    author_norm = sciscinet_author_name_norm_sql(
        "p.author_name",
        strip_tokens=strip_tokens,
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
        strip_tokens=False,
        first_name="Ada",
        last_name="Lovelace",
        author_name="Ada Lovelace",
    )
    assert _matches(
        strip_tokens=False,
        first_name="José",
        last_name="García",
        author_name="Jose Garcia",
    )


def test_v1_rejects_leading_or_trailing_spaces() -> None:
    assert not _matches(
        strip_tokens=False,
        first_name="Ada",
        last_name="Lovelace",
        author_name=" Ada Lovelace ",
    )


def test_v2_strips_only_outer_whitespace() -> None:
    assert _matches(
        strip_tokens=True,
        first_name=" Ada",
        last_name="Lovelace ",
        author_name=" Ada Lovelace ",
    )
    assert not _matches(
        strip_tokens=True,
        first_name="Ada",
        last_name="Lovelace",
        author_name="Ada  Lovelace",
    )
    assert not _matches(
        strip_tokens=True,
        first_name="Ada",
        last_name="Lovelace",
        author_name="Ada-Lovelace",
    )
