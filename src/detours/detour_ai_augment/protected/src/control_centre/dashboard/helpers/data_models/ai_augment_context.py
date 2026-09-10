from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Final, Self

import duckdb
import yaml
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from .....backend.api import (
    APPENDWATCH_REPORT_ENV_NAME,
    FORBIDDEN_NORMALIZED_PATH_PARTS,
    derive_ai_augment_outerdicts,
    load_release_batches,
    registered_release_map,
)
from .....backend.helpers.data_models.ai_augment_config import (
    AiAugmentDetourConfig,
)
from .....backend.helpers.data_models.ai_augment_context import (
    AiAugmentOuterDict,
)
from .....backend.helpers.data_models.pydantic_to_paste import (
    EXPORT_OPENALEX_API_KEY,
)
from ...helpers.locale import Locale
from ..data_models.lima import LimaConfiguration
from ..vars import (
    DEFAULT_CONFIG_PATH,
    LIMA_CONFIG_PATH,
    TEXT_ENCODING,
)

LIMA_APPENDWATCH_REPORT_PARAM: Final = APPENDWATCH_REPORT_ENV_NAME


class AiAugmentControlCentreContext(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    pipeline_config: AiAugmentDetourConfig
    openalex_api_key: StrictStr
    appendwatch_report: PurePosixPath
    ai_augment_outerdicts: tuple[AiAugmentOuterDict, ...]

    @classmethod
    def load(
        cls,
        *,
        ai_augment_outerdicts: tuple[AiAugmentOuterDict, ...] | None = None,
    ) -> Self:
        openalex_api_key = os.environ.get(EXPORT_OPENALEX_API_KEY, "").strip()
        if not openalex_api_key:
            raise RuntimeError(Locale.OPENALEX_API_KEY_MISSING)
        try:
            if LIMA_CONFIG_PATH.is_symlink() or not LIMA_CONFIG_PATH.is_file():
                raise OSError(Locale.LIMA_CONFIG_UNREADABLE)
            lima_value = yaml.safe_load(LIMA_CONFIG_PATH.read_text(encoding=TEXT_ENCODING))
            lima_configuration = LimaConfiguration.model_validate(lima_value)
            guest_report_value = lima_configuration.param[LIMA_APPENDWATCH_REPORT_PARAM]
            guest_report = PurePosixPath(guest_report_value)
            if (
                not guest_report.is_absolute()
                or str(guest_report) != guest_report_value
                or any(
                    part in FORBIDDEN_NORMALIZED_PATH_PARTS
                    for part in guest_report.parts
                )
            ):
                raise ValueError(Locale.LIMA_APPENDWATCH_PATH_INVALID)
        except (
            KeyError,
            OSError,
            UnicodeError,
            ValueError,
            ValidationError,
            yaml.YAMLError,
        ) as exc:
            raise RuntimeError(Locale.LIMA_CONFIG_INVALID) from exc
        pipeline_config = AiAugmentDetourConfig.from_json(config_path)
        if ai_augment_outerdicts is None:
            release_batches = load_release_batches(
                registered_release_map(pipeline_config)
            )
            source_connection = duckdb.connect(
                str(pipeline_config.db_file),
                read_only=True,
            )
            try:
                ai_augment_outerdicts = derive_ai_augment_outerdicts(
                    source_connection,
                    release_batches,
                    sample_seed=pipeline_config.sample_seed,
                )
            finally:
                source_connection.close()
        return cls(
            pipeline_config=pipeline_config,
            openalex_api_key=openalex_api_key,
            appendwatch_report=guest_report,
            ai_augment_outerdicts=ai_augment_outerdicts,
        )

    @property
    def source_db_path(self) -> Path:
        return self.pipeline_config.db_file
