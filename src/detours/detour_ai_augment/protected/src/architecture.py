"""Also see any classes implemented under `data_models`"""

from __future__ import annotations

from collections.abc import Mapping
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
    
    # =====================================================
    # Handling of intra-component HTTP-shaped
    # request/response events, owned by the Backend.
    # 
    # Raw `requests` objects must have already been wrapped
    # into `HttpRequestLogRecord` objects upstream
    # (e.g., by Backend's middleware).
    #
    # Therefore, these Request and Record properties 
    # stand for Backend-level representations rather
    # than HTTP request/responses.
    # =====================================================
    
    class AiAugmentHttpRequestLogRecordProperty(
        HttpRequestLogRecordProtocol,
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def http_request_log_record(self) -> HttpRequestLogRecord: ...

        @classmethod
        def from_http_request_log_record(
            cls,
            *,
            http_request_log_record: HttpRequestLogRecord,
        ) -> Self: ...

        @classmethod
        def from_serialized_json(
            cls,
            *,
            value: str,
        ) -> Self: ...

        def serialize(self) -> dict[str, object]: ...

    class RequestRecordProperty(
        AiAugmentHttpRequestLogRecordProperty,
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ): ...

    class ResponseRecordProperty(
        AiAugmentHttpRequestLogRecordProperty,
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ): ...

    class StoreExceptionProperty(ComponentProtocol.PropertyProtocol, Protocol):
        """Backend Store uses this to communicate exceptions asynchronously."""

        def raise_exception(self) -> NoReturn: ...

    class StoreAcknowledgmentProperty(ComponentProtocol.PropertyProtocol, Protocol):
        """Backend Store uses this to communicate the fact
        of durable storage of a request synchronously."""

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

    # =======================================
    # Request and Response Record properties
    # =======================================

    class PullRequestRecordProperty(RequestRecordProperty, Protocol): ...

    class PullResponseRecordProperty(ResponseRecordProperty, Protocol): ...

    class PushRequestRecordProperty(RequestRecordProperty, Protocol): ...

    class PushResponseRecordProperty(ResponseRecordProperty, Protocol): ...

    class CommitRequestRecordProperty(RequestRecordProperty, Protocol):
        @property
        def commit_request_body(
            self,
        ) -> BackendComponent.CommitRequestBodyProperty: ...

    class ValidationRequestRecordProperty(RequestRecordProperty, Protocol):
        """Encodes losslessly the entire Agent Runtime's
        attempt at getting the Backend to expose `410 Gone`
        at `GET /pull` by means of submitting processable
        content to `POST /push`. Not a part of the Agent
        Runtime - Backend connector because it is never
        exposed to the Agent Runtime."""

    class RunOutcomeRequestRecordProperty(RequestRecordProperty, Protocol):
        @property
        def namekey(self) -> NameKey | None: ...

        @property
        def session_id(self) -> UUID | None: ...

        @property
        def backend_validation_record(self) -> (
            BackendComponent.ValidationRequestRecordProperty | None
        ): ...

    class RunOutcomeResponseRecordProperty(
        ResponseRecordProperty,
        Protocol,
    ):
        @property
        def run_outcome_request(
            self,
        ) -> ControlCentreComponent.BackendPort.RunOutcomeRequestRecordProperty: ...

        @property
        def run_outcome_response_body(
            self,
        ) -> BackendComponent.RunOutcomeResponseBodyProperty: ...

        @property
        def run_outcome(
            self,
        ) -> ControlCentreComponent.LifecycleProperty: ...

    class QueryRequestRecordProperty(RequestRecordProperty, Protocol):
        pass

    class QueryResponseRecordProperty(ResponseRecordProperty, Protocol):
        @property
        def query_response_body(
            self,
        ) -> ControlCentreComponent.BackendPort.QueryResponseRecordProperty: ...
    
    # =============================================
    # Secondary representations for detour handoff
    # =============================================

    class CodexInnerDictProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        """A `/completed` RunOutcomeResponseRecord with its InnerDict."""

        @property
        def innerdict(self) -> InnerDict: ...

        @property
        def run_outcome_response_record(self) -> (
            BackendComponent.RunOutcomeResponseRecordProperty
        ): ...

        def text(self, column: str) -> str | None: ...

        def validate_codex_innerdict(self) -> Self: ...

        @classmethod
        def from_serialized(
            cls,
            value: Mapping[str, object],
        ) -> Self: ...

        def serialize(self) -> dict[str, object]: ...
    
    class AiAugmentSingularOuterDictProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        """Ultimate representation of a NameKey's augmented card."""

        @property
        def namekey(self) -> NameKey: ...

        @property
        def xlsx_innerdicts(self) -> tuple[InnerDict, ...]: ...

        @property
        def ssn_innerdicts(self) -> tuple[InnerDict, ...]: ...

        @property
        def docx_innerdicts(self) -> tuple[InnerDict, ...]: ...

        @property
        def codex_innerdicts(self) -> tuple[
            BackendComponent.CodexInnerDictProperty,
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

    # =============================================================
    # Lower-level representations used by Request/Response Records
    # =============================================================

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
        ) -> BackendComponent.AppendwatchReportEncodingProperty: ...

        @property
        def data(self) -> str: ...

    class CodexSessionRecordProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def session_id(self) -> UUID | None: ...

        @property
        def codex_rollout_record(
            self,
        ) -> BackendComponent.CodexRolloutRecordProperty | None: ...

        @property
        def appendwatch_report_record(
            self,
        ) -> BackendComponent.AppendwatchReportRecordProperty | None: ...

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

        @property
        def submission_type(
            self,
        ) -> Literal["Submission", "StandardizedSubmission"] | None: ...

        @property
        def submission(self) -> Mapping[str, JsonValue] | None: ...

    class ValidationRequestBodyProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        """Post-commit validation request body."""

        @property
        def commit_record(self) -> BackendComponent.CommitRequestRecordProperty: ...

        @property
        def post_commit_validation(
            self,
        ) -> BackendComponent.PostCommitValidationProperty: ...

        @property
        def initial_validation_record(
            self,
        ) -> BackendComponent.ValidationRequestRecordProperty | None: ...

        @property
        def openalex_ror_records(self) -> tuple[HttpRequestLogRecord, ...]: ...

    class RunOutcomeResponseBodyProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def attempt(self) -> AgentRuntimeComponent.BackendPort.AttemptProperty | None: ...

    # ================================
    # Backend's lifecycle and runtime
    # ================================

    class ContextProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def pipeline_config(self) -> PipelineConfig: ...

        @property
        def configured_namekey(self) -> NameKey | None: ...

        @property
        def backend_store(
            self,
        ) -> (
            BackendComponent.FullStoreProperty
            | BackendComponent.QueryOnlyStoreProperty
        ): ...

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

    class QueryOnlyStoreProperty(ComponentProtocol.PropertyProtocol, Protocol):
        def query(
            self,
            request: BackendComponent.QueryRequestRecordProperty,
        ) -> BackendComponent.ResponseRecordPromiseProperty[
            BackendComponent.QueryResponseRecordProperty
        ]: ...
            
    class FullStoreProperty(QueryOnlyStoreProperty, Protocol):
        @property
        def current_pull_record(self) -> HttpRequestLogRecord | None: ...

        @property
        def current_push_record(self) -> HttpRequestLogRecord | None: ...

        @property
        def current_commit_record(self) -> BackendComponent.CommitRequestRecordProperty | None: ...

        @property
        def current_validation_record(self) -> (
            BackendComponent.ValidationRequestRecordProperty | None
        ): ...

        @property
        def initial_validation_record(self) -> (
            BackendComponent.ValidationRequestRecordProperty | None
        ): ...

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
            BackendComponent.RunOutcomeResponseRecordProperty
        ]: ...

    class AgentRuntimePort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Backend - AI Agent Runtime connector.
        The Agent Runtime's port owns all logic due to
        Python's nested class inheritance limitations."""

    class ControlCentrePort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Backend - Control Centre connector.
        The Control Centre's port owns all logic due to
        Python's nested class inheritance limitations."""
        

