from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from src.helpers.resources import (
    RegisteredResource,
)

from .ai_augment_config import AiAugmentDetourConfig
from .source_population import (
    SourcePopulationRow,
)


@dataclass(frozen=True)
class AiAugmentBackendContext:
    pipeline: AiAugmentDetourConfig
    detour_db_path: Path
    replay_log: RegisteredResource
    rollout_cas_dir: Path
    namekey: str | None = None
    release_map: RegisteredResource | None = None
    source_population: tuple[SourcePopulationRow, ...] = ()
    eligible_cohorts: Mapping[str, str] | None = None
