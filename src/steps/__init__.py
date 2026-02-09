from __future__ import annotations

from ..helpers.vars import (
    STEP_ADD_ECONOMY_PRIORITY,
    STEP_BUILD_CARDS,
    STEP_BUILD_OUTERDICT,
    STEP_INFER_NAMES,
    STEP_LOAD_XLSX,
    STEP_MATCH_DOCX,
    STEP_MATCH_PARQUET,
    STEP_MATCH_XLSX,
    STEP_REGISTER_RESOURCES,
    STEP_SAMPLE_POPULATION,
)
from .step_01_register_resources import run as run_register_resources
from .step_02_load_xlsx import run as run_load_xlsx
from .step_03_infer_names import run as run_infer_names
from .step_04_add_economy_priority import run as run_add_economy_priority
from .step_05_sampling import run as run_sampling
from .step_06_build_outerdict_stub import run as run_build_outerdict_stub
from .step_07_match_xlsx import run as run_match_xlsx
from .step_08_match_docx import run as run_match_docx
from .step_09_match_parquet import run as run_match_parquet
from .step_10_build_cards import run as run_build_cards

STEP_REGISTRY = {
    STEP_REGISTER_RESOURCES: run_register_resources,
    STEP_LOAD_XLSX: run_load_xlsx,
    STEP_INFER_NAMES: run_infer_names,
    STEP_ADD_ECONOMY_PRIORITY: run_add_economy_priority,
    STEP_SAMPLE_POPULATION: run_sampling,
    STEP_BUILD_OUTERDICT: run_build_outerdict_stub,
    STEP_MATCH_XLSX: run_match_xlsx,
    STEP_MATCH_DOCX: run_match_docx,
    STEP_MATCH_PARQUET: run_match_parquet,
    STEP_BUILD_CARDS: run_build_cards,
}

__all__ = ["STEP_REGISTRY"]