class AgentRuntimeComponent(
    ComponentProtocol,
    Protocol,
):

    class BackendPort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Backend - Agent Runtime connector."""

        class AttemptProperty(
            BackendComponent.ValidationRequestRecordProperty,
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ): ...

        class AttemptRecordProperty(
            AttemptProperty,
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            """Wraps BackendValidationRecord, a.k.a (on the Agent
            Runtime's port) Attempt, in order to expose additional
            properties that are helpful on the Backend end's of
            the Agent Runtime - Backend connector for the purpose
            of processing an Agent Runtime's submission."""

            @property
            def attempt(self) -> AgentRuntimeComponent.BackendPort.AttemptProperty: ...

            @property
            def submission(
                self,
            ) -> Submission | StandardizedSubmission | None: ...

            @property
            def ground_truth_innerdict(self) -> InnerDict | None: ...


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

        def to_run_outcome(
            self,
        ) -> ControlCentreComponent.BackendPort.RunOutcomeProperty: ...

        @classmethod
        def from_run_outcome(
            cls,
            run_outcome: ControlCentreComponent.BackendPort.RunOutcomeProperty,
        ) -> Self: ...

    class RunEventProperty(
        ComponentProtocol.PropertyProtocol,
        Protocol,
    ):
        @property
        def run_id(self) -> UUID: ...

        @property
        def occurred_at_unix_usec(self) -> int: ...

        @property
        def lifecycle(self) -> ControlCentreComponent.LifecycleProperty: ...

        @property
        def detail(self) -> str | None: ...

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

        def is_queued(self) -> bool: ...

        def is_running(self) -> bool: ...

        def is_finished(self) -> bool: ...

        @property
        def session_id(self) -> UUID | None: ...

        @property
        def remote_pid(self) -> int | None: ...

        def events(
            self,
        ) -> tuple[
            ControlCentreComponent.RunEventProperty,
            ...,
        ]: ...

        @property
        def run_outcome_record(
            self,
        ) -> BackendComponent.RunOutcomeResponseRecordProperty | None: ...

    class BackendPort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Control Centre - Backend connector."""

        class RunOutcomeProperty(
            ComponentProtocol.PortProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def value(
                self,
            ) -> Literal[
                "completed",
                "failed",
                "cancelled",
            ]: ...

            @classmethod
            def from_url_path(
                cls,
                url_path: Literal[
                    "/completed",
                    "/failed",
                    "/cancelled",
                ]
            ) -> Self: ...

            @property
            def to_url_path(
                self,
            ) -> Literal[
                "/completed",
                "/failed",
                "/cancelled",
            ]: ...

        class RunOutcomeRequestRecordProperty(
            BackendComponent.RequestRecordProperty,
            ComponentProtocol.PropertyProtocol,
            Protocol,
        ):
            @property
            def namekey(self) -> NameKey | None: ...

            @property
            def session_id(self) -> UUID | None: ...

            @property
            def backend_validation_record(self) -> (
                BackendComponent.ValidationRequestRecordProperty | None
            ): ...

            @property
            def run_outcome(self) -> ControlCentreComponent.BackendPort.RunOutcomeProperty: ...
        
        class QueryRequestRecordProperty(
            BackendComponent.RequestRecordProperty,
            ComponentProtocol.PropertyProtocol,
            Protocol,
        ):
            """Request all `AiAugmentSingularOuterDict`s."""

        class QueryResponseRecordProperty(
            BackendComponent.ResponseRecordProperty,
            ComponentProtocol.PropertyProtocol,
            Protocol,
        ):

            @property
            def ai_augment_singular_outerdicts(
                self,
            ) -> tuple[
                BackendComponent.AiAugmentSingularOuterDictProperty,
                ...,
            ]: ...
