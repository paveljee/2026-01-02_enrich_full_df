from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class XlsxMatchSql:
    name_draws_fields: str
    pop_names_fields: str
    condition: str
    rule_payload_entry: str
    source_last_payload_expr: str
    target_last_payload_expr: str
    extra_ctes: str = ""
    name_draws_relation: str = "name_draws"
    pop_names_relation: str = "pop_names"
    base_select_keyword: str = "SELECT"
    match_path_priority_expr: str = ""


def xlsx_v2_tokens_sql(expr: str) -> str:
    normalized = (
        f"regexp_replace(lower(unaccent(COALESCE({expr}, ''))), "
        "'[[:punct:][:space:]]+', ' ', 'g')"
    )
    split = f"regexp_split_to_array(trim({normalized}), '\\s+')"
    return f"list_filter(list_transform({split}, token -> trim(token)), token -> token <> '')"


def xlsx_clean_tokens_sql(tokens_expr: str) -> str:
    return (
        "list_filter("
        f"list_transform({tokens_expr}, token -> trim(CAST(token AS VARCHAR))), "
        "token -> token <> ''"
        ")"
    )


def xlsx_v1_name_draws_fields_sql(first_expr: str, last_expr: str) -> str:
    return f"""
                   lower(unaccent({first_expr})) AS nd_first_clean,
                lower(unaccent({last_expr})) AS nd_last_clean,
                list_extract(
                       regexp_split_to_array(lower(unaccent({first_expr})), '\\s+'),
                       1
                   ) AS nd_first_token,
                regexp_split_to_array(lower(unaccent({first_expr})), '\\s+')
                    AS nd_first_tokens
    """


def xlsx_v1_pop_names_fields_sql(first_expr: str, last_expr: str) -> str:
    return f"""
                lower(unaccent({first_expr})) AS pop_first_clean,
                lower(unaccent({last_expr})) AS pop_last_clean,
                regexp_split_to_array(lower(unaccent({first_expr})), '\\s+')
                    AS pop_first_tokens,
                regexp_split_to_array(lower(unaccent({last_expr})), '\\s+')
                    AS pop_last_tokens,
    """


def xlsx_v2_name_draws_fields_sql(first_expr: str, last_expr: str) -> str:
    return f"""
                   {xlsx_v2_tokens_sql(first_expr)} AS nd_first_tokens,
                   {xlsx_v2_tokens_sql(last_expr)} AS nd_last_clean,
                   list_extract(
                       regexp_split_to_array(lower(unaccent({first_expr})), '\\s+'),
                       1
                   ) AS nd_v1_first_token,
                   lower(unaccent({last_expr})) AS nd_v1_last_clean
    """


def xlsx_v2_pop_names_fields_sql(first_expr: str, last_expr: str) -> str:
    return f"""
                {xlsx_v2_tokens_sql(first_expr)} AS pop_first_tokens,
                {xlsx_v2_tokens_sql(last_expr)} AS pop_last_clean,
                regexp_split_to_array(lower(unaccent({first_expr})), '\\s+')
                    AS pop_v1_first_tokens,
                lower(unaccent({last_expr})) AS pop_v1_last_clean,
    """


def xlsx_v1_match_condition_sql(
    *,
    source_first_expr: str,
    source_last_expr: str,
    target_first_expr: str,
    target_last_expr: str,
) -> str:
    return (
        f"{source_last_expr} = {target_last_expr} "
        f"AND list_contains({target_first_expr}, {source_first_expr})"
    )


def xlsx_compact_match_keys_sql(tokens_expr: str) -> str:
    tokens = xlsx_clean_tokens_sql(tokens_expr)
    return f"""
        (
            WITH RECURSIVE
            input(tokens) AS (
                SELECT {tokens}
            ),
            states(tokens, token_index, parts) AS (
                SELECT tokens, 1, CAST([] AS VARCHAR[])
                FROM input
                UNION (
                    SELECT
                        s.tokens,
                        s.token_index + 1,
                        list_concat(s.parts, [list_extract(s.tokens, s.token_index)])
                    FROM states s
                    WHERE s.token_index <= list_count(s.tokens)
                    UNION ALL
                    SELECT
                        s.tokens,
                        run_end + 1,
                        list_concat(
                            s.parts,
                            [
                                array_to_string(
                                    list_transform(
                                        range(s.token_index, run_end + 1),
                                        idx -> list_extract(s.tokens, idx)
                                    ),
                                    ''
                                )
                            ]
                        )
                    FROM states s,
                         UNNEST(range(s.token_index + 1, list_count(s.tokens) + 1))
                            AS r(run_end)
                    WHERE s.token_index <= list_count(s.tokens)
                      AND list_bool_and(
                          list_transform(
                              range(s.token_index, run_end + 1),
                              idx -> length(list_extract(s.tokens, idx)) = 1
                          )
                      )
                )
            ),
            keys AS (
                SELECT 'C|' || array_to_string(parts, chr(31)) AS match_key
                FROM states s
                WHERE s.token_index = list_count(s.tokens) + 1
                  AND list_count(parts) > 0
            )
            SELECT LIST(DISTINCT match_key ORDER BY match_key)
            FROM keys
        )
    """


