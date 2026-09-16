from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal, Self

from pydantic import (
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
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import HttpRequestLogRecord, InnerDict, MatchingProcedure

from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    name_key_from_header_value,
)
from .ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
    _AiAugmentSingularOuterDictJson,
)
from .commit_event import BackendCommitRecord, PostCommitValidation
from .committed_innerdict import _BackendCommitRecordJson
from .model_http_interceptor import ModelHttpInterceptor
from .run_outcome_response import RunOutcomeResponse
from .validation_event import ValidationRequestBody


@implements[AgentRuntimeComponent.AttemptProperty]()
class AgentRuntimeAttempt(FrozenStrictModel):
    pull_record: HttpRequestLogRecord
    commit_record: BackendCommitRecord
    post_commit_validation: PostCommitValidation


class _AgentRuntimeAttemptJson(FrozenStrictModel):
    pull_record: HttpRequestLogRecord
    commit_record: _BackendCommitRecordJson
    post_commit_validation: PostCommitValidation

    @classmethod
    def from_attempt(cls, value: AgentRuntimeAttempt) -> Self:
        return cls(
            pull_record=value.pull_record,
            commit_record=_BackendCommitRecordJson.from_commit_record(value.commit_record),
            post_commit_validation=value.post_commit_validation,
        )

    def to_attempt(self) -> AgentRuntimeAttempt:
        return AgentRuntimeAttempt(
            pull_record=self.pull_record,
            commit_record=self.commit_record.to_commit_record(),
            post_commit_validation=self.post_commit_validation,
        )


class _AgentRuntimeAttemptRecordJson(FrozenStrictModel):
    attempt: _AgentRuntimeAttemptJson
    submission: dict[str, Any] | None
    submission_type: Literal["Submission", "StandardizedSubmission"] | None = None
    http_records: tuple[HttpRequestLogRecord, ...] = ()
    validation_record: HttpRequestLogRecord | None = None
    ground_truth_innerdict: dict[str, Any] | None

    @classmethod
    def from_attempt_record(cls, value: AgentRuntimeAttemptRecord) -> Self:
        return cls(
            attempt=_AgentRuntimeAttemptJson.from_attempt(value.attempt),
            submission=None
            if value.submission is None
            else value.submission.model_dump(
                mode="json",
                by_alias=True,
            ),
            submission_type=None
            if value.submission is None
            else (
                "StandardizedSubmission"
                if isinstance(value.submission, StandardizedSubmission)
                else "Submission"
            ),
            http_records=value.http_records,
            validation_record=value.validation_record,
            ground_truth_innerdict=(
                None
                if value.ground_truth_innerdict is None
                else value.ground_truth_innerdict.model_dump(mode="json")
            ),
        )


@implements[BackendComponent.AgentRuntimePort.AttemptRecordProperty]()
class AgentRuntimeAttemptRecord(FrozenStrictModel):
    attempt: AgentRuntimeAttempt
    submission: Submission | StandardizedSubmission | None
    ground_truth_innerdict: InnerDict | None

    http_records: tuple[HttpRequestLogRecord, ...] = ()
    validation_record: HttpRequestLogRecord | None = None

    @model_validator(mode="after")
    def validate_attempt_record(self) -> Self:
        accepted = self.attempt.post_commit_validation.result.value == "accepted"
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
        submission = None
        if serialized.validation_record is not None:
            body = ValidationRequestBody.model_validate_json(
                serialized.validation_record.request_body or ""
            )
            if (
                body.commit_id != serialized.attempt.commit_record.http_record.record_id
                or body.post_commit_validation != serialized.attempt.post_commit_validation
                or body.submission != serialized.submission
                or body.submission_type != serialized.submission_type
                or body.http_record_ids
                != tuple(record.record_id for record in serialized.http_records)
                or serialized.validation_record.request_headers
                != serialized.attempt.commit_record.http_record.request_headers
            ):
                raise ValueError("Serialized validation inputs do not match the result")
        if serialized.submission is not None:
            submission_type = serialized.submission_type
            if submission_type is None:
                # Older DTOs did not carry a discriminator. No network fallback:
                # a legacy model needing HTTP still requires recorded inputs.
                submission_type = (
                    "StandardizedSubmission"
                    if any(
                        isinstance(value, dict) and "standardized_value" in value
                        for value in serialized.submission.values()
                    )
                    else "Submission"
                )
            model = (
                StandardizedSubmission
                if submission_type == "StandardizedSubmission"
                else Submission
            )
            submission = model.model_validate_with_http_records(
                json.dumps(serialized.submission),
                http=ModelHttpInterceptor.from_records(serialized.http_records),
            )
        return cls(
            attempt=serialized.attempt.to_attempt(),
            submission=submission,
            ground_truth_innerdict=loaded_ground_truth,
            http_records=serialized.http_records,
            validation_record=serialized.validation_record,
        )

    def serialize(self) -> dict[str, object]:
        return _AgentRuntimeAttemptRecordJson.from_attempt_record(self).model_dump(
            mode="json",
            by_alias=True,
        )

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()


class _QueryResponseJson(FrozenStrictModel):
    attempts: tuple[_AgentRuntimeAttemptRecordJson, ...]
    ai_augment_singular_outerdicts: tuple[_AiAugmentSingularOuterDictJson, ...]
    run_outcome_records: tuple[HttpRequestLogRecord, ...]


@implements[BackendComponent.ControlCentrePort.QueryResponseProperty]()
class QueryResponse(FrozenStrictModel):
    attempts: tuple[AgentRuntimeAttemptRecord, ...]
    ai_augment_singular_outerdicts: tuple[AiAugmentSingularOuterDict, ...]
    run_outcome_records: tuple[RunOutcomeResponse, ...] = ()

    @classmethod
    def from_serialized_json(
        cls,
        value: str | bytes,
    ) -> Self:
        serialized = _QueryResponseJson.model_validate_json(value)
        ai_augment_singular_outerdicts = tuple(
            AiAugmentSingularOuterDict.from_serialized(singular_outerdict.model_dump(mode="json"))
            for singular_outerdict in serialized.ai_augment_singular_outerdicts
        )
        singular_outerdict_by_namekey = {
            singular_outerdict.namekey.to_json_key(): singular_outerdict
            for singular_outerdict in ai_augment_singular_outerdicts
        }
        attempts: list[AgentRuntimeAttemptRecord] = []
        for attempt in serialized.attempts:
            procedure = None
            if attempt.ground_truth_innerdict is not None:
                namekey = name_key_from_header_value(
                    attempt.attempt.commit_record.http_record.request_headers.get(NAME_KEY_HEADER)
                )
                singular_outerdict = singular_outerdict_by_namekey.get(namekey.to_json_key())
                if singular_outerdict is None or not singular_outerdict.docx_innerdicts:
                    raise ValueError("ground-truth originating DOCX innerdict is missing")
                procedure = singular_outerdict.docx_innerdicts[0].procedure
            attempts.append(
                AgentRuntimeAttemptRecord.from_serialized_json(
                    attempt.model_dump_json(by_alias=True),
                    procedure=procedure,
                )
            )
        return cls(
            attempts=tuple(attempts),
            ai_augment_singular_outerdicts=ai_augment_singular_outerdicts,
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
            ai_augment_singular_outerdicts=tuple(
                _AiAugmentSingularOuterDictJson.from_ai_augment_singular_outerdict(
                    singular_outerdict
                )
                for singular_outerdict in self.ai_augment_singular_outerdicts
            ),
            run_outcome_records=tuple(
                record.http_request_log_record for record in self.run_outcome_records
            ),
        ).model_dump(mode="json", by_alias=True)

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()
