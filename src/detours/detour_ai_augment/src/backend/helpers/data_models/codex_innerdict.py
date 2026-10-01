from __future__ import annotations

import json
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, Self
from uuid import UUID

from pydantic import (
    model_serializer,
    model_validator,
)

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    CODEX_SESSION_ID_JSON_KEY,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import (
    HttpRequestLogRecord,
    InnerDict,
    NameKey,
)
from src.helpers.vars import (
    KTP_NAMEKEY_COL,
)

from ....control_centre.dashboard.helpers.data_models.run_outcome_event import (
    RunOutcome,
    RunOutcomeResponseRecord,
)
from .commit_request import BackendCommitRequestRecord, CodexRolloutRecord
from .pull_event import PullResponseRecord
from .push_event import PushResponseRecord
from .validation_request import BackendValidationRequestRecord, ValidationRequestBody


class _CodexInnerDictProcedure:
    dataset_id_field = KTP_NAMEKEY_COL


class _CodexInnerDictValidationJson(FrozenStrictModel):
    pull_response_http_record: HttpRequestLogRecord
    push_response_http_record: HttpRequestLogRecord
    commit_request_http_record: HttpRequestLogRecord
    validation_request_http_record: HttpRequestLogRecord
    openalex_ror_records: tuple[HttpRequestLogRecord, ...]

    @classmethod
    def from_validation_request_record(
        cls, validation: BackendValidationRequestRecord,
    ) -> Self:
        body = validation.validation_request_body
        commit = body.commit_request_record
        pull = commit.commit_request_body.pull_response_record
        push = commit.commit_request_body.push_response_record
        return cls(
            pull_response_http_record=pull.http_request_log_record,
            push_response_http_record=push.http_request_log_record,
            commit_request_http_record=commit.http_request_log_record,
            validation_request_http_record=validation.http_request_log_record,
            openalex_ror_records=body.openalex_ror_records,
        )

    def to_validation_request_record(
        self,
        *,
        prior_validation_request_record: BackendValidationRequestRecord | None,
        initial_validation_request_record: BackendValidationRequestRecord | None,
    ) -> BackendValidationRequestRecord:
        pull = PullResponseRecord.from_http_request_log_record(
            http_request_log_record=self.pull_response_http_record,
            validation_request_record=prior_validation_request_record,
        )
        push = PushResponseRecord.from_http_request_log_record(
            http_request_log_record=self.push_response_http_record,
            pull_response_record=pull,
        )
        commit_refs: dict[UUID, PullResponseRecord | PushResponseRecord] = {
            pull.record_id: pull,
            push.record_id: push,
        }
        commit = BackendCommitRequestRecord.from_http_request_log_record(
            self.commit_request_http_record,
            resolve_http_record=commit_refs.__getitem__,
        )

        request_body = self.validation_request_http_record.request_body
        assert request_body is not None
        provider_records = {
            record.record_id: record for record in self.openalex_ror_records
        }
        body = ValidationRequestBody.from_serialized_json(
            request_body,
            commit_request_record=commit,
            initial_validation_request_record=initial_validation_request_record,
            resolve_http_record=provider_records.__getitem__,
        )
        validation = BackendValidationRequestRecord.from_http_request_log_record(
            self.validation_request_http_record,
            validation_request_body=body,
        )
        assert pull.validation_request_record is prior_validation_request_record
        assert push.pull_response_record is pull
        assert commit.commit_request_body.pull_response_record is pull
        assert commit.commit_request_body.push_response_record is push
        assert body.commit_request_record is commit
        assert body.initial_validation_request_record is initial_validation_request_record
        return validation


