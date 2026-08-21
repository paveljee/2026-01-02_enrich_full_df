from pathlib import Path
from typing import Self

from pydantic import model_validator

from src.helpers.config import PipelineConfig

from ..vars import (
    MAP_SUBSET_0_TO_BATCH_KEY,
    REPLAY_LOG_KEY,
    TEXT_ENCODING,
)


class AiAugmentDetourConfig(PipelineConfig):
    rollout_cas_dir: Path

    @model_validator(mode="after")
    def _validate_ai_augment_files_config(self) -> Self:
        missing_required_keys = sorted(
            {
                MAP_SUBSET_0_TO_BATCH_KEY,
                REPLAY_LOG_KEY,
            }
            - set(self.files_config.keys())
        )
        if missing_required_keys:
            raise ValueError(
                "files_config missing required AI augment keys: "
                + ", ".join(missing_required_keys)
            )

        return self

    @classmethod
    def from_json(cls, path: Path) -> Self:
        return cls.model_validate_json(path.read_text(encoding=TEXT_ENCODING))
