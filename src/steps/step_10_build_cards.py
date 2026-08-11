from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from ..helpers.cards import build_cards, write_cards_zip
from ..helpers.context import PipelineContext, StepResult
from ..helpers.data_models import FragmentType, InnerDict, NameKey, OuterDict, ResourceGroup
from ..helpers.duckdb_utils import (
    duckdb_quote_identifier,
    register_frame,
)
from ..helpers.schema import (
    CARD_PARTITION_REVIEW_ROWS_TABLE,
    CARD_PARTITION_REVIEW_VIEW,
    CARD_PARTITION_TABLE,
    DOCX_OUTPUT_VIEW,
    PARQUET_OUTPUT_VIEW,
    XLSX_OUTPUT_VIEW,
)
from ..helpers.vars import (
    CARD_BUILD_SUBSET_DESCRIPTIONS,
    CARD_INTRODUCTION,
    CARD_PARTITION_ARTIFACT_MODES,
    CSV_ROW_INDEX_COL,
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    DRAW_LABEL,
    HCR_CATEGORY_COL,
    HCR_XLSX_KEY_PREFIX,
    KTP_DOCX_MATCH_COL,
    KTP_DOCX_OPTIONAL_EMPTY_COLS,
    KTP_DOCX_TABLE_1_PREFIX,
    KTP_ECONOMIES_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FF_AUTHOR_ID_COL,
    KTP_FF_DISCARD_COL,
    KTP_FF_NOTE_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_PARTITION_COL,
    KTP_PARTITION_DOCX_VALUE,
    KTP_PARTITION_FLAG_DOCX_ANY_COL,
    KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_ANY_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
    KTP_PARTITION_NO_RESOLUTION_VALUE,
    KTP_PARTITION_SSN_VALUE,
    KTP_PARTITION_XLSX_VALUE,
    KTP_NAMEKEY_COL,
    KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
    KTP_SSN_SUM_HIT_1PCT_COL,
    KTP_SSN_TOP_INSTITUTIONS_COL,
    KTP_SSNAD_FILENAME_COL,
    KTP_SSNAD_MATCH_COL,
    KTP_SSNAF_FILENAME_COL,
    KTP_SSNAP_FILENAME_COL,
    KTP_SSNAU_FILENAME_COL,
    KTP_SSNF_FILENAME_COL,
    KTP_SSNHPL0_FILENAME_COL,
    KTP_SSNHPL1_FILENAME_COL,
    KTP_SSNP_FILENAME_COL,
    KTP_SSNPAA_FILENAME_COL,
    KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_RULE_KEY,
    KTP_XLSX_MATCH_RULE_V1,
    KTP_XLSX_MATCH_RULE_V2,
    KTP_XLSX_MATCH_NAMEKEY_LAST_KEY,
    KTP_XLSX_MATCH_NAMEKEY_TOKENS_KEY,
    SSNAD_CITED_BY_COUNT_COL,
    SSNAD_DISPLAY_NAME_ALTERNATIVES_COL,
    SSNAD_DISPLAY_NAME_COL,
    SSNAD_WORKS_API_URL_COL,
    SSNAD_WORKS_COUNT_COL,
    STEP_BUILD_CARDS,
)
from .shared import draw_sort_ctes_sql, draw_sort_order_by_sql

CARD_PARTITION_FRAME_TABLE = "card_partition_frame"
XLSX_REVIEW_SOURCE_TABLE = "card_partition_review_xlsx_source"
SCISCINET_REVIEW_SOURCE_TABLE = "card_partition_review_sciscinet_source"
DOCX_REVIEW_SOURCE_TABLE = "card_partition_review_docx_source"
REVIEW_DOMAIN_XLSX = "xlsx"
REVIEW_DOMAIN_SCISCINET = "sciscinet"
REVIEW_DOMAIN_DOCX = "docx"
XLSX_CONTEXT_CTE = "xlsx_context"
SCISCINET_CONTEXT_CTE = "sciscinet_context"
DOCX_CONTEXT_CTE = "docx_context"
REVIEW_CONTEXT_ALIASES = {
    REVIEW_DOMAIN_XLSX: "xs",
    REVIEW_DOMAIN_SCISCINET: "ss",
    REVIEW_DOMAIN_DOCX: "ds",
}


@dataclass(frozen=True)
class CardPartitionRuleState:
    name_key: NameKey
    source_key: str
    first_name: str
    last_name: str
    draw_number: object | None
    xlsx_non_exact_any: bool
    xlsx_any: bool
    sciscinet_count: int
    docx_table_1_required_all: bool
    docx_any: bool

    @property
    def xlsx_ok(self) -> bool:
        return self.xlsx_any and not self.xlsx_non_exact_any

    @property
    def docx_ok(self) -> bool:
        return self.docx_any and self.docx_table_1_required_all

    @property
    def sciscinet_ok(self) -> bool:
        return self.sciscinet_count == 1

    @property
    def subset1_ok(self) -> bool:
        return self.xlsx_ok and self.docx_ok and self.sciscinet_ok


def _qualified(alias: str, col: str) -> str:
    return f"{alias}.{duckdb_quote_identifier(col)}"