def xlsx_initial_alternatives_sql(token_expr: str, *, side: str) -> str:
    if side == "source":
        return f"""
            CASE
                WHEN length({token_expr}) = 1 THEN ['x:' || {token_expr}, 's:' || {token_expr}]
                ELSE ['x:' || {token_expr}, 't:' || left({token_expr}, 1)]
            END
        """
    if side == "target":
        return f"""
            CASE
                WHEN length({token_expr}) = 1 THEN ['x:' || {token_expr}, 't:' || {token_expr}]
                ELSE ['x:' || {token_expr}, 's:' || left({token_expr}, 1)]
            END
        """
    raise ValueError(f"Unsupported XLSX match key side: {side}")


def xlsx_initial_match_keys_sql(tokens_expr: str, *, side: str) -> str:
    tokens = xlsx_clean_tokens_sql(tokens_expr)
    alternatives = xlsx_initial_alternatives_sql("list_extract(s.tokens, s.token_index)", side=side)
    return f"""
        (
            WITH RECURSIVE
            input(tokens) AS (
                SELECT {tokens}
            ),
            states(tokens, token_index, parts) AS (
                SELECT tokens, 1, CAST([] AS VARCHAR[])
                FROM input
                UNION ALL
                SELECT
                    s.tokens,
                    s.token_index + 1,
                    list_concat(s.parts, [alternative])
                FROM states s,
                     UNNEST({alternatives}) AS a(alternative)
                WHERE s.token_index <= list_count(s.tokens)
            ),
            keys AS (
                SELECT 'I|' || array_to_string(parts, chr(31)) AS match_key
                FROM states s
                WHERE s.token_index = list_count(s.tokens) + 1
                  AND list_count(parts) > 0
            )
            SELECT LIST(DISTINCT match_key ORDER BY match_key)
            FROM keys
        )
    """


def xlsx_token_match_keys_sql(tokens_expr: str, *, side: str) -> str:
    compact_keys = xlsx_compact_match_keys_sql(tokens_expr)
    initial_keys = xlsx_initial_match_keys_sql(tokens_expr, side=side)
    return f"""
        list_distinct(
            list_concat(
                COALESCE({compact_keys}, CAST([] AS VARCHAR[])),
                COALESCE({initial_keys}, CAST([] AS VARCHAR[]))
            )
        )
    """


def xlsx_v2_match_key_ctes_sql(*, rule_v1: str, rule_v2: str) -> str:
    return f"""
        ,
        name_draw_v2_keys AS (
            SELECT
                nd.*,
                '{rule_v2}' AS nd_xlsx_match_rule,
                0 AS nd_xlsx_match_priority,
                nd_first_key.match_key AS nd_first_match_key,
                nd_last_key.match_key AS nd_last_match_key
            FROM name_draws nd
            CROSS JOIN LATERAL UNNEST(
                {xlsx_token_match_keys_sql('nd.nd_first_tokens', side='source')}
            ) AS nd_first_key(match_key)
            CROSS JOIN LATERAL UNNEST(
                {xlsx_token_match_keys_sql('nd.nd_last_clean', side='source')}
            ) AS nd_last_key(match_key)
        ),
        name_draw_v1_keys AS (
            SELECT
                nd.*,
                '{rule_v1}' AS nd_xlsx_match_rule,
                1 AS nd_xlsx_match_priority,
                'V1F|' || nd.nd_v1_first_token AS nd_first_match_key,
                'V1L|' || nd.nd_v1_last_clean AS nd_last_match_key
            FROM name_draws nd
        ),
        name_draw_keys AS (
            SELECT * FROM name_draw_v2_keys
            UNION ALL
            SELECT * FROM name_draw_v1_keys
        ),
        pop_name_v2_keys AS (
            SELECT
                p.*,
                '{rule_v2}' AS pop_xlsx_match_rule,
                pop_first_key.match_key AS pop_first_match_key,
                pop_last_key.match_key AS pop_last_match_key
            FROM pop_names p
            CROSS JOIN LATERAL UNNEST(
                {xlsx_token_match_keys_sql('p.pop_first_tokens', side='target')}
            ) AS pop_first_key(match_key)
            CROSS JOIN LATERAL UNNEST(
                {xlsx_token_match_keys_sql('p.pop_last_clean', side='target')}
            ) AS pop_last_key(match_key)
        ),
        pop_name_v1_keys AS (
            SELECT
                p.*,
                '{rule_v1}' AS pop_xlsx_match_rule,
                'V1F|' || pop_v1_first_token AS pop_first_match_key,
                'V1L|' || p.pop_v1_last_clean AS pop_last_match_key
            FROM pop_names p
            CROSS JOIN LATERAL UNNEST(p.pop_v1_first_tokens)
                AS pop_first_token(pop_v1_first_token)
        ),
        pop_name_keys AS (
            SELECT * FROM pop_name_v2_keys
            UNION ALL
            SELECT * FROM pop_name_v1_keys
        )
    """


