from __future__ import annotations

from collections import defaultdict
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
from src.helpers.data_models import InnerDict, NameKey

from .....backend.helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
)
from .....backend.helpers.data_models.codex_innerdict import CodexInnerDict
from .....backend.helpers.data_models.validation_request import BackendValidationRecord
from .query_event import QueryResponseRecord
from .run_outcome_event import RunOutcomeResponseRecord


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
    def committed_by_id(self) -> Mapping[UUID, CodexInnerDict]:
        return MappingProxyType({
            committed.run_outcome_response_record.attempt.validation_request_body
            .commit_request_record.record_id: committed
            for researcher in self.ai_augment_singular_outerdicts
            for committed in researcher.codex_innerdicts
            if committed.run_outcome_response_record.attempt is not None
        })

    @cached_property
    def attempts_by_namekey(self) -> Mapping[str, tuple[BackendValidationRecord, ...]]:
        grouped: dict[str, list[BackendValidationRecord]] = defaultdict(list)
        for researcher in self.ai_augment_singular_outerdicts:
            for committed in researcher.codex_innerdicts:
                attempt = committed.run_outcome_response_record.attempt
                if attempt is not None:
                    grouped[researcher.namekey.to_json_key()].append(attempt)
        return MappingProxyType({key: tuple(records) for key, records in grouped.items()})

    @cached_property
    def outcomes_by_session(self) -> Mapping[tuple[str, UUID], RunOutcomeResponseRecord]:
        return MappingProxyType({
            (
                namekey.to_json_key(),
                session_id,
            ): run_outcome_record
            for researcher in self.ai_augment_singular_outerdicts
            for committed in researcher.codex_innerdicts
            if (run_outcome_record := committed.run_outcome_response_record)
            if (namekey := run_outcome_record.run_outcome_request_record.namekey) is not None
            if (
                session_id := (
                    run_outcome_record._codex_session_record().session_id
                )
            )
            is not None
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
        committed_count = 0
        for researcher in self.ai_augment_singular_outerdicts:
            researcher.validate_ai_augment_singular_outerdict()
            committed_count += len(researcher.codex_innerdicts)
        if len(self.committed_by_id) != committed_count:
            raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)

        for researcher in self.ai_augment_singular_outerdicts:
            for committed in researcher.codex_innerdicts:
                outcome = committed.run_outcome_response_record
                attempt = outcome.attempt
                if (
                    attempt is None
                    or outcome.run_outcome_request_record.namekey != researcher.namekey
                    or outcome._codex_session_record().session_id is None
                    or attempt.validation_request_body.commit_request_record.record_id
                    not in self.committed_by_id
                ):
                    raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
        # Build every derived lookup before a snapshot can replace persisted/UI state.
        _ = self.ground_truth_by_namekey, self.outcomes_by_session
        return self

    def attempts_for_session(
        self, namekey: NameKey, session_id: UUID | None,
    ) -> tuple[BackendValidationRecord, ...]:
        if session_id is None:
            return ()
        return tuple(
            record for record in self.attempts_by_namekey.get(namekey.to_json_key(), ())
            if (
                record.validation_request_body.commit_request_record
                .commit_request_body.codex_session_record.session_id
            )
            == session_id
        )