def _extract_filenames(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return set()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                return {
                    Path(str(item)).name
                    for item in parsed
                    if item is not None and str(item).strip()
                }
            except json.JSONDecodeError:
                return {Path(raw).name}
        return {Path(raw).name}
    if isinstance(value, (list, tuple, set)):
        return {Path(str(item)).name for item in value if item is not None and str(item).strip()}
    return {Path(str(value)).name}


def _is_sciscinet_inner(inner: InnerDict, sciscinet_filenames: set[str]) -> bool:
    filename_cols = [
        KTP_FILENAME_COL,
        KTP_SSNAD_FILENAME_COL,
        KTP_SSNAU_FILENAME_COL,
        KTP_SSNAP_FILENAME_COL,
        KTP_SSNPAA_FILENAME_COL,
        KTP_SSNP_FILENAME_COL,
        KTP_SSNAF_FILENAME_COL,
        KTP_SSNHPL0_FILENAME_COL,
        KTP_SSNHPL1_FILENAME_COL,
        KTP_SSNF_FILENAME_COL,
    ]
    for col in filename_cols:
        values = _extract_filenames(inner.data.get(col))
        if values & sciscinet_filenames:
            return True
    return False


def _is_exact_xlsx_match_payload(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return True
    raw = value.strip()
    if not raw:
        return True
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    source_key_tokens = payload.get(KTP_XLSX_MATCH_NAMEKEY_TOKENS_KEY, [])
    source_key_last = payload.get(KTP_XLSX_MATCH_NAMEKEY_LAST_KEY)
    first_tokens = payload.get(KTP_XLSX_MATCH_FIRST_TOKENS_KEY, [])
    last_name_norm = payload.get(KTP_XLSX_MATCH_LAST_NAME_NORM_KEY)
    if not isinstance(source_key_tokens, list):
        source_key_tokens = []
    if not isinstance(first_tokens, list):
        first_tokens = []
    match_rule = payload.get(KTP_XLSX_MATCH_RULE_KEY)
    if match_rule == KTP_XLSX_MATCH_RULE_V1:
        if isinstance(source_key_last, list) or isinstance(last_name_norm, list):
            return False
    if match_rule == KTP_XLSX_MATCH_RULE_V2:
        source_key_last_tokens = source_key_last if isinstance(source_key_last, list) else []
        last_name_tokens = last_name_norm if isinstance(last_name_norm, list) else []
        return bool(
            source_key_tokens
            and first_tokens
            and source_key_last_tokens
            and last_name_tokens
        )
    source_key_last_str = str(source_key_last).strip() if source_key_last is not None else ""
    last_name_norm_str = str(last_name_norm).strip() if last_name_norm is not None else ""
    source_key_token_values = sorted(
        {str(token).strip() for token in source_key_tokens if str(token).strip()}
    )
    if not source_key_token_values or not source_key_last_str:
        return False
    first_token_values = sorted(
        {str(token).strip() for token in first_tokens if str(token).strip()}
    )
    return (
        source_key_token_values == first_token_values
        and bool(last_name_norm_str)
        and source_key_last_str == last_name_norm_str
    )


def _has_present_xlsx_match_payload(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _is_non_empty_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return False
        if normalized in KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS:
            return False
        return True
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return True


def _has_complete_docx_table_fields(inner: InnerDict) -> bool:
    docx_cols = [
        col
        for col in inner.data.keys()
        if col.startswith(KTP_DOCX_TABLE_1_PREFIX) and col not in KTP_DOCX_OPTIONAL_EMPTY_COLS
    ]
    if not docx_cols:
        return True
    return all(_is_non_empty_value(inner.data.get(col)) for col in docx_cols)


def _mode_matches(
    mode: int,
    *,
    sciscinet_exactly_one_ok: bool,
    xlsx_exact_ok: bool,
    docx_complete_ok: bool,
) -> bool:
    if mode == 0:
        return True
    if mode == 1:
        return sciscinet_exactly_one_ok and xlsx_exact_ok and docx_complete_ok
    if mode == 2:
        return not (sciscinet_exactly_one_ok and xlsx_exact_ok and docx_complete_ok)
    if mode == 3:
        return sciscinet_exactly_one_ok and xlsx_exact_ok
    if mode == 4:
        return not (sciscinet_exactly_one_ok and xlsx_exact_ok)
    raise ValueError(f"Unsupported card_subset_mode={mode}")


def _first_present_value(inner_dicts: tuple[InnerDict, ...], col: str) -> object | None:
    for inner in inner_dicts:
        value = inner.data.get(col)
        if _is_non_empty_value(value):
            return value
    return None


def _evaluate_card_partition_state(
    name_key: NameKey,
    inner_dicts: tuple[InnerDict, ...],
    *,
    sciscinet_filenames: set[str],
    docx_filenames: set[str],
) -> CardPartitionRuleState:
    sciscinet_count = sum(
        1 for inner in inner_dicts if _is_sciscinet_inner(inner, sciscinet_filenames)
    )
    xlsx_match_payloads = [inner.data.get(KTP_XLSX_MATCH_COL) for inner in inner_dicts]
    xlsx_any = any(_has_present_xlsx_match_payload(value) for value in xlsx_match_payloads)
    xlsx_non_exact_any = any(
        not _is_exact_xlsx_match_payload(value) for value in xlsx_match_payloads
    )
    docx_innerdicts = []
    for inner in inner_dicts:
        filenames = _extract_filenames(inner.data.get(KTP_FILENAME_COL))
        if filenames & docx_filenames:
            docx_innerdicts.append(inner)
    docx_any = bool(docx_innerdicts)
    docx_table_1_required_all = docx_any and any(
        _has_complete_docx_table_fields(inner) for inner in docx_innerdicts
    )
    return CardPartitionRuleState(
        name_key=name_key,
        source_key=name_key.to_json_key(),
        first_name=name_key.first_name,
        last_name=name_key.last_name,
        draw_number=_first_present_value(inner_dicts, DRAW_LABEL),
        xlsx_non_exact_any=xlsx_non_exact_any,
        xlsx_any=xlsx_any,
        sciscinet_count=sciscinet_count,
        docx_table_1_required_all=docx_table_1_required_all,
        docx_any=docx_any,
    )


def _resource_filename_sets(context: PipelineContext) -> tuple[set[str], set[str]]:
    sciscinet_filenames: set[str] = set()
    docx_filenames: set[str] = set()
    if context.resources is None:
        return sciscinet_filenames, docx_filenames
    all_resources = (
        list(context.resources.parquet_resources.values())
        + list(context.resources.xlsx_resources.values())
        + [context.resources.world_bank_resource]
        + list(context.resources.docx_resources.values())
    )
    all_resources.append(context.resources.openalex_author_search_log_resource)
    all_resources.append(context.resources.openalex_paper_title_log_resource)
    sciscinet_filenames = {
        resource.name for resource in all_resources if resource.group == ResourceGroup.SCISCINET_HF
    }
    docx_filenames = {
        resource.name
        for resource in all_resources
        if resource.group == ResourceGroup.KTP_MANUAL_EXTRACTIONS
        and resource.fragment_type == FragmentType.DOCX_ROW
    }
    return sciscinet_filenames, docx_filenames


def _subset_items_and_states(
    outer_dict: OuterDict,
    *,
    sciscinet_filenames: set[str],
    docx_filenames: set[str],
) -> tuple[
    dict[int, list[tuple[NameKey, tuple[InnerDict, ...]]]],
    dict[str, CardPartitionRuleState],
    dict[str, int],
]:
    subset_mode_items: dict[int, list[tuple[NameKey, tuple[InnerDict, ...]]]] = {
        mode: [] for mode in CARD_BUILD_SUBSET_DESCRIPTIONS
    }
    state_by_source_key: dict[str, CardPartitionRuleState] = {}
    stats = {
        "total": 0,
        "sciscinet_count_pass": 0,
        "sciscinet_count_failures": 0,
        "xlsx_match_pass": 0,
        "xlsx_match_failed": 0,
        "docx_table_fields_pass": 0,
        "docx_table_fields_failed": 0,
    }
    for name_key, inner_dicts in outer_dict.items():
        stats["total"] += 1
        state = _evaluate_card_partition_state(
            name_key,
            inner_dicts,
            sciscinet_filenames=sciscinet_filenames,
            docx_filenames=docx_filenames,
        )
        state_by_source_key[state.source_key] = state
        if state.sciscinet_ok:
            stats["sciscinet_count_pass"] += 1
        else:
            stats["sciscinet_count_failures"] += 1
        if state.xlsx_ok:
            stats["xlsx_match_pass"] += 1
        else:
            stats["xlsx_match_failed"] += 1
        if state.docx_ok:
            stats["docx_table_fields_pass"] += 1
        else:
            stats["docx_table_fields_failed"] += 1

        for mode in subset_mode_items:
            if _mode_matches(
                mode,
                sciscinet_exactly_one_ok=state.sciscinet_ok,
                xlsx_exact_ok=state.xlsx_ok,
                docx_complete_ok=state.docx_ok,
            ):
                subset_mode_items[mode].append((name_key, inner_dicts))
    return subset_mode_items, state_by_source_key, stats


def _partition_value(state: CardPartitionRuleState) -> int:
    if state.subset1_ok:
        return KTP_PARTITION_NO_RESOLUTION_VALUE
    if not state.xlsx_ok and state.docx_ok and state.sciscinet_ok:
        return KTP_PARTITION_XLSX_VALUE
    if state.docx_ok and not state.sciscinet_ok:
        return KTP_PARTITION_SSN_VALUE
    return KTP_PARTITION_DOCX_VALUE


def _partition_priority(partition_value: int) -> int:
    return {
        KTP_PARTITION_XLSX_VALUE: 0,
        KTP_PARTITION_SSN_VALUE: 1,
        KTP_PARTITION_DOCX_VALUE: 2,
        KTP_PARTITION_NO_RESOLUTION_VALUE: 3,
    }.get(partition_value, 99)


def _draw_sort_key(value: object | None) -> tuple[int, int, str]:
    if value is None:
        return (3, 999999999, "")
    try:
        if bool(pd.isna(value)):
            return (3, 999999999, "")
    except (TypeError, ValueError):
        pass
    raw = str(value).strip()
    if not raw:
        return (3, 999999999, "")
    if raw.startswith("pilot."):
        try:
            return (0, int(raw.split(".", 1)[1]), raw)
        except (IndexError, ValueError):
            return (0, 999999999, raw)
    try:
        return (1, int(raw), raw)
    except ValueError:
        return (2, 999999999, raw)


def _partition_sort_key(state: CardPartitionRuleState) -> tuple[Any, ...]:
    partition_value = _partition_value(state)
    sciscinet_tie_sort = 0 if state.xlsx_ok else 1
    return (
        _partition_priority(partition_value),
        state.sciscinet_count if partition_value == KTP_PARTITION_SSN_VALUE else 0,
        sciscinet_tie_sort if partition_value == KTP_PARTITION_SSN_VALUE else 0,
        _draw_sort_key(state.draw_number),
        state.source_key,
    )


def _partition_rows_df(
    selected_items: list[tuple[NameKey, tuple[InnerDict, ...]]],
    *,
    state_by_source_key: dict[str, CardPartitionRuleState],
    subset_mode: int,
) -> pd.DataFrame:
    states = [state_by_source_key[name_key.to_json_key()] for name_key, _ in selected_items]
    states.sort(key=_partition_sort_key)
    columns = [
        KTP_NAMEKEY_COL,
        KTP_PARTITION_COL,
        KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
        KTP_PARTITION_FLAG_XLSX_ANY_COL,
        KTP_PARTITION_FLAG_SSN_COUNT_COL,
        KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL,
        KTP_PARTITION_FLAG_DOCX_ANY_COL,
        "card_subset_mode",
        DRAW_LABEL,
        KTP_FIRST_NAME_COL,
        KTP_LAST_NAME_COL,
    ]
    records = [
        {
            KTP_NAMEKEY_COL: state.source_key,
            KTP_PARTITION_COL: _partition_value(state),
            KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: state.xlsx_non_exact_any,
            KTP_PARTITION_FLAG_XLSX_ANY_COL: state.xlsx_any,
            KTP_PARTITION_FLAG_SSN_COUNT_COL: state.sciscinet_count,
            KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: state.docx_table_1_required_all,
            KTP_PARTITION_FLAG_DOCX_ANY_COL: state.docx_any,
            "card_subset_mode": subset_mode,
            DRAW_LABEL: state.draw_number,
            KTP_FIRST_NAME_COL: state.first_name,
            KTP_LAST_NAME_COL: state.last_name,
        }
        for state in states
    ]
    return pd.DataFrame(records, columns=columns)


def _materialize_partition_table(
    conn: duckdb.DuckDBPyConnection,
    partition_df: pd.DataFrame,
) -> None:
    register_frame(conn, CARD_PARTITION_FRAME_TABLE, partition_df)
    conn.execute(
        f"CREATE OR REPLACE TABLE {CARD_PARTITION_TABLE} AS "
        f"SELECT * FROM {CARD_PARTITION_FRAME_TABLE}"
    )
    conn.execute(f"DROP TABLE IF EXISTS {CARD_PARTITION_FRAME_TABLE}")


def _materialize_partition_review_source_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    source_view: str,
    table_name: str,
) -> None:
    source_key = duckdb_quote_identifier(KTP_NAMEKEY_COL)
    conn.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE {table_name} AS
        SELECT source.*
        FROM {source_view} source
        JOIN {CARD_PARTITION_TABLE} cp
          ON source.{source_key} = cp.{source_key}
        """
    )


def _drop_partition_review_source_tables(conn: duckdb.DuckDBPyConnection) -> None:
    for table_name in (
        XLSX_REVIEW_SOURCE_TABLE,
        SCISCINET_REVIEW_SOURCE_TABLE,
        DOCX_REVIEW_SOURCE_TABLE,
    ):
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")


def _relation_columns(conn: duckdb.DuckDBPyConnection, relation_name: str) -> list[str]:
    try:
        return [row[0] for row in conn.execute(f"DESCRIBE {relation_name}").fetchall()]
    except duckdb.CatalogException as exc:
        raise ValueError(
            f"Missing required relation '{relation_name}' for card partition review view."
        ) from exc


def _required_docx_table1_columns(docx_columns: list[str]) -> list[str]:
    return [
        col
        for col in docx_columns
        if col.startswith(KTP_DOCX_TABLE_1_PREFIX) and col not in KTP_DOCX_OPTIONAL_EMPTY_COLS
    ]


def _review_columns(docx_columns: list[str]) -> list[str]:
    return [
        KTP_NAMEKEY_COL,
        KTP_PARTITION_COL,
        KTP_FILENAME_COL,
        KTP_FRAGMENT_COL,
        KTP_FRAGMENT_TYPE_COL,
        DRAW_LABEL,
        KTP_FF_AUTHOR_ID_COL,
        KTP_FF_DISCARD_COL,
        KTP_FF_NOTE_COL,
        KTP_FIRST_NAME_COL,
        KTP_LAST_NAME_COL,
        SSNAD_DISPLAY_NAME_COL,
        SSNAD_DISPLAY_NAME_ALTERNATIVES_COL,
        HCR_CATEGORY_COL,
        KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
        KTP_ECONOMIES_COL,
        KTP_ECONOMY_MATCH_COL,
        KTP_HCR_PRIMARY_AFFILIATIONS_COL,
        KTP_HCR_SECONDARY_AFFILIATIONS_COL,
        KTP_SSN_TOP_INSTITUTIONS_COL,
        KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
        KTP_PARTITION_FLAG_XLSX_ANY_COL,
        KTP_XLSX_MATCH_COL,
        KTP_PARTITION_FLAG_SSN_COUNT_COL,
        KTP_SSNAD_MATCH_COL,
        KTP_SSN_SUM_HIT_1PCT_COL,
        SSNAD_WORKS_COUNT_COL,
        SSNAD_CITED_BY_COUNT_COL,
        SSNAD_WORKS_API_URL_COL,
        KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL,
        KTP_PARTITION_FLAG_DOCX_ANY_COL,
        KTP_DOCX_MATCH_COL,
        *_required_docx_table1_columns(docx_columns),
    ]


def _review_info_domain(col: str) -> str | None:
    if col in {
        HCR_CATEGORY_COL,
        KTP_ECONOMIES_COL,
        KTP_ECONOMY_MATCH_COL,
        KTP_HCR_PRIMARY_AFFILIATIONS_COL,
        KTP_HCR_SECONDARY_AFFILIATIONS_COL,
        KTP_XLSX_MATCH_COL,
    }:
        return REVIEW_DOMAIN_XLSX
    if col in {
        SSNAD_DISPLAY_NAME_COL,
        SSNAD_DISPLAY_NAME_ALTERNATIVES_COL,
        KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
        KTP_SSN_TOP_INSTITUTIONS_COL,
        KTP_SSNAD_MATCH_COL,
        KTP_SSN_SUM_HIT_1PCT_COL,
        SSNAD_WORKS_COUNT_COL,
        SSNAD_CITED_BY_COUNT_COL,
        SSNAD_WORKS_API_URL_COL,
    }:
        return REVIEW_DOMAIN_SCISCINET
    if col == KTP_DOCX_MATCH_COL or col.startswith(KTP_DOCX_TABLE_1_PREFIX):
        return REVIEW_DOMAIN_DOCX
    return None


def _review_context_has_col(
    *,
    col: str,
    target_domain: str,
    domain_columns: dict[str, set[str]],
) -> bool:
    if col in {KTP_FILENAME_COL, KTP_FRAGMENT_COL, KTP_FRAGMENT_TYPE_COL}:
        return col in domain_columns[target_domain]
    return _review_info_domain(col) == target_domain and col in domain_columns[target_domain]


def _empty_varchar_list_expr() -> str:
    return "CAST([] AS VARCHAR[])"


def _review_context_list_expr(
    *,
    col: str,
    target_domain: str,
    domain_columns: dict[str, set[str]],
) -> str:
    if not _review_context_has_col(
        col=col,
        target_domain=target_domain,
        domain_columns=domain_columns,
    ):
        return _empty_varchar_list_expr()
    alias = REVIEW_CONTEXT_ALIASES[target_domain]
    return f"COALESCE({_qualified(alias, col)}, {_empty_varchar_list_expr()})"


def _list_concat_expr(values: list[str]) -> str:
    if not values:
        return _empty_varchar_list_expr()
    merged = values[0]
    for value in values[1:]:
        merged = f"list_concat({merged}, {value})"
    return merged


def _review_domain_expr(
    *,
    col: str,
    target_domain: str,
    primary_alias: str | None,
    primary_domain: str,
    domain_columns: dict[str, set[str]],
) -> str:
    if _review_context_has_col(
        col=col,
        target_domain=target_domain,
        domain_columns=domain_columns,
    ):
        return _review_context_merge_expr(
            _review_context_list_expr(
                col=col,
                target_domain=target_domain,
                domain_columns=domain_columns,
            )
        )
    if target_domain == primary_domain and primary_alias is not None:
        if col in domain_columns[target_domain]:
            return f"CAST({_qualified(primary_alias, col)} AS VARCHAR)"
    return "CAST(NULL AS VARCHAR)"


def _review_source_expr(
    *,
    primary_alias: str | None,
    primary_domain: str,
    domain_columns: dict[str, set[str]],
    col: str,
) -> str:
    if col == KTP_NAMEKEY_COL:
        return _qualified("cp", col)
    if col == KTP_PARTITION_COL:
        return _qualified("cp", col)
    if col == KTP_FF_AUTHOR_ID_COL:
        if primary_domain == REVIEW_DOMAIN_SCISCINET and primary_alias is not None:
            if KTP_FRAGMENT_COL in domain_columns[REVIEW_DOMAIN_SCISCINET]:
                return f"CAST({_qualified(primary_alias, KTP_FRAGMENT_COL)} AS VARCHAR)"
        return _review_context_merge_expr(
            _review_context_list_expr(
                col=KTP_FRAGMENT_COL,
                target_domain=REVIEW_DOMAIN_SCISCINET,
                domain_columns=domain_columns,
            )
        )
    if col == KTP_FF_DISCARD_COL:
        return "CAST(NULL AS BOOLEAN)"
    if col == KTP_FF_NOTE_COL:
        return "CAST(NULL AS VARCHAR)"
    if col in {
        KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
        KTP_PARTITION_FLAG_XLSX_ANY_COL,
        KTP_PARTITION_FLAG_SSN_COUNT_COL,
        KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL,
        KTP_PARTITION_FLAG_DOCX_ANY_COL,
    }:
        return _qualified("cp", col)
    if col in {KTP_FILENAME_COL, KTP_FRAGMENT_COL, KTP_FRAGMENT_TYPE_COL}:
        values = [
            _review_context_list_expr(
                col=col,
                target_domain=domain,
                domain_columns=domain_columns,
            )
            for domain in (REVIEW_DOMAIN_XLSX, REVIEW_DOMAIN_SCISCINET, REVIEW_DOMAIN_DOCX)
        ]
        return _review_context_merge_expr(_list_concat_expr(values))
    if col in {DRAW_LABEL, KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL}:
        return f"CAST({_qualified('cp', col)} AS VARCHAR)"
    target_domain = _review_info_domain(col)
    if target_domain is not None:
        return _review_domain_expr(
            col=col,
            target_domain=target_domain,
            primary_alias=primary_alias,
            primary_domain=primary_domain,
            domain_columns=domain_columns,
        )
    return "NULL"


def _review_select_list(
    columns: list[str],
    *,
    primary_alias: str | None,
    primary_domain: str,
    domain_columns: dict[str, set[str]],
) -> str:
    exprs: list[str] = []
    for col in columns:
        expr = _review_source_expr(
            primary_alias=primary_alias,
            primary_domain=primary_domain,
            domain_columns=domain_columns,
            col=col,
        )
        exprs.append(f"{expr} AS {duckdb_quote_identifier(col)}")
    return ",\n                ".join(exprs)


def _review_context_specs(
    *,
    source_domain: str,
    source_columns: set[str],
    review_columns: list[str],
) -> dict[str, str]:
    specs = {
        col: col
        for col in review_columns
        if _review_info_domain(col) == source_domain and col in source_columns
    }
    for col in (KTP_FILENAME_COL, KTP_FRAGMENT_COL, KTP_FRAGMENT_TYPE_COL):
        if col in source_columns:
            specs[col] = col
    return specs


def _review_context_values_expr(
    *,
    source_alias: str,
    source_col: str,
    source_columns: set[str],
) -> str:
    value_expr = f"CAST({_qualified(source_alias, source_col)} AS VARCHAR)"
    order_candidates = [KTP_FILENAME_COL, KTP_FRAGMENT_COL, KTP_FRAGMENT_TYPE_COL, source_col]
    order_cols: list[str] = []
    for col in order_candidates:
        if col in source_columns and col not in order_cols:
            order_cols.append(col)
    order_sql = ", ".join(
        f"CAST({_qualified(source_alias, col)} AS VARCHAR)" for col in order_cols
    )
    if not order_sql:
        order_sql = value_expr
    return (
        "list_filter("
        f"list(CASE WHEN {_qualified(source_alias, source_col)} IS NOT NULL "
        f"AND trim({value_expr}) <> '' THEN {value_expr} ELSE NULL END "
        f"ORDER BY {order_sql}), "
        "value -> value IS NOT NULL)"
    )


def _review_context_merge_expr(values_col: str) -> str:
    return f"""
        CASE
            WHEN list_count({values_col}) = 0 THEN NULL
            WHEN list_count(
                list_filter(
                    {values_col},
                    value -> contains(value, chr(10)) OR contains(value, chr(13))
                )
            ) > 0
                THEN array_to_string({values_col}, chr(10) || '-----' || chr(10))
            ELSE array_to_string({values_col}, chr(10))
        END
    """


def _review_context_cte_sql(
    *,
    cte_name: str,
    source_view: str,
    source_alias: str,
    source_domain: str,
    source_columns: set[str],
    review_columns: list[str],
) -> str:
    specs = _review_context_specs(
        source_domain=source_domain,
        source_columns=source_columns,
        review_columns=review_columns,
    )
    if not specs:
        return f"""
        {cte_name} AS (
            SELECT DISTINCT {duckdb_quote_identifier(KTP_NAMEKEY_COL)}
            FROM {source_view}
        )
        """

    values_cte_name = f"{cte_name}_values"
    values_cols = {col: f"__review_value_{idx}" for idx, col in enumerate(specs)}
    values_select = ",\n                ".join(
        f"{_review_context_values_expr(
            source_alias=source_alias,
            source_col=source_col,
            source_columns=source_columns,
        )} AS {duckdb_quote_identifier(values_col)}"
        for col, source_col in specs.items()
        for values_col in [values_cols[col]]
    )
    context_select = ",\n                ".join(
        f"{duckdb_quote_identifier(values_col)} AS {duckdb_quote_identifier(col)}"
        for col, values_col in values_cols.items()
    )
    source_key_select = (
        f"{_qualified(source_alias, KTP_NAMEKEY_COL)} "
        f"AS {duckdb_quote_identifier(KTP_NAMEKEY_COL)}"
    )
    return f"""
        {values_cte_name} AS (
            SELECT
                {source_key_select},
                {values_select}
            FROM {source_view} {source_alias}
            GROUP BY {_qualified(source_alias, KTP_NAMEKEY_COL)}
        ),
        {cte_name} AS (
            SELECT
                {duckdb_quote_identifier(KTP_NAMEKEY_COL)},
                {context_select}
            FROM {values_cte_name}
        )
    """


def _context_joins_sql() -> str:
    xlsx_alias = REVIEW_CONTEXT_ALIASES[REVIEW_DOMAIN_XLSX]
    sciscinet_alias = REVIEW_CONTEXT_ALIASES[REVIEW_DOMAIN_SCISCINET]
    docx_alias = REVIEW_CONTEXT_ALIASES[REVIEW_DOMAIN_DOCX]
    return f"""
            LEFT JOIN {XLSX_CONTEXT_CTE} {xlsx_alias}
              ON {_qualified(xlsx_alias, KTP_NAMEKEY_COL)} =
                 {_qualified('cp', KTP_NAMEKEY_COL)}
            LEFT JOIN {SCISCINET_CONTEXT_CTE} {sciscinet_alias}
              ON {_qualified(sciscinet_alias, KTP_NAMEKEY_COL)} =
                 {_qualified('cp', KTP_NAMEKEY_COL)}
            LEFT JOIN {DOCX_CONTEXT_CTE} {docx_alias}
              ON {_qualified(docx_alias, KTP_NAMEKEY_COL)} =
                 {_qualified('cp', KTP_NAMEKEY_COL)}
    """


def _review_branch_sql(
    *,
    columns: list[str],
    source_view: str,
    source_alias: str,
    source_domain: str,
    domain_columns: dict[str, set[str]],
    partition_value: int,
) -> str:
    select_list = _review_select_list(
        columns,
        primary_alias=source_alias,
        primary_domain=source_domain,
        domain_columns=domain_columns,
    )
    source_key_join = (
        f"{_qualified(source_alias, KTP_NAMEKEY_COL)} = "
        f"{_qualified('cp', KTP_NAMEKEY_COL)}"
    )
    return f"""
            SELECT
                {select_list}
            FROM {CARD_PARTITION_TABLE} cp
            JOIN {source_view} {source_alias}
              ON {source_key_join}
            {_context_joins_sql()}
            WHERE {_qualified('cp', KTP_PARTITION_COL)} = {partition_value}
    """


def _review_placeholder_branch_sql(
    *,
    columns: list[str],
    source_view: str,
    source_alias: str,
    source_domain: str,
    domain_columns: dict[str, set[str]],
    partition_value: int,
) -> str:
    source_key_join = (
        f"{_qualified(source_alias, KTP_NAMEKEY_COL)} = "
        f"{_qualified('cp', KTP_NAMEKEY_COL)}"
    )
    return f"""
            SELECT
                {_review_select_list(
                    columns,
                    primary_alias=None,
                    primary_domain=source_domain,
                    domain_columns=domain_columns,
                )}
            FROM {CARD_PARTITION_TABLE} cp
            {_context_joins_sql()}
            WHERE {_qualified('cp', KTP_PARTITION_COL)} = {partition_value}
              AND NOT EXISTS (
                  SELECT 1
                  FROM {source_view} {source_alias}
                  WHERE {source_key_join}
              )
    """


def _review_context_only_branch_sql(
    *,
    columns: list[str],
    domain_columns: dict[str, set[str]],
    partition_value: int,
) -> str:
    return f"""
            SELECT
                {_review_select_list(
                    columns,
                    primary_alias=None,
                    primary_domain=REVIEW_DOMAIN_XLSX,
                    domain_columns=domain_columns,
                )}
            FROM {CARD_PARTITION_TABLE} cp
            {_context_joins_sql()}
            WHERE {_qualified('cp', KTP_PARTITION_COL)} = {partition_value}
    """


def _create_partition_review_view(conn: duckdb.DuckDBPyConnection) -> list[str]:
    xlsx_columns = set(_relation_columns(conn, XLSX_OUTPUT_VIEW))
    sciscinet_columns = set(_relation_columns(conn, PARQUET_OUTPUT_VIEW))
    docx_column_list = _relation_columns(conn, DOCX_OUTPUT_VIEW)
    docx_columns = set(docx_column_list)
    _materialize_partition_review_source_table(
        conn,
        source_view=XLSX_OUTPUT_VIEW,
        table_name=XLSX_REVIEW_SOURCE_TABLE,
    )
    _materialize_partition_review_source_table(
        conn,
        source_view=PARQUET_OUTPUT_VIEW,
        table_name=SCISCINET_REVIEW_SOURCE_TABLE,
    )
    _materialize_partition_review_source_table(
        conn,
        source_view=DOCX_OUTPUT_VIEW,
        table_name=DOCX_REVIEW_SOURCE_TABLE,
    )
    domain_columns = {
        REVIEW_DOMAIN_XLSX: xlsx_columns,
        REVIEW_DOMAIN_SCISCINET: sciscinet_columns,
        REVIEW_DOMAIN_DOCX: docx_columns,
    }
    columns = _review_columns(docx_column_list)
    branches = [
        _review_branch_sql(
            columns=columns,
            source_view=XLSX_REVIEW_SOURCE_TABLE,
            source_alias="x",
            source_domain=REVIEW_DOMAIN_XLSX,
            domain_columns=domain_columns,
            partition_value=KTP_PARTITION_XLSX_VALUE,
        ),
        _review_placeholder_branch_sql(
            columns=columns,
            source_view=XLSX_REVIEW_SOURCE_TABLE,
            source_alias="x",
            source_domain=REVIEW_DOMAIN_XLSX,
            domain_columns=domain_columns,
            partition_value=KTP_PARTITION_XLSX_VALUE,
        ),
        _review_branch_sql(
            columns=columns,
            source_view=SCISCINET_REVIEW_SOURCE_TABLE,
            source_alias="s",
            source_domain=REVIEW_DOMAIN_SCISCINET,
            domain_columns=domain_columns,
            partition_value=KTP_PARTITION_SSN_VALUE,
        ),
        _review_placeholder_branch_sql(
            columns=columns,
            source_view=SCISCINET_REVIEW_SOURCE_TABLE,
            source_alias="s",
            source_domain=REVIEW_DOMAIN_SCISCINET,
            domain_columns=domain_columns,
            partition_value=KTP_PARTITION_SSN_VALUE,
        ),
        _review_branch_sql(
            columns=columns,
            source_view=DOCX_REVIEW_SOURCE_TABLE,
            source_alias="d",
            source_domain=REVIEW_DOMAIN_DOCX,
            domain_columns=domain_columns,
            partition_value=KTP_PARTITION_DOCX_VALUE,
        ),
        _review_placeholder_branch_sql(
            columns=columns,
            source_view=DOCX_REVIEW_SOURCE_TABLE,
            source_alias="d",
            source_domain=REVIEW_DOMAIN_DOCX,
            domain_columns=domain_columns,
            partition_value=KTP_PARTITION_DOCX_VALUE,
        ),
        _review_context_only_branch_sql(
            columns=columns,
            domain_columns=domain_columns,
            partition_value=KTP_PARTITION_NO_RESOLUTION_VALUE,
        ),
    ]
    union_sql = "\n            UNION ALL\n".join(branches)
    select_columns = ",\n            ".join(duckdb_quote_identifier(col) for col in columns)
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {CARD_PARTITION_REVIEW_ROWS_TABLE} AS
        WITH
        {_review_context_cte_sql(
            cte_name=XLSX_CONTEXT_CTE,
            source_view=XLSX_REVIEW_SOURCE_TABLE,
            source_alias='x_context_source',
            source_domain=REVIEW_DOMAIN_XLSX,
            source_columns=xlsx_columns,
            review_columns=columns,
        )},
        {_review_context_cte_sql(
            cte_name=SCISCINET_CONTEXT_CTE,
            source_view=SCISCINET_REVIEW_SOURCE_TABLE,
            source_alias='s_context_source',
            source_domain=REVIEW_DOMAIN_SCISCINET,
            source_columns=sciscinet_columns,
            review_columns=columns,
        )},
        {_review_context_cte_sql(
            cte_name=DOCX_CONTEXT_CTE,
            source_view=DOCX_REVIEW_SOURCE_TABLE,
            source_alias='d_context_source',
            source_domain=REVIEW_DOMAIN_DOCX,
            source_columns=docx_columns,
            review_columns=columns,
        )},
        base AS (
            {union_sql}
        ),
        {draw_sort_ctes_sql(draw_col=DRAW_LABEL, source_key_col=KTP_NAMEKEY_COL)}
        SELECT *
        FROM ranked
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {CARD_PARTITION_REVIEW_VIEW} AS
        SELECT
            {select_columns}
        FROM {CARD_PARTITION_REVIEW_ROWS_TABLE}
        ORDER BY
            CASE "{KTP_PARTITION_COL}"
                WHEN {KTP_PARTITION_XLSX_VALUE} THEN 0
                WHEN {KTP_PARTITION_SSN_VALUE} THEN 1
                WHEN {KTP_PARTITION_DOCX_VALUE} THEN 2
                ELSE 3
            END,
            CASE
                WHEN "{KTP_PARTITION_COL}" = {KTP_PARTITION_SSN_VALUE}
                    THEN "{KTP_PARTITION_FLAG_SSN_COUNT_COL}"
                ELSE 0
            END,
            CASE
                WHEN "{KTP_PARTITION_COL}" = {KTP_PARTITION_SSN_VALUE}
                 AND "{KTP_PARTITION_FLAG_XLSX_ANY_COL}"
                 AND NOT "{KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL}"
                    THEN 0
                WHEN "{KTP_PARTITION_COL}" = {KTP_PARTITION_SSN_VALUE}
                    THEN 1
                ELSE 0
            END,
            {draw_sort_order_by_sql(
                source_key_col=KTP_NAMEKEY_COL,
                filename_col=KTP_FILENAME_COL,
                fragment_col=KTP_FRAGMENT_COL,
            )}
        """
    )
    _drop_partition_review_source_tables(conn)
    return columns


def _build_selected_outer_dict(
    selected_items: list[tuple[NameKey, tuple[InnerDict, ...]]]
) -> OuterDict:
    subset_outer = OuterDict.from_name_keys([name_key for name_key, _ in selected_items])
    for name_key, inner_dicts in selected_items:
        for inner in inner_dicts:
            subset_outer.add_inner(name_key, inner)
    return subset_outer


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    outer_dict = context.outer_dict
    subset_mode = int(getattr(context.config, "card_subset_mode", 0))
    if subset_mode not in CARD_BUILD_SUBSET_DESCRIPTIONS:
        raise ValueError(
            f"Unsupported card_subset_mode={subset_mode}. Supported: "
            f"{sorted(CARD_BUILD_SUBSET_DESCRIPTIONS.keys())}"
        )
    subset_mode_desc = CARD_BUILD_SUBSET_DESCRIPTIONS[subset_mode]

    def log(msg: str) -> None:
        if context.log:
            context.log(msg, "cyan")

    def progress_bar(done: int, total: int, width: int = 24) -> str:
        if total <= 0:
            return "[" + ("-" * width) + "]"
        filled = min(width, int(width * done / total))
        return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

    def hcr_bundle_name() -> str:
        hcr_paths = [
            Path(meta["path"])
            for key, meta in context.config.files_config.items()
            if key.startswith(HCR_XLSX_KEY_PREFIX) and "path" in meta
        ]
        if not hcr_paths:
            return "hcr_xlsx_inputs"
        parent_names = {path.parent.name for path in hcr_paths}
        if len(parent_names) == 1:
            return next(iter(parent_names))
        return "hcr_xlsx_inputs"

    def on_build_progress(done: int, total: int, _card_id: str) -> None:
        log(f"Card build progress {progress_bar(done, total)} {done}/{total}")

    def on_conversion_progress(done: int, total: int, _card_id: str) -> None:
        phase = "DOCX conversion" if context.config.output_format == "docx" else "Output write"
        log(f"{phase} progress {progress_bar(done, total)} {done}/{total}")

    sciscinet_filenames, docx_filenames = _resource_filename_sets(context)
    subset_mode_items, state_by_source_key, stats = _subset_items_and_states(
        outer_dict,
        sciscinet_filenames=sciscinet_filenames,
        docx_filenames=docx_filenames,
    )
    subset_items = subset_mode_items[subset_mode]
    total = stats["total"]
    mode_header = f"Card subset mode {subset_mode}: {subset_mode_desc}"
    table_header = f"{'Rule':<44} {'Pass':>6} {'Fail':>6}"
    table_sep = "-" * len(table_header)

    def row(label: str, passed: int, failed: int) -> str:
        return f"{label:<44} {passed:>6} {failed:>6}"

    table_lines = [
        mode_header,
        table_header,
        table_sep,
        row(
            "sciscinet: exactly one innerdict",
            stats["sciscinet_count_pass"],
            stats["sciscinet_count_failures"],
        ),
        row(
            "xlsx: all present ktp.xlsx_match exact",
            stats["xlsx_match_pass"],
            stats["xlsx_match_failed"],
        ),
        row(
            "docx: required ktp.table_1_* non-empty",
            stats["docx_table_fields_pass"],
            stats["docx_table_fields_failed"],
        ),
        table_sep,
        row("mode_1", len(subset_mode_items[1]), total - len(subset_mode_items[1])),
        row("mode_2", len(subset_mode_items[2]), total - len(subset_mode_items[2])),
        row("mode_3", len(subset_mode_items[3]), total - len(subset_mode_items[3])),
        row("mode_4", len(subset_mode_items[4]), total - len(subset_mode_items[4])),
        row("selected for current mode", len(subset_items), total - len(subset_items)),
        f"mode_1 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[1]}",
        f"mode_2 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[2]}",
        f"mode_3 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[3]}",
        f"mode_4 description: {CARD_BUILD_SUBSET_DESCRIPTIONS[4]}",
    ]
    log("\n".join(table_lines))

    artifacts: dict[str, Any] = {}
    messages: list[str] = []
    diagnostics: list[str] = []
    if subset_mode in CARD_PARTITION_ARTIFACT_MODES:
        partition_df = _partition_rows_df(
            subset_items,
            state_by_source_key=state_by_source_key,
            subset_mode=subset_mode,
        )
        _materialize_partition_table(context.conn, partition_df)
        _create_partition_review_view(context.conn)
        review_df = context.conn.execute(f"SELECT * FROM {CARD_PARTITION_REVIEW_VIEW}").df()
        artifacts["card_partitions_df"] = partition_df
        artifacts["card_partition_review_df"] = review_df
        messages.append(f"Card partition rows: {len(partition_df)}")
        messages.append(f"Card partition review rows: {len(review_df)}")
        diagnostics.append(f"Card partition rows: {len(partition_df)}")
        diagnostics.append(f"Card partition review rows: {len(review_df)}")

    excluded_cols = {
        KTP_FILENAME_COL,
        KTP_NAMEKEY_COL,
        CSV_ROW_INDEX_COL,
        DOCX_TABLE_INDEX_COL,
        DOCX_ROW_INDEX_COL,
        DOCX_FRAGMENT_COL,
    }

    selected_outer_dict = _build_selected_outer_dict(subset_items)
    intro_date = datetime.now(ZoneInfo(context.config.timezone)).strftime("%B %d, %Y")
    subset_intro_note = f"Subset applied: mode {subset_mode} ({subset_mode_desc})."
    intro = f"{CARD_INTRODUCTION.format(intro_date)}\n{subset_intro_note}"
    log("Building cards from selected subset")
    cards = build_cards(
        selected_outer_dict,
        total_draws=context.config.total_draws,
        intro=intro,
        excluded_cols=excluded_cols,
        progress_callback=on_build_progress,
    )
    zip_path = write_cards_zip(
        cards,
        context.config.output_dir,
        f"{hcr_bundle_name()}_combined_cards.zip",
        output_format=context.config.output_format,
        reference_docx=context.config.pandoc_reference_docx,
        docx_workers=max(1, min(8, os.cpu_count() or 1)),
        progress_callback=on_conversion_progress,
    )

    artifacts.update({"cards": cards, "zip_path": zip_path})
    messages.extend([f"Cards generated: {len(cards)}", f"Output zip: {zip_path}"])
    diagnostics.extend([f"Cards: {len(cards)}", f"Output: {zip_path}"])
    return StepResult(
        step_id=STEP_BUILD_CARDS,
        artifacts=artifacts,
        messages=messages,
        diagnostics=diagnostics,
    )
