import os
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo
from typing import Final, Mapping

from pydantic import ValidationError
import duckdb
import yaml

from .....backend.api import (
    APPENDWATCH_REPORT_ENV_NAME,
    FORBIDDEN_NORMALIZED_PATH_PARTS,
    derive_source_population,
    eligible_cohorts,
    load_release_batches,
    registered_release_map,
)

from .....backend.helpers.data_models.ai_augment_context import (
    AiAugmentDetourConfig,
)

from .....backend.helpers.data_models.pydantic_to_paste import (
    EXPORT_OPENALEX_API_KEY,
)

from .....backend.helpers.data_models.source_population import (
    SourcePopulationRow,
)

from ..data_models.lima import LimaConfiguration

from ...helpers.locale import Locale

from ..vars import (
    DEFAULT_CONFIG_PATH,
    LIMA_CONFIG_PATH,
    TEXT_ENCODING,
)

LIMA_APPENDWATCH_REPORT_PARAM: Final = APPENDWATCH_REPORT_ENV_NAME


# =============================================================================
# Configuration / database location
# =============================================================================


class AiAugmentCtlCtrContext:
    def __init__(
        self,
        *,
        config_path: Path = DEFAULT_CONFIG_PATH,
    ) -> None:
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
                or any(part in FORBIDDEN_NORMALIZED_PATH_PARTS for part in guest_report.parts)
            ):
                raise ValueError(Locale.LIMA_APPENDWATCH_PATH_INVALID)
            host_reports: list[Path] = []
            for mount in lima_configuration.mounts:
                host_root = Path(mount.location)
                guest_root = PurePosixPath(mount.mount_point)
                if (
                    not host_root.is_absolute()
                    or str(host_root) != mount.location
                    or not guest_root.is_absolute()
                    or str(guest_root) != mount.mount_point
                    or any(
                        part in FORBIDDEN_NORMALIZED_PATH_PARTS
                        for part in guest_root.parts
                    )
                ):
                    raise ValueError(Locale.LIMA_MOUNT_INVALID)
                try:
                    relative_report = guest_report.relative_to(guest_root)
                except ValueError:
                    continue
                host_reports.append(host_root.joinpath(*relative_report.parts))
        except (
            KeyError, OSError, UnicodeError, ValueError, ValidationError, yaml.YAMLError
        ) as exc:
            raise RuntimeError(Locale.LIMA_CONFIG_INVALID) from exc
        if len(host_reports) != 1:
            raise RuntimeError(Locale.LIMA_APPENDWATCH_MOUNT_INVALID)
        appendwatch_report = host_reports[0]
        if (
            appendwatch_report.is_symlink()
            or not appendwatch_report.is_file()
            or not os.access(appendwatch_report, os.R_OK)
        ):
            raise RuntimeError(Locale.LIMA_APPENDWATCH_REPORT_UNREADABLE)
        pipeline_config = AiAugmentDetourConfig.from_json(config_path)
        release_map = registered_release_map(pipeline_config)
        release_batches = load_release_batches(release_map)
        source_connection = duckdb.connect(str(pipeline_config.db_file), read_only=True)
        try:
            source_population = derive_source_population(
                source_connection,
                release_batches,
                sample_seed=pipeline_config.sample_seed,
            )
        finally:
            source_connection.close()
        self._config_path = config_path
        self._pipeline_config = pipeline_config
        self._openalex_api_key = openalex_api_key
        self._appendwatch_report = appendwatch_report
        self._timezone = ZoneInfo(pipeline_config.timezone)
        self._source_population = source_population
        self._eligible_cohorts = eligible_cohorts(source_population)

    @property
    def pipeline_config(self) -> AiAugmentDetourConfig:
        return self._pipeline_config

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def openalex_api_key(self) -> str:
        return self._openalex_api_key

    @property
    def appendwatch_report(self) -> Path:
        return self._appendwatch_report

    @property
    def timezone(self) -> ZoneInfo:
        return self._timezone

    @property
    def source_db_path(self) -> Path:
        return self._pipeline_config.db_file

    @property
    def source_population(self) -> tuple[SourcePopulationRow, ...]:
        return self._source_population

    @property
    def eligible_cohorts(self) -> Mapping[str, str]:
        return self._eligible_cohorts


