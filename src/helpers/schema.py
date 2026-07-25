from __future__ import annotations

import re

POPULATION_TABLE = "population"
POPULATION_NAMES_TABLE = "population_names"
POPULATION_NAMES_VIEW = "population_with_names"
POPULATION_ECON_TABLE = "population_economy"
POPULATION_ECON_VIEW = "population_with_names_economy"

SAMPLES_TABLE = "samples"
SAMPLES_VIEW = "samples_with_context"
SAMPLES_WITH_NAMES_VIEW = "samples_with_names"

OUTERDICT_STUB_TABLE = "outerdict_stub"
OUTERDICT_NAME_VIEW = "outerdict_name_keys"
OUTERDICT_EXCLUDED_STUB_TABLE = "outerdict_stub_excluded"
OUTERDICT_EXCLUDED_NAME_VIEW = "outerdict_name_keys_excluded"
REGISTERED_RESOURCES_TABLE = "registered_resources"

XLSX_MATCH_VIEW = "xlsx_matches"
XLSX_INNERDICT_TABLE = "xlsx_innerdicts"
XLSX_OUTPUT_VIEW = "xlsx_output"

DOCX_TABLE = "docx_rows"
DOCX_MATCH_VIEW = "docx_matches"
DOCX_INNERDICT_TABLE = "docx_innerdicts"
DOCX_OUTPUT_VIEW = "docx_output"

PARQUET_AUTHOR_MATCH_TABLE = "ssn_author_matches"
PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW = "ssn_author_matches_nonzero_hit"
PARQUET_AUTHOR_MATCH_HIT_CANDIDATE_TABLE = "ssn_author_match_hit_candidates"
PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW = "ssn_author_matches_hit_selected"
PARQUET_AUTHOR_MATCH_HIT_SELECTED_PRE_OPENALEX_TABLE = (
    "ssn_author_matches_hit_selected_pre_openalex"
)
PARQUET_AUTHOR_MATCH_OPENALEX_CHECK_TABLE = "ssn_author_match_openalex_checks"
PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW = "ssn_author_match_hit_selected_author_ids"
PARQUET_AUTHOR_PAPERS_TABLE = "ssn_author_papers"
PARQUET_ALL_HITS_TABLE = "ssn_all_hits"
PARQUET_AUTHOR_HIT_AGG_TABLE = "ssn_author_hit_agg"
PARQUET_AUTHOR_AGG_TABLE = "ssn_author_agg"
PARQUET_INNERDICT_TABLE = "ssn_innerdicts"
PARQUET_LEGACY_ROWS_INNERDICT_TABLE = "ssn_legacy_rows_innerdicts"
PARQUET_AUTHOR_OUTPUT_TABLE = "ssn_author_output"
PARQUET_OUTPUT_VIEW = "ssn_parquet_output"

INNERDICT_NAME_KEY_COL = "name_key"
INNERDICT_JSONLINES_COL = "innerdicts"
INNERDICT_TABLE_SCHEMA: tuple[tuple[str, str], ...] = (
    (INNERDICT_NAME_KEY_COL, "VARCHAR"),
    (INNERDICT_JSONLINES_COL, "VARCHAR"),
)
INNERDICT_SOURCE_RELATIONS: dict[str, str] = {
    XLSX_INNERDICT_TABLE: XLSX_MATCH_VIEW,
    DOCX_INNERDICT_TABLE: DOCX_MATCH_VIEW,
    PARQUET_INNERDICT_TABLE: PARQUET_LEGACY_ROWS_INNERDICT_TABLE,
}

CARD_PARTITION_TABLE = "card_partitions"
CARD_PARTITION_REVIEW_VIEW = "card_partition_review"


def safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", value)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower() or "unnamed"
