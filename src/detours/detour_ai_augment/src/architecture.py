from __future__ import annotations

from typing import Protocol
from uuid import UUID

from src.helpers.data_models import HttpRequestLogRecord, NameKey

from .acme_protocol import ComponentProtocol


class implements[Proto]:
    """
    Generic decorator for statically asserting that a concrete class
    structurally implements a `Protocol`.

    When `Proto` is a `Protocol` class, applying `@implements[Proto]()`
    to a concrete class causes a static type checker such as mypy
    to check that the class structurally satisfies `type[Proto]`,
    in particular `Proto`'s read-only `@property` definitions.

    Note that the static type checker neither asserts nor enforces
    that `Proto` is a `Protocol` class; rather, this is mandated
    as a convention in this code base.

    For a concrete class `C`, this decorator imposes essentially
    the same static compatibility check as:

    ```python
    _check: type[Proto] = C
    ```

    Normal mypy protocol compatibility rules apply, including
    compatibility of member signatures and nested member types.

    At runtime, no conformance check is performed. 
    
    Returns the original class unchanged.

    signed off: human (credit to gpt-6-astra-pro for conceiving)
    """


    def __call__(self, cls: type[Proto]) -> type[Proto]:
        return cls


class BackendComponent(
    ComponentProtocol,
    Protocol,
):

    class CodexSessionRecordProperty(
        ComponentProtocol
        .PropertyProtocol,
        Protocol,
    ):
        @property
        def session_id(self) -> UUID | None:
            ...

        @property
        def codex_rollout_record(
            self,
        ) -> (
            BackendComponent
            .AgentRuntimePort
            .CodexRolloutRecordProperty
            | None
        ):
            ...

        @property
        def appendwatch_report_record(
            self,
        ) -> (
            BackendComponent
            .AgentRuntimePort
            .AppendwatchReportRecordProperty
            | None
        ):
            ...

    class CommitRequestBodyProperty(
        ComponentProtocol
        .PropertyProtocol,
        Protocol,
    ):
        @property
        def pull_record(self) -> HttpRequestLogRecord:
            ...

        @property
        def push_record(self) -> HttpRequestLogRecord:
            ...

        @property
        def codex_session_record(self) -> (
            BackendComponent
            .CodexSessionRecordProperty
        ):
            ...

    class CommitRecordProperty(
        ComponentProtocol
        .PropertyProtocol,
        Protocol,
    ):
        @property
        def pull_record(self) -> HttpRequestLogRecord:
            ...

        @property
        def push_record(self) -> HttpRequestLogRecord:
            ...

        @property
        def codex_session_record(self) -> (
            BackendComponent
            .CodexSessionRecordProperty
        ):
            ...

    class PostCommitValidationProperty(
        ComponentProtocol
        .PropertyProtocol,
        Protocol,
    ):
        @property
        def stage(self) -> str:
            ...

        @property
        def result(self) -> str:
            ...

        @property
        def detail(self) -> str | None:
            ...

    class AgentRuntimePort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Backend - AI Agent Runtime Connector."""

        class CodexRolloutRecordProperty(
            ComponentProtocol
            .PortProtocol
            .PropertyProtocol,
            Protocol,
        ):
            @property
            def sha256(self) -> str:
                ...

            @property
            def size(self) -> int:
                ...

            @property
            def line_count(self) -> int:
                ...

        class AppendwatchReportRecordProperty(
            ComponentProtocol
            .PortProtocol
            .PropertyProtocol,
            Protocol,
        ):
            @property
            def encoding(self) -> str:
                ...

            @property
            def data(self) -> str:
                ...


class AgentRuntimeComponent(
    ComponentProtocol,
    Protocol,
):

    class AttemptProperty(
        ComponentProtocol
        .PropertyProtocol,
        Protocol,
    ):
        @property
        def pull_record(self) -> HttpRequestLogRecord:
            ...

        @property
        def commit_record(self) -> (
            BackendComponent
            .CommitRecordProperty
        ):
            ...

        @property
        def post_commit_validation(
            self,
        ) -> (
            BackendComponent
            .PostCommitValidationProperty
        ):
            ...


class ControlCentreComponent(
    ComponentProtocol,
    Protocol,
):

    class RunProperty(
        ComponentProtocol
        .PropertyProtocol,
        Protocol,
    ):
        @property
        def run_id(self) -> UUID:
            ...

        @property
        def namekey(self) -> NameKey:
            ...

        @property
        def phase(self) -> str:
            ...

        @property
        def outcome(self) -> str | None:
            ...

        @property
        def attempts(self) -> tuple[
            AgentRuntimeComponent
            .AttemptProperty,
            ...
        ]:
            ...

        @property
        def run_outcome_record(
            self,
        ) -> (
            ControlCentreComponent
            .BackendPort
            .RunOutcomeRecordProperty
            | None
        ):
            ...

    class RunEventProperty(
        ComponentProtocol
        .PropertyProtocol,
        Protocol,
    ):
        @property
        def run_id(self) -> UUID:
            ...

        @property
        def namekey(self) -> NameKey:
            ...

        @property
        def occurred_at_unix_usec(self) -> int:
            ...

        @property
        def kind(self) -> str:
            ...

        @property
        def session_id(self) -> UUID | None:
            ...

        @property
        def rollout_jsonl(self) -> str | None:
            ...

        @property
        def remote_pid(self) -> int | None:
            ...

        @property
        def accepted_commit_record_id(self) -> UUID | None:
            ...

        @property
        def codex_exit_code(self) -> int | None:
            ...

        @property
        def detail(self) -> str | None:
            ...

    class BackendPort(
        ComponentProtocol.PortProtocol,
        Protocol,
    ):
        """Serves the Control Centre - Backend Connector."""

        class RunOutcomeResponseBodyProperty(
            ComponentProtocol
            .PortProtocol
            .PropertyProtocol,
            Protocol,
        ):
            @property
            def pull_record_id(self) -> UUID | None:
                ...

            @property
            def push_record_id(self) -> UUID | None:
                ...

            @property
            def codex_session_record(
                self,
            ) -> (
                BackendComponent
                .CodexSessionRecordProperty
            ):
                ...

        class RunOutcomeRecordProperty(
            ComponentProtocol
            .PortProtocol
            .PropertyProtocol,
            Protocol,
        ):
            @property
            def run_outcome(self) -> str:
                ...

            @property
            def run_outcome_response_body(
                self,
            ) -> (
                ControlCentreComponent
                .BackendPort
                .RunOutcomeResponseBodyProperty
            ):
                ...
