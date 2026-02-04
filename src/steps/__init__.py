from __future__ import annotations

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
    "register_resources": run_register_resources,
    "load_xlsx": run_load_xlsx,
    "infer_names": run_infer_names,
    "add_economy_priority": run_add_economy_priority,
    "sample_population": run_sampling,
    "build_outerdict": run_build_outerdict_stub,
    "match_xlsx": run_match_xlsx,
    "match_docx": run_match_docx,
    "match_parquet": run_match_parquet,
    "build_cards": run_build_cards,
}

__all__ = ["STEP_REGISTRY"]