class _RunOutcomeResponseRecordJson(FrozenStrictModel):
    run_outcome_response_http_record: HttpRequestLogRecord
    validation_requests: tuple[_CodexInnerDictValidationJson, ...]

    @classmethod
    def from_run_outcome_response_record(
        cls, outcome: RunOutcomeResponseRecord,
    ) -> Self:
        validations: list[_CodexInnerDictValidationJson] = []
        validation = outcome.attempt
        while validation is not None:
            validations.append(
                _CodexInnerDictValidationJson.from_validation_request_record(
                    validation
                )
            )
            pull = (
                validation.validation_request_body.commit_request_record
                .commit_request_body.pull_response_record
            )
            validation = pull.validation_request_record
        return cls(
            run_outcome_response_http_record=outcome.http_request_log_record,
            validation_requests=tuple(reversed(validations)),
        )

    def to_run_outcome_response_record(self) -> RunOutcomeResponseRecord:
        prior: BackendValidationRequestRecord | None = None
        initial: BackendValidationRequestRecord | None = None
        for serialized in self.validation_requests:
            validation = serialized.to_validation_request_record(
                prior_validation_request_record=prior,
                initial_validation_request_record=initial,
            )
            if initial is None:
                initial = validation
            prior = validation
        outcome = RunOutcomeResponseRecord.from_http_request_log_record(
            self.run_outcome_response_http_record,
            attempt=prior,
        )
        if outcome._body().validation_record_id != (
            None if prior is None else prior.record_id
        ):
            raise ValueError(Locale.RUN_OUTCOME_ATTEMPT_LINK_INVALID)
        assert outcome.attempt is prior
        return outcome


class _CodexInnerDictJson(FrozenStrictModel):
    innerdict: dict[str, Any]
    run_outcome_response_record_json: _RunOutcomeResponseRecordJson

    @classmethod
    def from_codex_innerdict(cls, value: CodexInnerDict) -> Self:
        return cls(
            innerdict=value.innerdict.data,
            run_outcome_response_record_json=(
                _RunOutcomeResponseRecordJson.from_run_outcome_response_record(
                    value.run_outcome_response_record
                )
            ),
        )


@implements[BackendComponent.CodexInnerDictProperty]()
class CodexInnerDict(FrozenStrictModel):
    innerdict: InnerDict
    run_outcome_response_record: RunOutcomeResponseRecord

    def text(self, column: str) -> str | None:
        value = self.innerdict.data.get(column)
        if value is not None and not isinstance(value, str):
            raise ValueError(Locale.CODEX_INNERDICT_TEXT_INVALID)
        return value

    def _required_text(self, column: str) -> str:
        value = self.text(column)
        if value is None:
            raise ValueError(Locale.CODEX_INNERDICT_REQUIRED_TEXT_MISSING)
        return value

    def validate_codex_innerdict(self) -> Self:
        stored_namekey = NameKey.from_json_key(self._required_text(KTP_NAMEKEY_COL))
        outcome = self.run_outcome_response_record
        if (
            outcome.response_code != HTTPStatus.OK
            or outcome.run_outcome_request_record.run_outcome is not RunOutcome.COMPLETED
            or outcome.run_outcome_request_record.namekey != stored_namekey
        ):
            raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
        session_id = outcome._codex_session_record().session_id
        if session_id is None or session_id != outcome.run_outcome_request_record.session_id:
            raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
        summary = CodexRolloutRecord.parse_summary_json(
            self._required_text(KTP_AI_AUGMENT_SESSION_METADATA_COL)
        )
        if UUID(summary[CODEX_SESSION_ID_JSON_KEY]) != session_id:
            raise ValueError(Locale.INNERDICT_OUTCOME_MISMATCH)
        return self

    @model_validator(mode="after")
    def _validate_codex_innerdict(self) -> Self:
        return self.validate_codex_innerdict()

    @classmethod
    def from_serialized(cls, value: Mapping[str, object]) -> Self:
        serialized = _CodexInnerDictJson.model_validate_json(json.dumps(value))
        return cls(
            innerdict=InnerDict.from_mapping(
                serialized.innerdict,
                _CodexInnerDictProcedure(),
            ),
            run_outcome_response_record=(
                serialized.run_outcome_response_record_json.to_run_outcome_response_record()
            ),
        )

    def serialize(self) -> dict[str, object]:
        return _CodexInnerDictJson.from_codex_innerdict(self).model_dump(
            mode="json"
        )

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()
