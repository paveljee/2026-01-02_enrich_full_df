from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Self

from pydantic import Field, ValidationInfo, model_validator

from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_cas import (  # noqa: E501
    AiAugmentCAS,
)
from src.helpers.architecture import FrozenStrictModel
from src.helpers.config import PipelineConfig
from src.helpers.data_models import (
    FragmentType,
    RegisteredResource,
)

from ..vars import (
    MAP_SUBSET_0_TO_BATCH_KEY,
    REPLAY_LOG_KEY,
    TEXT_ENCODING,
)
from .ai_augment_detour_db import AiAugmentDetourDB
from .ai_augment_registered_resource import AiAugmentRegisteredResource
from .replay_log import ReplayLogRegisteredResource


class AiAugmentDetourConfig(PipelineConfig, FrozenStrictModel):
    release_map: AiAugmentRegisteredResource = Field(frozen=True)
    replay_log: ReplayLogRegisteredResource = Field(frozen=True)
    backend_store: AiAugmentBackendStore
    rollout_cas: AiAugmentCAS = Field(alias="rollout_cas_dir", frozen=True)

    @property
    def registered_resources(self) -> tuple[RegisteredResource, ...]:
        return self.release_map, self.replay_log

    @model_validator(mode="before")
    @classmethod
    def _derive_ai_augment_configuration(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        files_config = data.get("files_config")
        db_file = data.get("db_file")
        rollout_cas_dir = data.get("rollout_cas_dir")
        if not isinstance(files_config, Mapping) or not isinstance(
            db_file,
            (str, Path),
        ) or not isinstance(
            rollout_cas_dir,
            (str, Path),
        ):
            return data
        duckdb_extensions = data.get("duckdb_extensions", {})
        if not isinstance(duckdb_extensions, Mapping):
            return data
        verify_hash_on_init = True
        if info.context is not None:
            verify_hash_on_init = bool(
                info.context.get("verify_hash_on_init", True)
            )
        release_map = AiAugmentRegisteredResource.from_config_entry(
            files_config.get(MAP_SUBSET_0_TO_BATCH_KEY),
            resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
            fragment_type=FragmentType.CSV_ROW,
            verify_hash_on_init=verify_hash_on_init,
        )
        replay_log = ReplayLogRegisteredResource.from_config_entry(
            files_config.get(REPLAY_LOG_KEY),
            resource_key=REPLAY_LOG_KEY,
            verify_hash_on_init=verify_hash_on_init,
        )
        detour_db = AiAugmentDetourDB.from_pipeline_db(
            Path(db_file),
            duckdb_extensions=duckdb_extensions,
        )
        rollout_cas = AiAugmentCAS(path=Path(rollout_cas_dir))
        data["release_map"] = release_map
        data["replay_log"] = replay_log
        data["rollout_cas_dir"] = rollout_cas
        data["backend_store"] = AiAugmentBackendStore.from_resources(
            replay_log=replay_log,
            detour_db=detour_db,
            rollout_cas=rollout_cas,
        )
        return data

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
    def from_json(
        cls,
        path: Path,
        *,
        verify_hash_on_init: bool = True,
    ) -> Self:
        return cls.model_validate_json(
            path.read_text(encoding=TEXT_ENCODING),
            context={"verify_hash_on_init": verify_hash_on_init},
        )
