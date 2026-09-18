"""Also see any classes implemented under `data_models`"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import (
    Literal,
    NoReturn,
    Protocol,
    Self,
)
from uuid import UUID

from pydantic import JsonValue

from src.helpers.config import PipelineConfig
from src.helpers.data_models import (
    HttpRequestLogRecord,
    InnerDict,
    MatchingProcedure,
    NameKey,
)
from src.helpers.data_models.http_request_log import HttpRequestLogRecordProtocol

from .acme_protocol import ComponentProtocol
from .backend.helpers.data_models.pydantic_to_paste import StandardizedSubmission
from .backend.helpers.data_models.submission_init import Submission
from .backend.helpers.vars import (
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from .control_centre.dashboard.helpers.data_models.lima import LimaConfiguration


class BackendComponent(
    ComponentProtocol,
    Protocol,
):
    class RequestRecordProperty(
        HttpRequestLogRecordProtocol, ComponentProtocol.PropertyProtocol, Protocol
    ):
        pass

    class ResponseRecordProperty(
        HttpRequestLogRecordProtocol, ComponentProtocol.PropertyProtocol, Protocol
    ):
        pass

    class StoreExceptionProperty(ComponentProtocol.PropertyProtocol, Protocol):
        def raise_exception(self) -> NoReturn: ...

    class StoreAcknowledgmentProperty(ComponentProtocol.PropertyProtocol, Protocol):
        @property
        def value(self) -> Literal["ack", "nak"]: ...

    type ResponseRecordPromiseResultProperty[R] = (
        tuple[R, None] | tuple[None, BackendComponent.StoreExceptionProperty]
    )

    class ResponseRecordPromiseProperty[
        R: BackendComponent.ResponseRecordProperty,
    ](ComponentProtocol.PropertyProtocol, Protocol):
        """A request-persistence acknowledgment and an eventual application result.

        ACK means the request record was appended and fsynced in the replay log.
        NAK means it was not. IPC deliberately does not persist request records.
        Neither value describes response persistence or application success.

        Backend Store performs response persistence where required before returning
        the successful completed result. Response-persistence failure returns
        (None, exc); success returns (response_record, None).

        Returning the initial promise handle does not imply processing completion.
        """

        @property
        def acknowledgment(self) -> BackendComponent.StoreAcknowledgmentProperty: ...

        async def response_record(
            self,
        ) -> BackendComponent.ResponseRecordPromiseResultProperty[R]: ...

    class PullRequestRecordProperty(RequestRecordProperty, Protocol):
        pass

    class PullResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def pull_response_body(self) -> str: ...

    class PushRequestRecordProperty(RequestRecordProperty, Protocol):
        @property
        def pull_record_id(self) -> UUID | None: ...

        @property
        def session_id(self) -> UUID | None: ...

    class PushResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def commit_record(self) -> BackendComponent.CommitRecordProperty | None: ...

        @property
        def validation_record(self) -> BackendComponent.ValidationRecordProperty | None: ...

    class QueryRequestRecordProperty(RequestRecordProperty, Protocol):
        pass

    class QueryResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def query_response_body(
            self,
        ) -> BackendComponent.ControlCentrePort.QueryResponseProperty: ...

    class RunOutcomeRequestRecordProperty(RequestRecordProperty, Protocol):
        @property
        def pull_record_id(self) -> UUID | None: ...

        @property
        def push_record_id(self) -> UUID | None: ...

        @property
        def codex_session_record(self) -> BackendComponent.CodexSessionRecordProperty: ...

        @property
        def rollout_filename(self) -> str | None: ...

    class QueryOnlyStoreProperty(ComponentProtocol.PropertyProtocol, Protocol):
        def query(
            self,
            request: BackendComponent.QueryRequestRecordProperty,
        ) -> BackendComponent.ResponseRecordPromiseProperty[
            BackendComponent.QueryResponseRecordProperty
        ]: ...

    class FullStoreProperty(QueryOnlyStoreProperty, Protocol):
        def pull(
            self,
            request: BackendComponent.PullRequestRecordProperty,
        ) -> BackendComponent.ResponseRecordPromiseProperty[
            BackendComponent.PullResponseRecordProperty
        ]: ...

        def push(
            self,
            request: BackendComponent.PushRequestRecordProperty,
        ) -> BackendComponent.ResponseRecordPromiseProperty[
            BackendComponent.PushResponseRecordProperty
        ]: ...

        def run_outcome(
            self,
            request: BackendComponent.RunOutcomeRequestRecordProperty,
        ) -> BackendComponent.ResponseRecordPromiseProperty[
            BackendComponent.ControlCentrePort.RunOutcomeRecordProperty
        ]: ...

    class ContextProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def pipeline_config(self) -> PipelineConfig: ...

        @property
        def configured_namekey(self) -> NameKey | None: ...

        def ai_augment_singular_outerdicts_factory(
            self,
        ) -> tuple[
            BackendComponent.ControlCentrePort.AiAugmentSingularOuterDictProperty,
            ...,
        ]: ...

        @property
        def ai_augment_singular_outerdicts(
            self,
        ) -> tuple[
            BackendComponent.ControlCentrePort.AiAugmentSingularOuterDictProperty,
            ...,
        ]: ...

        def configured_ai_augment_singular_outerdict(
            self,
        ) -> BackendComponent.ControlCentrePort.AiAugmentSingularOuterDictProperty | None: ...

    class LifecycleProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def value(
            self,
        ) -> Literal[
            "ready",
            "busy",
            "configuration",
            "appendwatch_report_validation",
            "rollout_index",
            "pydantic_validation",
            "duckdb_evidence_validation",
            "researcher_resolution",
            "innerdict_and_card",
            "accepted",
            "configuration_error",
            "rejected",
            "retry",
            "completed",
            "failed",
        ]: ...

        def is_post_commit_validation_stage(self) -> bool: ...

        def is_post_commit_validation_result(self) -> bool: ...

    class CodexSessionRecordProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def session_id(self) -> UUID | None: ...

        @property
        def codex_rollout_record(
            self,
        ) -> BackendComponent.AgentRuntimePort.CodexRolloutRecordProperty | None: ...

        @property
        def appendwatch_report_record(
            self,
        ) -> BackendComponent.AgentRuntimePort.AppendwatchReportRecordProperty | None: ...

    class CommitRequestBodyProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def pull_record(self) -> HttpRequestLogRecord: ...

        @property
        def push_record(self) -> HttpRequestLogRecord: ...

        @property
        def codex_session_record(self) -> BackendComponent.CodexSessionRecordProperty: ...

        def validate_complete_commit(self) -> Self: ...

        @classmethod
        def validate_serialized_json(cls, value: str) -> None: ...

        @classmethod
        def from_serialized_json(
            cls,
            value: str,
            *,
            resolve_http_record: Callable[
                [UUID],
                HttpRequestLogRecord,
            ],
        ) -> Self: ...

        def serialize(self) -> dict[str, object]: ...

    class CommitRecordProperty(
        HttpRequestLogRecordProtocol,
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def http_request_log_record(self) -> HttpRequestLogRecord: ...

        @property
        def commit_request_body(
            self,
        ) -> BackendComponent.CommitRequestBodyProperty: ...

        def validate_commit_record(self) -> Self: ...

        @classmethod
        def from_http_request_log_record(
            cls,
            record: HttpRequestLogRecord,
            *,
            resolve_http_record: Callable[
                [UUID],
                HttpRequestLogRecord,
            ],
        ) -> Self: ...

    class PostCommitValidationProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def stage(self) -> BackendComponent.LifecycleProperty: ...

        @property
        def result(self) -> BackendComponent.LifecycleProperty: ...

        @property
        def detail(self) -> str | None: ...

        def validate_lifecycle(self) -> Self: ...

    class ValidationRequestBodyProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def commit_id(self) -> UUID: ...

        @property
        def post_commit_validation(
            self,
        ) -> BackendComponent.PostCommitValidationProperty: ...

        @property
        def submission_type(
            self,
        ) -> Literal["Submission", "StandardizedSubmission"] | None: ...

        @property
        def submission(self) -> Mapping[str, JsonValue] | None: ...

        @property
        def http_record_ids(self) -> tuple[UUID, ...]: ...

        def validate_body(self) -> Self: ...

    class ValidationRecordProperty(
        HttpRequestLogRecordProtocol,
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def http_request_log_record(self) -> HttpRequestLogRecord: ...

        @property
        def validation_request_body(
            self,
        ) -> BackendComponent.ValidationRequestBodyProperty: ...

        def validate_record(self) -> Self: ...

        @classmethod
        def from_http_request_log_record(
            cls,
            record: HttpRequestLogRecord,
        ) -> Self: ...

    class AgentRuntimePort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Backend - AI Agent Runtime Connector."""

        class AttemptRecordProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def attempt(self) -> AgentRuntimeComponent.AttemptProperty: ...

            @property
            def submission(
                self,
            ) -> Submission | StandardizedSubmission | None: ...

            @property
            def ground_truth_innerdict(self) -> InnerDict | None: ...

            @property
            def validation_record(
                self,
            ) -> BackendComponent.ValidationRecordProperty | None: ...

            @classmethod
            def from_serialized_json(
                cls,
                value: str | bytes,
                *,
                procedure: MatchingProcedure | None,
            ) -> Self: ...

            def serialize(self) -> dict[str, object]: ...

        class CodexRolloutRecordProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def sha256(self) -> str: ...

            @property
            def size(self) -> int: ...

            @property
            def line_count(self) -> int: ...

            @classmethod
            def build_summary_json(
                cls,
                values: Mapping[str, object],
            ) -> str: ...

            @classmethod
            def parse_summary_json(
                cls,
                value: str,
            ) -> dict[str, str]: ...

        class AppendwatchReportEncodingProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def value(self) -> Literal["base64"]: ...

        class AppendwatchReportRecordProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def encoding(
                self,
            ) -> BackendComponent.AgentRuntimePort.AppendwatchReportEncodingProperty: ...

            @property
            def data(self) -> str: ...

            def validate_canonical_base64(self) -> Self: ...

            def decoded_bytes(self) -> bytes: ...

    class ControlCentrePort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Backend - Control Centre Connector."""

        class CommittedInnerDictProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def innerdict(self) -> InnerDict: ...

            @property
            def commit_record(self) -> BackendComponent.CommitRecordProperty: ...

            def text(self, column: str) -> str | None: ...

            def validate_committed_innerdict(self) -> Self: ...

            @classmethod
            def from_serialized(
                cls,
                value: Mapping[str, object],
            ) -> Self: ...

            def serialize(self) -> dict[str, object]: ...

        class AiAugmentSingularOuterDictProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def namekey(self) -> NameKey: ...

            @property
            def xlsx_innerdicts(self) -> tuple[InnerDict, ...]: ...

            @property
            def ssn_innerdicts(self) -> tuple[InnerDict, ...]: ...

            @property
            def docx_innerdicts(self) -> tuple[InnerDict, ...]: ...

            @property
            def committed_innerdicts(self) -> tuple[
                BackendComponent.ControlCentrePort.CommittedInnerDictProperty,
                ...
            ]: ...

            @property
            def ai_augment_rnd(self) -> int: ...

            @property
            def ai_augment_cohort(
                self,
            ) -> AiAugmentCohort: ...

            @property
            def ai_augment_ineligibility_category(
                self,
            ) -> AiAugmentIneligibilityCategory | None: ...

            def validate_ai_augment_singular_outerdict(self) -> Self: ...

            def ground_truth_innerdict(self) -> InnerDict | None: ...

            @classmethod
            def from_serialized(
                cls,
                value: Mapping[str, object],
            ) -> Self: ...

            def serialize(self) -> dict[str, object]: ...

        class RunOutcomeResponseBodyProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def commit_record_id(self) -> UUID | None: ...

            @property
            def validation_record_id(self) -> UUID | None: ...

            @property
            def run_outcome_record_id(self) -> UUID: ...

            @property
            def pull_record_id(self) -> UUID | None: ...

            @property
            def push_record_id(self) -> UUID | None: ...

            @property
            def codex_session_record(
                self,
            ) -> BackendComponent.CodexSessionRecordProperty: ...

            @classmethod
            def from_serialized_json(
                cls,
                value: str | bytes,
            ) -> Self: ...

            def serialize(self) -> dict[str, object]: ...

        class RunOutcomeRecordProperty(
            HttpRequestLogRecordProtocol,
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def run_outcome_request(
                self,
            ) -> ControlCentreComponent.BackendPort.RunOutcomeRequestProperty: ...

            @property
            def http_request_log_record(self) -> HttpRequestLogRecord: ...

            @property
            def run_outcome_response_body(
                self,
            ) -> BackendComponent.ControlCentrePort.RunOutcomeResponseBodyProperty: ...

            @property
            def run_outcome(
                self,
            ) -> ControlCentreComponent.LifecycleProperty: ...

            def validate_record(self) -> Self: ...

            @classmethod
            def from_http_request_log_record(
                cls,
                record: HttpRequestLogRecord,
            ) -> Self: ...

        class QueryResponseProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def attempts(
                self,
            ) -> tuple[
                BackendComponent.AgentRuntimePort.AttemptRecordProperty,
                ...,
            ]: ...

            @property
            def ai_augment_singular_outerdicts(
                self,
            ) -> tuple[
                BackendComponent.ControlCentrePort.AiAugmentSingularOuterDictProperty,
                ...,
            ]: ...

            @property
            def run_outcome_records(
                self,
            ) -> tuple[
                BackendComponent.ControlCentrePort.RunOutcomeRecordProperty,
                ...,
            ]: ...

            @classmethod
            def from_serialized_json(
                cls,
                value: str | bytes,
            ) -> Self: ...

            def serialize(self) -> dict[str, object]: ...


class AgentRuntimeComponent(
    ComponentProtocol,
    Protocol,
):
    class AttemptProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def pull_record(self) -> HttpRequestLogRecord: ...

        @property
        def commit_record(self) -> BackendComponent.CommitRecordProperty: ...

        @property
        def post_commit_validation(
            self,
        ) -> BackendComponent.PostCommitValidationProperty: ...


class ControlCentreComponent(
    ComponentProtocol,
    Protocol,
):
    class ContextProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def pipeline_config(self) -> PipelineConfig: ...

        @property
        def openalex_api_key(self) -> str: ...

        @property
        def lima_configuration(
            self,
        ) -> LimaConfiguration: ...

    class LifecycleProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def value(
            self,
        ) -> Literal[
            "ready",
            "queued",
            "running",
            "started",
            "remote_pid_discovered",
            "session_discovered",
            "rollout_discovered",
            "push_accepted",
            "cancel_requested",
            "codex_exited",
            "completed",
            "failed",
            "cancelled",
        ]: ...

        def is_run_outcome(self) -> bool: ...

        def to_run_outcome_path(
            self,
        ) -> ControlCentreComponent.BackendPort.RunOutcomePathProperty: ...

        @classmethod
        def from_run_outcome_path(
            cls,
            path: str,
        ) -> Self: ...

    class RunEventProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def run_id(self) -> UUID: ...

        @property
        def namekey(self) -> NameKey: ...

        @property
        def occurred_at_unix_usec(self) -> int: ...

        @property
        def lifecycle(self) -> ControlCentreComponent.LifecycleProperty: ...

        @property
        def session_id(self) -> UUID | None: ...

        @property
        def rollout_jsonl(self) -> PurePosixPath | None: ...

        @property
        def remote_pid(self) -> int | None: ...

        @property
        def accepted_commit_record_id(self) -> UUID | None: ...

        @property
        def codex_exit_code(self) -> int | None: ...

        @property
        def detail(self) -> str | None: ...

        @property
        def occurred_at(self) -> datetime: ...

    class RunProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def run_id(self) -> UUID: ...

        @property
        def namekey(self) -> NameKey: ...

        @property
        def lifecycle(self) -> ControlCentreComponent.LifecycleProperty: ...

        @property
        def run_outcome(
            self,
        ) -> ControlCentreComponent.LifecycleProperty | None: ...

        def is_queued(self) -> bool: ...

        def is_running(self) -> bool: ...

        def is_finished(self) -> bool: ...

        @property
        def events(
            self,
        ) -> tuple[
            ControlCentreComponent.RunEventProperty,
            ...,
        ]: ...

        @property
        def attempts(
            self,
        ) -> tuple[
            AgentRuntimeComponent.AttemptProperty,
            ...,
        ]: ...

        @property
        def run_outcome_record(
            self,
        ) -> BackendComponent.ControlCentrePort.RunOutcomeRecordProperty | None: ...

    class BackendPort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Control Centre - Backend Connector."""

        class RunOutcomePathProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def value(
                self,
            ) -> Literal[
                "/completed",
                "/failed",
                "/cancelled",
            ]: ...

        class QueryRequestProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            """Request the complete Backend snapshot; no parameters."""

        class RunOutcomeRequestProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def run_outcome(self) -> ControlCentreComponent.LifecycleProperty: ...

            @property
            def namekey(self) -> NameKey: ...

            @property
            def http_request_log_record(self) -> HttpRequestLogRecord: ...

            @property
            def path(
                self,
            ) -> ControlCentreComponent.BackendPort.RunOutcomePathProperty: ...

            @property
            def request_headers(self) -> Mapping[str, str]: ...

            @classmethod
            def from_http_request(
                cls,
                *,
                received_at_unix_usec: int,
                method: str,
                scheme: str,
                host: str,
                port: int | None,
                path: str,
                query: str,
                request_headers: Mapping[str, str],
                request_body: bytes,
            ) -> Self: ...

            @classmethod
            def from_http_request_log_record(
                cls,
                record: HttpRequestLogRecord,
            ) -> Self: ...

            def validate_http_request_log_record(self) -> Self: ...
