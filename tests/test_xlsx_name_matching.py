from __future__ import annotations

import duckdb
import pytest

from src.helpers.name_matching import xlsx_match_sql
from src.helpers.vars import KTP_XLSX_MATCH_RULE_KEY, KTP_XLSX_MATCH_RULE_V2


def _connect() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
    return conn


def _matches(
    *,
    use_v2: bool,
    source_first: str,
    source_last: str,
    target_first: str,
    target_last: str,
) -> bool:
    conn = _connect()
    match_sql = xlsx_match_sql(
        use_v2=use_v2,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
    )
    row = conn.execute(
        f"""
        WITH source_input(first_name, last_name) AS (VALUES (?, ?)),
        target_input(first_name, last_name) AS (VALUES (?, ?)),
        name_draws AS (
            SELECT
                nk.first_name,
                nk.last_name,
                {match_sql.name_draws_fields}
            FROM source_input nk
        ),
        pop_names AS (
            SELECT
                n.first_name AS pop_first,
                n.last_name AS pop_last,
                {match_sql.pop_names_fields}
                1 AS sentinel
            FROM target_input n
        ){match_sql.extra_ctes}
        SELECT COALESCE(bool_or({match_sql.condition}), FALSE) AS matched
        FROM {match_sql.name_draws_relation} nd
        CROSS JOIN {match_sql.pop_names_relation} p
        """,
        [source_first, source_last, target_first, target_last],
    ).fetchone()
    assert row is not None
    return bool(row[0])


def test_v2_join_condition_is_key_equality_not_pairwise_recursive_sql() -> None:
    match_sql = xlsx_match_sql(
        use_v2=True,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
    )

    assert match_sql.condition == (
        "nd.nd_first_match_key = p.pop_first_match_key "
        "AND nd.nd_last_match_key = p.pop_last_match_key"
    )
    assert match_sql.name_draws_relation == "name_draw_keys"
    assert match_sql.pop_names_relation == "pop_name_keys"
    assert match_sql.base_select_keyword == "SELECT DISTINCT"


def test_v1_preserves_original_first_token_contains_and_unaccent_behavior() -> None:
    assert _matches(
        use_v2=False,
        source_first="John R",
        source_last="Smith",
        target_first="R John",
        target_last="Smith",
    )
    assert _matches(
        use_v2=False,
        source_first="Jose",
        source_last="Garcia",
        target_first="Jose Maria",
        target_last="Garcia",
    )
    assert _matches(
        use_v2=False,
        source_first="José",
        source_last="García",
        target_first="Jose",
        target_last="Garcia",
    )


def test_v1_does_not_get_v2_punctuation_or_last_token_matching() -> None:
    assert not _matches(
        use_v2=False,
        source_first="John-R",
        source_last="Smith Jones",
        target_first="John R",
        target_last="Smith-Jones",
    )


def test_v2_normalizes_punctuation_and_requires_sequence_order() -> None:
    assert _matches(
        use_v2=True,
        source_first="John-R",
        source_last="Smith Jones",
        target_first="John R",
        target_last="Smith-Jones",
    )
    assert not _matches(
        use_v2=True,
        source_first="R John",
        source_last="Smith",
        target_first="John R",
        target_last="Smith",
    )


@pytest.mark.parametrize(
    ("source_first", "target_first", "expected"),
    [
        ("John RB", "John R B", True),
        ("John R B", "John RB", True),
        ("RB John", "John R B", False),
        ("John RB", "John R B James", False),
    ],
)
def test_v2_compact_initials_rule_for_first_names(
    source_first: str,
    target_first: str,
    expected: bool,
) -> None:
    assert (
        _matches(
            use_v2=True,
            source_first=source_first,
            source_last="Smith",
            target_first=target_first,
            target_last="Smith",
        )
        is expected
    )


@pytest.mark.parametrize(
    ("source_first", "target_first", "expected"),
    [
        ("Abdul Latif M", "Abdul L M", True),
        ("L Abdul", "Abdul Latif", False),
        ("Abdul Latif Merem", "Abdul L", False),
    ],
)
def test_v2_initial_expansion_rule_for_first_names(
    source_first: str,
    target_first: str,
    expected: bool,
) -> None:
    assert (
        _matches(
            use_v2=True,
            source_first=source_first,
            source_last="Khan",
            target_first=target_first,
            target_last="Khan",
        )
        is expected
    )


def test_v2_fallback_rules_apply_to_last_names() -> None:
    assert _matches(
        use_v2=True,
        source_first="John",
        source_last="Smith RB",
        target_first="John",
        target_last="Smith R B",
    )
    assert not _matches(
        use_v2=True,
        source_first="John",
        source_last="RB Smith",
        target_first="John",
        target_last="Smith R B",
    )
