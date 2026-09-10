from __future__ import annotations

import json
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_serializer,
    model_validator,
)

from src.helpers.architecture import implements
from src.helpers.data_models import (
    HttpRequestLogRecord,
    InnerDict,
    NameKey,
    RegisteredResource,
)
from src.helpers.procedures import (
    DocxMatchProcedure,
    ParquetMatchProcedure,
    XlsxMatchProcedure,
)
from src.helpers.vars import DRAW_LABEL, KTP_NAMEKEY_COL

from ....architecture import BackendComponent
from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    name_key_from_header_value,
)
from ..vars import (
    KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
)
from .ai_augment_config import AiAugmentDetourConfig
from .server_event import (
    AgentRuntimeAttempt,
    BackendCommitRecord,
    CodexRolloutRecord,
    CodexSessionRecord,
    CommitRequestBody,
    PostCommitValidation,
    RunOutcomeResponse,
)


class AiAugmentCohort(StrEnum):
    GROUND_TRUTH = "ground_truth"
    NO_GROUND_TRUTH = "no_ground_truth"
    INELIGIBLE = "ineligible"


class AiAugmentIneligibilityCategory(StrEnum):
    EXCLUDED_DUPLICATE_NAMEKEY = "excluded_duplicate_namekey"
    RELEASE_BATCH_SUBSET_8 = "release_batch_subset_8"
    STAGING_PARTITION_2 = "staging_partition_2"
    STAGING_PARTITION_4_XLSX_NON_EXACT = "staging_partition_4_xlsx_non_exact"
    STAGING_PARTITION_4_MULTIPLE_SSN = "staging_partition_4_multiple_ssn"


class AiAugmentBackendContext(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    pipeline: AiAugmentDetourConfig
    detour_db_path: Path
    replay_log: RegisteredResource
    rollout_cas_dir: Path
    configured_namekey: NameKey | None = None
    release_map: RegisteredResource | None = None
    ai_augment_outerdicts: tuple[AiAugmentOuterDict, ...] = ()

    @property
    def configured_ai_augment_outerdict(self) -> AiAugmentOuterDict | None:
        if self.configured_namekey is None:
            return None
        matches = tuple(
            outerdict
            for outerdict in self.ai_augment_outerdicts
            if outerdict.namekey == self.configured_namekey
        )
        if len(matches) != 1:
            raise ValueError("configured AI augment outerdict is missing or duplicated")
        return matches[0]
