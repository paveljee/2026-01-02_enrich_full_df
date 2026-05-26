from __future__ import annotations

import duckdb

from src.helpers.name_matching import docx_match_condition_sql, docx_name_norm_sql


def _connect() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
    return conn


def _matches(first_name: str, last_name: str, docx_name: str | None) -> bool:
    conn = _connect()
    first_norm = docx_name_norm_sql("n.first_name")
    last_norm = docx_name_norm_sql("n.last_name")
    docx_norm = docx_name_norm_sql("d.docx_name", coalesce_empty=True)
    condition = docx_match_condition_sql("n.first_clean", "n.last_clean", "d.docx_clean")
    row = conn.execute(
        f"""
        WITH names(first_name, last_name) AS (VALUES (?, ?)),
        docx_rows(docx_name) AS (VALUES (?)),
        names_clean AS (
            SELECT
                {first_norm} AS first_clean,
                {last_norm} AS last_clean
            FROM names n
        ),
        docx_clean AS (
            SELECT {docx_norm} AS docx_clean
            FROM docx_rows d
        )
        SELECT {condition} AS matched
        FROM names_clean n
        CROSS JOIN docx_clean d
        """,
        [first_name, last_name, docx_name],
    ).fetchone()
    assert row is not None
    return bool(row[0])


def test_docx_matching_preserves_punctuation_stripping_and_containment() -> None:
    assert _matches(
        "Jean-Luc",
        "Picard",
        "Professor Jean Luc Picard, Federation Archaeology Program",
    )


def test_docx_matching_preserves_unaccent_behavior() -> None:
    assert _matches("José", "García", "Jose Garcia")


def test_docx_matching_still_requires_first_and_last_containment() -> None:
    assert not _matches("Ada", "Lovelace", "Ada Byron")


def test_docx_null_table_name_does_not_match_non_empty_name_key() -> None:
    assert not _matches("Ada", "Lovelace", None)
