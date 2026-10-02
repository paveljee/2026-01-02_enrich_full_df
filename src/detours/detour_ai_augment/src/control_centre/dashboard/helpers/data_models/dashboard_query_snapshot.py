from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property
from types import MappingProxyType
from typing import Self
from uuid import UUID

from pydantic import model_validator

from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AiAugmentCohort,
)
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models import InnerDict

from .....backend.helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
)
from .query_event import QueryResponseRecord


class DashboardQuerySnapshot(FrozenStrictModel):
    """One complete query response; the Dashboard never mutates its nested models."""

    ai_augment_singular_outerdicts: tuple[AiAugmentSingularOuterDict, ...]

    @classmethod
    def from_serialized_json(cls, value: str | bytes) -> Self:
        return cls(
            ai_augment_singular_outerdicts=(
                QueryResponseRecord.outerdicts_from_response_body(value)
            ),
        )

    @cached_property
    def researchers_by_namekey(self) -> Mapping[str, AiAugmentSingularOuterDict]:
        return MappingProxyType({
            researcher.namekey.to_json_key(): researcher
            for researcher in self.ai_augment_singular_outerdicts
        })

    @cached_property
    def ground_truth_by_namekey(self) -> Mapping[str, InnerDict]:
        result: dict[str, InnerDict] = {}
        for researcher in self.ai_augment_singular_outerdicts:
            if researcher.ai_augment_cohort is AiAugmentCohort.GROUND_TRUTH:
                innerdict = researcher.ground_truth_innerdict()
                if innerdict is None:
                    raise ValueError(Locale.GROUND_TRUTH_MISSING)
                result[researcher.namekey.to_json_key()] = innerdict
        return MappingProxyType(result)

    @model_validator(mode="after")
    def validate_records(self) -> Self:
        if len(self.researchers_by_namekey) != len(self.ai_augment_singular_outerdicts):
            raise ValueError(Locale.NAMEKEYS_NOT_UNIQUE)
        attempt_ids: set[UUID] = set()
        session_ids: set[UUID] = set()
        for researcher in self.ai_augment_singular_outerdicts:
            researcher.validate_ai_augment_singular_outerdict()
            for codex_innerdict in researcher.codex_innerdicts:
                outcome = codex_innerdict.run_outcome_response_record
                attempt = outcome.attempt
                session_id = outcome.run_outcome_request_record.session_id
                if (
                    attempt is None
                    or outcome.run_outcome_request_record.namekey != researcher.namekey
                    or session_id is None
                    or outcome._codex_session_record().session_id != session_id
                    or outcome.run_outcome_request_record.validation_request_record_id
                    != attempt.record_id
                    or attempt.record_id in attempt_ids
                ):
                    raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
                if session_id in session_ids:
                    raise ValueError(Locale.RUN_OUTCOME_SESSION_DUPLICATE)
                attempt_ids.add(attempt.record_id)
                session_ids.add(session_id)
        # Build every derived lookup before a snapshot can replace persisted/UI state.
        _ = self.ground_truth_by_namekey
        return self