def xlsx_match_sql(
    *,
    use_v2: bool,
    source_first_expr: str,
    source_last_expr: str,
    target_first_expr: str,
    target_last_expr: str,
    rule_key: str,
    rule_v2: str,
    rule_v1: str = "v1",
) -> XlsxMatchSql:
    if use_v2:
        return XlsxMatchSql(
            name_draws_fields=xlsx_v2_name_draws_fields_sql(source_first_expr, source_last_expr),
            pop_names_fields=xlsx_v2_pop_names_fields_sql(target_first_expr, target_last_expr),
            condition=(
                "nd.nd_xlsx_match_rule = p.pop_xlsx_match_rule "
                "AND nd.nd_first_match_key = p.pop_first_match_key "
                "AND nd.nd_last_match_key = p.pop_last_match_key"
            ),
            rule_payload_entry=f"'{rule_key}', nd.nd_xlsx_match_rule,",
            source_last_payload_expr="to_json(nd.nd_last_clean)",
            target_last_payload_expr="to_json(p.pop_last_clean)",
            extra_ctes=xlsx_v2_match_key_ctes_sql(
                rule_v1=rule_v1,
                rule_v2=rule_v2,
            ),
            name_draws_relation="name_draw_keys",
            pop_names_relation="pop_name_keys",
            base_select_keyword="SELECT DISTINCT",
            match_path_priority_expr="nd.nd_xlsx_match_priority",
        )
    return XlsxMatchSql(
        name_draws_fields=xlsx_v1_name_draws_fields_sql(source_first_expr, source_last_expr),
        pop_names_fields=xlsx_v1_pop_names_fields_sql(target_first_expr, target_last_expr),
        condition=xlsx_v1_match_condition_sql(
            source_first_expr="nd.nd_first_token",
            source_last_expr="nd.nd_last_clean",
            target_first_expr="p.pop_first_tokens",
            target_last_expr="p.pop_last_clean",
        ),
        rule_payload_entry="",
        source_last_payload_expr="nd.nd_last_clean",
        target_last_payload_expr="p.pop_last_clean",
    )


def sciscinet_ktp_name_norm_sql(
    first_expr: str,
    last_expr: str,
    *,
    strip_tokens: bool,
) -> str:
    base = f"lower(unaccent({first_expr} || ' ' || {last_expr}))"
    return f"trim({base})" if strip_tokens else base


def sciscinet_author_name_norm_sql(name_expr: str, *, strip_tokens: bool) -> str:
    base = f"lower(unaccent({name_expr}))"
    return f"trim({base})" if strip_tokens else base


def docx_name_norm_sql(expr: str, *, coalesce_empty: bool = False) -> str:
    value_expr = f"COALESCE({expr}, '')" if coalesce_empty else expr
    return f"regexp_replace(lower(unaccent({value_expr})), '[^0-9a-z]+', '', 'g')"


def docx_match_condition_sql(first_norm_expr: str, last_norm_expr: str, docx_norm_expr: str) -> str:
    return (
        f"POSITION({first_norm_expr} IN {docx_norm_expr}) > 0 "
        f"AND POSITION({last_norm_expr} IN {docx_norm_expr}) > 0"
    )
