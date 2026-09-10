from __future__ import annotations

import os
from functools import cached_property
from pathlib import PurePosixPath
from typing import Final

import yaml
from pydantic import ValidationError, computed_field

from src.detours.detour_ai_augment.protected.src.architecture import (
    ControlCentreComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    EXPORT_OPENALEX_API_KEY,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.data_models.lima import (  # noqa: E501
    LimaConfiguration,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.vars import (
    LIMA_CONFIG_PATH,
    TEXT_ENCODING,
)
from src.helpers.architecture import implements

from .....backend.api import (
    APPENDWATCH_REPORT_ENV_NAME,
    FORBIDDEN_NORMALIZED_PATH_PARTS,
)
from .....backend.helpers.data_models.ai_augment_context import (
    AiAugmentBackendContext,
)

LIMA_APPENDWATCH_REPORT_PARAM: Final = APPENDWATCH_REPORT_ENV_NAME


@implements[ControlCentreComponent.ContextProperty]()
class AiAugmentControlCentreContext(AiAugmentBackendContext):
    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @cached_property
    def openalex_api_key(self) -> str:
        value = os.environ.get(EXPORT_OPENALEX_API_KEY, "").strip()
        if not value:
            raise RuntimeError(Locale.OPENALEX_API_KEY_MISSING)
        return value

    @computed_field  # type: ignore[prop-decorator]
    @cached_property
    def lima_configuration(self) -> LimaConfiguration:
        try:
            if LIMA_CONFIG_PATH.is_symlink() or not LIMA_CONFIG_PATH.is_file():
                raise OSError(Locale.LIMA_CONFIG_UNREADABLE)
            value = yaml.safe_load(LIMA_CONFIG_PATH.read_text(encoding=TEXT_ENCODING))
            configuration = LimaConfiguration.model_validate(value)
            report_value = configuration.param[LIMA_APPENDWATCH_REPORT_PARAM]
            report_path = PurePosixPath(report_value)
            if (
                not report_path.is_absolute()
                or str(report_path) != report_value
                or any(
                    part in FORBIDDEN_NORMALIZED_PATH_PARTS
                    for part in report_path.parts
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
        return configuration
