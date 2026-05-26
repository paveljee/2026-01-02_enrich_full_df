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
                   {xlsx_v2_tokens_sql(last_expr)} AS nd_last_clean
    """


def xlsx_v2_pop_names_fields_sql(first_expr: str, last_expr: str) -> str:
    return f"""
                {xlsx_v2_tokens_sql(first_expr)} AS pop_first_tokens,
                {xlsx_v2_tokens_sql(last_expr)} AS pop_last_clean,
    """


def xlsx_match_condition_sql(
    *,
    source_first_expr: str,
    source_last_expr: str,
    target_first_expr: str,
    target_last_expr: str,
    use_v2: bool,
) -> str:
    if use_v2:
        return (
            f"{xlsx_token_sequence_match_sql(source_first_expr, target_first_expr)} "
            f"AND {xlsx_token_sequence_match_sql(source_last_expr, target_last_expr)}"
        )
    return (
        f"{source_last_expr} = {target_last_expr} "
        f"AND list_contains({target_first_expr}, {source_first_expr})"
    )


def xlsx_initial_expansion_match_sql(left_tokens_expr: str, right_tokens_expr: str) -> str:
    left_tokens = xlsx_clean_tokens_sql(left_tokens_expr)
    right_tokens = xlsx_clean_tokens_sql(right_tokens_expr)
    return f"""
        (
            list_count({left_tokens}) = list_count({right_tokens})
            AND list_count({left_tokens}) > 0
            AND list_bool_and(
                list_transform(
                    range(1, list_count({left_tokens}) + 1),
                    idx -> list_extract({left_tokens}, idx) = list_extract({right_tokens}, idx)
                        OR (
                            length(list_extract({left_tokens}, idx)) = 1
                            AND starts_with(
                                list_extract({right_tokens}, idx),
                                list_extract({left_tokens}, idx)
                            )
                        )
                        OR (
                            length(list_extract({right_tokens}, idx)) = 1
                            AND starts_with(
                                list_extract({left_tokens}, idx),
                                list_extract({right_tokens}, idx)
                            )
                        )
                )
            )
        )
    """


def xlsx_compact_initials_one_way_match_sql(
    expanded_tokens_expr: str,
    compact_tokens_expr: str,
) -> str:
    expanded_tokens = xlsx_clean_tokens_sql(expanded_tokens_expr)
    compact_tokens = xlsx_clean_tokens_sql(compact_tokens_expr)
    return f"""
        (
            WITH RECURSIVE
            input(expanded_tokens, compact_tokens) AS (
                SELECT {expanded_tokens}, {compact_tokens}
            ),
            states(expanded_tokens, compact_tokens, expanded_index, compact_index) AS (
                SELECT expanded_tokens, compact_tokens, 1, 1
                FROM input
                UNION (
                    SELECT
                        s.expanded_tokens,
                        s.compact_tokens,
                        s.expanded_index + 1,
                        s.compact_index + 1
                    FROM states s
                    WHERE s.expanded_index <= list_count(s.expanded_tokens)
                      AND s.compact_index <= list_count(s.compact_tokens)
                      AND list_extract(s.expanded_tokens, s.expanded_index)
                          = list_extract(s.compact_tokens, s.compact_index)
                    UNION
                    SELECT
                        s.expanded_tokens,
                        s.compact_tokens,
                        run_end + 1,
                        s.compact_index + 1
                    FROM states s,
                         UNNEST(
                             range(s.expanded_index + 1, list_count(s.expanded_tokens) + 1)
                         ) AS r(run_end)
                    WHERE s.expanded_index <= list_count(s.expanded_tokens)
                      AND s.compact_index <= list_count(s.compact_tokens)
                      AND list_bool_and(
                          list_transform(
                              range(s.expanded_index, run_end + 1),
                              idx -> length(list_extract(s.expanded_tokens, idx)) = 1
                          )
                      )
                      AND list_extract(s.compact_tokens, s.compact_index) IN (
                          array_to_string(
                              list_transform(
                                  range(s.expanded_index, run_end + 1),
                                  idx -> list_extract(s.expanded_tokens, idx)
                              ),
                              ''
                          ),
                          array_to_string(
                              list_transform(
                                  range(s.expanded_index, run_end + 1),
                                  idx -> list_extract(s.expanded_tokens, idx)
                              ),
                              ' '
                          )
                      )
                )
            )
            SELECT EXISTS (
                SELECT 1
                FROM states s
                WHERE s.expanded_index = list_count(s.expanded_tokens) + 1
                  AND s.compact_index = list_count(s.compact_tokens) + 1
            )
        )
    """


def xlsx_token_sequence_match_sql(left_tokens_expr: str, right_tokens_expr: str) -> str:
    left_tokens = xlsx_clean_tokens_sql(left_tokens_expr)
    right_tokens = xlsx_clean_tokens_sql(right_tokens_expr)
    return f"""
        (
            list_count({left_tokens}) > 0
            AND list_count({right_tokens}) > 0
            AND (
                {left_tokens} = {right_tokens}
                OR {xlsx_compact_initials_one_way_match_sql(left_tokens_expr, right_tokens_expr)}
                OR {xlsx_compact_initials_one_way_match_sql(right_tokens_expr, left_tokens_expr)}
                OR {xlsx_initial_expansion_match_sql(left_tokens_expr, right_tokens_expr)}
            )
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
) -> XlsxMatchSql:
    if use_v2:
        return XlsxMatchSql(
            name_draws_fields=xlsx_v2_name_draws_fields_sql(source_first_expr, source_last_expr),
            pop_names_fields=xlsx_v2_pop_names_fields_sql(target_first_expr, target_last_expr),
            condition=xlsx_match_condition_sql(
                source_first_expr="nd.nd_first_tokens",
                source_last_expr="nd.nd_last_clean",
                target_first_expr="p.pop_first_tokens",
                target_last_expr="p.pop_last_clean",
                use_v2=True,
            ),
            rule_payload_entry=f"'{rule_key}', '{rule_v2}',",
            source_last_payload_expr="to_json(nd.nd_last_clean)",
            target_last_payload_expr="to_json(p.pop_last_clean)",
        )
    return XlsxMatchSql(
        name_draws_fields=xlsx_v1_name_draws_fields_sql(source_first_expr, source_last_expr),
        pop_names_fields=xlsx_v1_pop_names_fields_sql(target_first_expr, target_last_expr),
        condition=xlsx_match_condition_sql(
            source_first_expr="nd.nd_first_token",
            source_last_expr="nd.nd_last_clean",
            target_first_expr="p.pop_first_tokens",
            target_last_expr="p.pop_last_clean",
            use_v2=False,
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
