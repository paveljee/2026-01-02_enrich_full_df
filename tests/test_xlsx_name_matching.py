from __future__ import annotations

import json

import duckdb
import pytest

from src.helpers.name_matching import xlsx_match_sql
from src.helpers.vars import (
    KTP_XLSX_MATCH_RULE_KEY,
    KTP_XLSX_MATCH_RULE_V1,
    KTP_XLSX_MATCH_RULE_V2,
)


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


def _matched_rules(
    *,
    source_first: str,
    source_last: str,
    target_first: str,
    target_last: str,
) -> list[str]:
    conn = _connect()
    match_sql = xlsx_match_sql(
        use_v2=True,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
        rule_v1=KTP_XLSX_MATCH_RULE_V1,
    )
    return [
        str(row[0])
        for row in conn.execute(
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
            SELECT DISTINCT nd.nd_xlsx_match_rule
            FROM {match_sql.name_draws_relation} nd
            CROSS JOIN {match_sql.pop_names_relation} p
            WHERE {match_sql.condition}
            ORDER BY nd.nd_xlsx_match_rule
            """,
            [source_first, source_last, target_first, target_last],
        ).fetchall()
    ]


def _preferred_matched_rules(
    *,
    source_first: str,
    source_last: str,
    target_first: str,
    target_last: str,
) -> list[str]:
    conn = _connect()
    match_sql = xlsx_match_sql(
        use_v2=True,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
        rule_v1=KTP_XLSX_MATCH_RULE_V1,
    )
    return [
        str(row[0])
        for row in conn.execute(
            f"""
            WITH source_input(first_name, last_name) AS (VALUES (?, ?)),
            target_input(first_name, last_name) AS (VALUES (?, ?)),
            name_draws AS (
                SELECT
                    'source' AS "ktp.source_key",
                    nk.first_name,
                    nk.last_name,
                    {match_sql.name_draws_fields}
                FROM source_input nk
            ),
            pop_names AS (
                SELECT
                    'hcr.xlsx' AS "hcr.filename",
                    1 AS "hcr.row_number",
                    n.first_name AS pop_first,
                    n.last_name AS pop_last,
                    {match_sql.pop_names_fields}
                    1 AS sentinel
                FROM target_input n
            ){match_sql.extra_ctes}
            , base_candidates AS (
                SELECT DISTINCT
                    'source' AS "ktp.source_key",
                    'hcr.xlsx' AS "ktp.filename",
                    1 AS "ktp.fragment",
                    nd.nd_xlsx_match_rule,
                    {match_sql.match_path_priority_expr} AS xlsx_match_path_priority
                FROM {match_sql.name_draws_relation} nd
                CROSS JOIN {match_sql.pop_names_relation} p
                WHERE {match_sql.condition}
            ),
            base_min_priority AS (
                SELECT
                    "ktp.source_key",
                    "ktp.filename",
                    "ktp.fragment",
                    MIN(xlsx_match_path_priority) AS xlsx_match_path_priority
                FROM base_candidates
                GROUP BY "ktp.source_key", "ktp.filename", "ktp.fragment"
            )
            SELECT bc.nd_xlsx_match_rule
            FROM base_candidates bc
            JOIN base_min_priority bp
              ON bc."ktp.source_key" = bp."ktp.source_key"
             AND bc."ktp.filename" = bp."ktp.filename"
             AND bc."ktp.fragment" = bp."ktp.fragment"
             AND bc.xlsx_match_path_priority = bp.xlsx_match_path_priority
            ORDER BY bc.nd_xlsx_match_rule
            """,
            [source_first, source_last, target_first, target_last],
        ).fetchall()
    ]


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
        "nd.nd_xlsx_match_rule = p.pop_xlsx_match_rule "
        "AND nd.nd_first_match_key = p.pop_first_match_key "
        "AND nd.nd_last_match_key = p.pop_last_match_key"
    )
    assert match_sql.name_draws_relation == "name_draw_keys"
    assert match_sql.pop_names_relation == "pop_name_keys"
    assert match_sql.base_select_keyword == "SELECT DISTINCT"
    assert match_sql.match_path_priority_expr == "nd.nd_xlsx_match_priority"


def test_v1_payload_includes_rule_version() -> None:
    match_sql = xlsx_match_sql(
        use_v2=False,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
        rule_v1=KTP_XLSX_MATCH_RULE_V1,
    )
    row = _connect().execute(
        f"""
        SELECT json_object(
            {match_sql.rule_payload_entry}
            'sentinel', 'ok'
        )
        """
    ).fetchone()
    assert row is not None
    payload = json.loads(row[0])

    assert payload[KTP_XLSX_MATCH_RULE_KEY] == KTP_XLSX_MATCH_RULE_V1


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


def test_v2_includes_original_v1_candidate_as_v1_rule() -> None:
    assert _matches(
        use_v2=True,
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano Nunes",
        target_last="Nunes-Nesi",
    )
    assert _matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano Nunes",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V1]
    assert _preferred_matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano Nunes",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V1]


def test_v2_preferred_when_candidate_also_matches_original_v1_rule() -> None:
    assert _matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V1, KTP_XLSX_MATCH_RULE_V2]
    assert _preferred_matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V2]


def test_v2_normalizes_punctuation_and_requires_sequence_order() -> None:
    assert KTP_XLSX_MATCH_RULE_V2 in _matched_rules(
        source_first="John-R",
        source_last="Smith Jones",
        target_first="John R",
        target_last="Smith-Jones",
    )
    assert _matched_rules(
        source_first="R John",
        source_last="Smith",
        target_first="John R",
        target_last="Smith",
    ) == [KTP_XLSX_MATCH_RULE_V1]


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
    rules = _matched_rules(
        source_first=source_first,
        source_last="Smith",
        target_first=target_first,
        target_last="Smith",
    )
    assert (KTP_XLSX_MATCH_RULE_V2 in rules) is expected


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
    rules = _matched_rules(
        source_first=source_first,
        source_last="Khan",
        target_first=target_first,
        target_last="Khan",
    )
    assert (KTP_XLSX_MATCH_RULE_V2 in rules) is expected


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
