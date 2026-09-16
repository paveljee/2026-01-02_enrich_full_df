from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from functools import cached_property
from types import MappingProxyType
from typing import Self
from uuid import UUID

from pydantic import model_validator

from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import AiAugmentCohort
from src.detours.detour_ai_augment.protected.src.control_centre.dashboard.helpers.locale import (
    Locale,
)
from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models import InnerDict, NameKey

from .....backend.helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
)
from .....backend.helpers.data_models.commit_event import BackendLifecycle
from .....backend.helpers.data_models.committed_innerdict import CommittedInnerDict
from .....backend.helpers.data_models.query_response import AgentRuntimeAttemptRecord, QueryResponse
from .....backend.helpers.data_models.run_outcome_response import RunOutcomeResponse
from .run_outcome import NAME_KEY_HEADER, name_key_from_header_value


class DashboardQuerySnapshot(FrozenStrictModel):
    """One complete query response; the Dashboard never mutates its nested models."""

    query_response: QueryResponse

    @property
    def ai_augment_singular_outerdicts(self) -> tuple[AiAugmentSingularOuterDict, ...]:
        return self.query_response.ai_augment_singular_outerdicts

    @cached_property
    def researchers_by_namekey(self) -> Mapping[str, AiAugmentSingularOuterDict]:
        return MappingProxyType({
            researcher.namekey.to_json_key(): researcher
            for researcher in self.ai_augment_singular_outerdicts
        })

    @cached_property
    def committed_by_id(self) -> Mapping[UUID, CommittedInnerDict]:
        return MappingProxyType({
            committed.commit_record.record_id: committed
            for researcher in self.ai_augment_singular_outerdicts
            for committed in researcher.committed_innerdicts
        })

    @cached_property
    def attempts_by_namekey(self) -> Mapping[str, tuple[AgentRuntimeAttemptRecord, ...]]:
        grouped: dict[str, list[AgentRuntimeAttemptRecord]] = defaultdict(list)
        for record in self.query_response.attempts:
            namekey = name_key_from_header_value(
                record.attempt.commit_record.request_headers.get(NAME_KEY_HEADER)
            )
            grouped[namekey.to_json_key()].append(record)
        return MappingProxyType({key: tuple(records) for key, records in grouped.items()})

    @cached_property
    def outcomes_by_session(self) -> Mapping[tuple[str, UUID], RunOutcomeResponse]:
        return MappingProxyType({
            (run_outcome_record.run_outcome_request.namekey.to_json_key(), session_id):
            run_outcome_record
            for run_outcome_record in self.query_response.run_outcome_records
            if (session_id := (
                run_outcome_record.run_outcome_response_body.codex_session_record.session_id
            )) is not None
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
            committed_count += len(researcher.committed_innerdicts)
        if len(self.committed_by_id) != committed_count:
            raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)

        seen: set[UUID] = set()
        accepted_ids: set[UUID] = set()
        for namekey, records in self.attempts_by_namekey.items():
            if namekey not in self.researchers_by_namekey:
                raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
            for record in records:
                commit = record.attempt.commit_record
                commit_id = commit.record_id
                result = record.attempt.post_commit_validation.result
                accepted = self.committed_by_id.get(commit_id)
                if (
                    commit_id in seen
                    or result not in {
                        BackendLifecycle.ACCEPTED,
                        BackendLifecycle.REJECTED,
                        BackendLifecycle.CONFIGURATION_ERROR,
                    }
                    or (result is BackendLifecycle.ACCEPTED) != (accepted is not None)
                ):
                    raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
                seen.add(commit_id)
                if accepted is not None:
                    session_id = commit.commit_request_body.codex_session_record.session_id
                    if (
                        session_id is None
                        or session_id
                        != (accepted.commit_record.commit_request_body
                            .codex_session_record.session_id)
                        or name_key_from_header_value(
                            accepted.commit_record.request_headers.get(NAME_KEY_HEADER)
                        ).to_json_key() != namekey
                    ):
                        raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
                    accepted_ids.add(commit_id)
        if accepted_ids != set(self.committed_by_id):
            raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
        for run_outcome_record in self.query_response.run_outcome_records:
            namekey = run_outcome_record.run_outcome_request.namekey.to_json_key()
            if namekey not in self.researchers_by_namekey:
                raise ValueError(Locale.ATTEMPT_DATABASE_INCONSISTENT)
        # Build every derived lookup before a snapshot can replace persisted/UI state.
        _ = self.ground_truth_by_namekey, self.outcomes_by_session
        return self

    def attempts_for_session(
        self, namekey: NameKey, session_id: UUID | None,
    ) -> tuple[AgentRuntimeAttemptRecord, ...]:
        if session_id is None:
            return ()
        return tuple(
            record for record in self.attempts_by_namekey.get(namekey.to_json_key(), ())
            if record.attempt.commit_record.commit_request_body.codex_session_record.session_id
            == session_id
        )
