from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    model_serializer,
    model_validator,
)

from src.detours.detour_ai_augment.protected.src.architecture import (
    AgentRuntimeComponent,
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    StandardizedSubmission,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_init import (  # noqa: E501
    Submission,
)
from src.helpers.architecture import implements
from src.helpers.data_models import HttpRequestLogRecord, InnerDict, MatchingProcedure

from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    name_key_from_header_value,
)
from .ai_augment_outer_dict import (
    AiAugmentOuterDict,
    _AiAugmentOuterDictJson,
    _BackendCommitRecordJson,
)
from .commit_event import BackendCommitRecord, PostCommitValidation
from .run_outcome_response import RunOutcomeResponse


@implements[AgentRuntimeComponent.AttemptProperty]()
class AgentRuntimeAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pull_record: HttpRequestLogRecord
    commit_record: BackendCommitRecord
    post_commit_validation: PostCommitValidation


class _AgentRuntimeAttemptJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    pull_record: HttpRequestLogRecord
    commit_record: _BackendCommitRecordJson
    post_commit_validation: PostCommitValidation

    @classmethod
    def from_attempt(cls, value: AgentRuntimeAttempt) -> Self:
        return cls(
            pull_record=value.pull_record,
            commit_record=_BackendCommitRecordJson.from_commit_record(
                value.commit_record
            ),
            post_commit_validation=value.post_commit_validation,
        )

    def to_attempt(self) -> AgentRuntimeAttempt:
        return AgentRuntimeAttempt(
            pull_record=self.pull_record,
            commit_record=self.commit_record.to_commit_record(),
            post_commit_validation=self.post_commit_validation,
        )


class _AgentRuntimeAttemptRecordJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attempt: _AgentRuntimeAttemptJson
    submission: Submission | StandardizedSubmission | None
    ground_truth_innerdict: dict[str, Any] | None

    @classmethod
    def from_attempt_record(cls, value: AgentRuntimeAttemptRecord) -> Self:
        return cls(
            attempt=_AgentRuntimeAttemptJson.from_attempt(value.attempt),
            submission=value.submission,
            ground_truth_innerdict=(
                None
                if value.ground_truth_innerdict is None
                else value.ground_truth_innerdict.model_dump(mode="json")
            ),
        )


@implements[BackendComponent.AgentRuntimePort.AttemptRecordProperty]()
class AgentRuntimeAttemptRecord(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    attempt: AgentRuntimeAttempt
    submission: Submission | StandardizedSubmission | None
    ground_truth_innerdict: InnerDict | None

    @model_validator(mode="after")
    def validate_attempt_record(self) -> Self:
        accepted = (
            self.attempt.post_commit_validation.result.value == "accepted"
        )
        if accepted and self.submission is None:
            raise ValueError("accepted attempt submission is missing")
        if not accepted and self.ground_truth_innerdict is not None:
            raise ValueError("rejected attempt cannot contain ground truth")
        return self

    @classmethod
    def from_serialized_json(
        cls,
        value: str | bytes,
        *,
        procedure: MatchingProcedure | None,
    ) -> Self:
        serialized = _AgentRuntimeAttemptRecordJson.model_validate_json(value)
        ground_truth_innerdict = serialized.ground_truth_innerdict
        if ground_truth_innerdict is not None:
            if procedure is None:
                raise ValueError("ground-truth matching procedure is required")
            if set(ground_truth_innerdict) != {"data"}:
                raise ValueError("serialized ground-truth innerdict is invalid")
            data = ground_truth_innerdict["data"]
            if not isinstance(data, Mapping):
                raise ValueError("serialized ground-truth innerdict data is invalid")
            loaded_ground_truth = InnerDict.from_mapping(data, procedure)
        else:
            loaded_ground_truth = None
        return cls(
            attempt=serialized.attempt.to_attempt(),
            submission=serialized.submission,
            ground_truth_innerdict=loaded_ground_truth,
        )

    def serialize(self) -> dict[str, object]:
        return _AgentRuntimeAttemptRecordJson.from_attempt_record(self).model_dump(
            mode="json",
            by_alias=True,
        )

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


class _QueryResponseJson(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attempts: tuple[_AgentRuntimeAttemptRecordJson, ...]
    ai_augment_outerdicts: tuple[_AiAugmentOuterDictJson, ...]
    run_outcome_records: tuple[HttpRequestLogRecord, ...]


@implements[BackendComponent.ControlCentrePort.QueryResponseProperty]()
class QueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    attempts: tuple[AgentRuntimeAttemptRecord, ...]
    ai_augment_outerdicts: tuple[AiAugmentOuterDict, ...]
    run_outcome_records: tuple[RunOutcomeResponse, ...] = ()

    @classmethod
    def from_serialized_json(
        cls,
        value: str | bytes,
    ) -> Self:
        serialized = _QueryResponseJson.model_validate_json(value)
        ai_augment_outerdicts = tuple(
            AiAugmentOuterDict.from_serialized(outerdict.model_dump(mode="json"))
            for outerdict in serialized.ai_augment_outerdicts
        )
        outerdict_by_namekey = {
            outerdict.namekey.to_json_key(): outerdict
            for outerdict in ai_augment_outerdicts
        }
        attempts: list[AgentRuntimeAttemptRecord] = []
        for attempt in serialized.attempts:
            procedure = None
            if attempt.ground_truth_innerdict is not None:
                namekey = name_key_from_header_value(
                    attempt.attempt.commit_record.http_record.request_headers.get(
                        NAME_KEY_HEADER
                    )
                )
                outerdict = outerdict_by_namekey.get(namekey.to_json_key())
                if outerdict is None or not outerdict.docx_innerdicts:
                    raise ValueError(
                        "ground-truth originating DOCX innerdict is missing"
                    )
                procedure = outerdict.docx_innerdicts[0].procedure
            attempts.append(
                AgentRuntimeAttemptRecord.from_serialized_json(
                    attempt.model_dump_json(by_alias=True),
                    procedure=procedure,
                )
            )
        return cls(
            attempts=tuple(attempts),
            ai_augment_outerdicts=ai_augment_outerdicts,
            run_outcome_records=tuple(
                RunOutcomeResponse.from_http_request_log_record(record)
                for record in serialized.run_outcome_records
            ),
        )

    def serialize(self) -> dict[str, object]:
        return _QueryResponseJson(
            attempts=tuple(
                _AgentRuntimeAttemptRecordJson.from_attempt_record(attempt)
                for attempt in self.attempts
            ),
            ai_augment_outerdicts=tuple(
                _AiAugmentOuterDictJson.from_ai_augment_outerdict(outerdict)
                for outerdict in self.ai_augment_outerdicts
            ),
            run_outcome_records=tuple(
                record.http_request_log_record
                for record in self.run_outcome_records
            ),
        ).model_dump(mode="json", by_alias=True)

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()
