from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from src.helpers.config import PipelineConfig
from src.helpers.data_models import (
    FragmentType,
    RegisteredResource,
    ResourceGroup,
)

from ..locale import Locale
from ..vars import (
    MAP_SUBSET_0_TO_BATCH_KEY,
    REPLAY_LOG_KEY,
    TEXT_ENCODING,
)

DETOUR_ID = "ai-augment"
DETOUR_DB_SUFFIX = ".duckdb"
DETOUR_DB_FILENAME_TEMPLATE = "{stem}__detour_{detour_id}{suffix}"
RESOURCE_PATH_KEY = "path"
RESOURCE_DESCRIPTION_KEY = "desc"
RESOURCE_SHA256_KEY = "sha256"
OPERATOR_CONFIRMATIONS = frozenset({"y", "yes"})


class _AiAugmentRegisteredResource(RegisteredResource):
    """Freeze the initialization-time hash-verification result for supervision."""

    model_config = ConfigDict(frozen=True)


class AiAugmentResources(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    release_map: _AiAugmentRegisteredResource
    replay_log: _AiAugmentRegisteredResource

    @property
    def registered_resources(self) -> tuple[RegisteredResource, ...]:
        return (self.release_map, self.replay_log)


def _detour_db_path(path: Path) -> Path:
    suffix = path.suffix or DETOUR_DB_SUFFIX
    stem = path.stem if path.suffix else path.name
    return path.with_name(
        DETOUR_DB_FILENAME_TEMPLATE.format(
            stem=stem,
            detour_id=DETOUR_ID,
            suffix=suffix,
        )
    )


def _repair_incomplete_replay_log_tail(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            value = stream.read()
        if not value or value.endswith(b"\n"):
            return
        previous_newline = value.rfind(b"\n")
        truncate_at = previous_newline + 1
        discarded_bytes = len(value) - truncate_at
        reply = input(
            Locale.REPLAY_LOG_TAIL_REPAIR_PROMPT_TEMPLATE.format(
                path=path,
                discarded_bytes=discarded_bytes,
            )
        )
        if reply.strip().casefold() not in OPERATOR_CONFIRMATIONS:
            raise ValueError(Locale.REPLAY_LOG_TAIL_REPAIR_DECLINED)
        with path.open("r+b") as stream:
            stream.seek(truncate_at)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except (EOFError, OSError) as exc:
        raise ValueError(Locale.REPLAY_LOG_TAIL_REPAIR_FAILED) from exc


def _registered_resource(
    files_config: Mapping[str, object],
    *,
    resource_key: str,
    fragment_type: FragmentType,
    verify_hash_on_init: bool,
    writable: bool = False,
) -> _AiAugmentRegisteredResource:
    try:
        metadata = files_config[resource_key]
        if not isinstance(metadata, Mapping):
            raise TypeError
        path_value = metadata[RESOURCE_PATH_KEY]
        hash_value = metadata[RESOURCE_SHA256_KEY]
        description_value = metadata[RESOURCE_DESCRIPTION_KEY]
        if not all(
            isinstance(value, str)
            for value in (path_value, hash_value, description_value)
        ):
            raise TypeError
        path = Path(path_value)
        if writable:
            if path.is_symlink() or not path.is_file() or not os.access(
                path,
                os.R_OK | os.W_OK,
            ):
                raise OSError(Locale.REPLAY_LOG_UNREADABLE)
            _repair_incomplete_replay_log_tail(path)
        return _AiAugmentRegisteredResource(
            name=path.name,
            hash=hash_value,
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=fragment_type,
            description=description_value,
            url=path.resolve().as_uri(),
            verify_hash_on_init=verify_hash_on_init,
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise ValueError(
            Locale.CONFIGURED_RESOURCE_INVALID_TEMPLATE.format(
                resource_key=resource_key
            )
        ) from exc


class AiAugmentDetourConfig(PipelineConfig):
    detour_db_path: Path
    rollout_cas_dir: Path
    resources: AiAugmentResources = Field(frozen=True)

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
        if not isinstance(files_config, Mapping) or not isinstance(
            db_file,
            (str, Path),
        ):
            return data
        verify_hash_on_init = True
        if info.context is not None:
            verify_hash_on_init = bool(
                info.context.get("verify_hash_on_init", True)
            )
        data["detour_db_path"] = _detour_db_path(Path(db_file))
        data["resources"] = {
            "release_map": _registered_resource(
                files_config,
                resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
                fragment_type=FragmentType.CSV_ROW,
                verify_hash_on_init=verify_hash_on_init,
            ),
            "replay_log": _registered_resource(
                files_config,
                resource_key=REPLAY_LOG_KEY,
                fragment_type=FragmentType.LINE_NUMBER,
                verify_hash_on_init=verify_hash_on_init,
                writable=True,
            ),
        }
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
