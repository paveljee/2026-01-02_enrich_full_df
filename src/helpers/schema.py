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

XLSX_MATCH_VIEW = "xlsx_matches"
XLSX_INNERDICT_TABLE = "xlsx_innerdicts"
XLSX_OUTPUT_VIEW = "xlsx_output"

DOCX_TABLE = "docx_rows"
DOCX_MATCH_VIEW = "docx_matches"
DOCX_INNERDICT_TABLE = "docx_innerdicts"
DOCX_OUTPUT_VIEW = "docx_output"

PARQUET_AUTHOR_MATCH_TABLE = "ssn_author_matches"
PARQUET_INNERDICT_TABLE = "ssn_innerdicts"
PARQUET_AUTHOR_OUTPUT_TABLE = "ssn_author_output"


def safe_identifier(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_]+", "_", value)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned.lower() or "unnamed"
