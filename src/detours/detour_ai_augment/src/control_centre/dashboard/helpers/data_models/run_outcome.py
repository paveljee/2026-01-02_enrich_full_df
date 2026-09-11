from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from src.detours.detour_ai_augment.protected.src.architecture import (
    ControlCentreComponent,
)
from src.helpers.architecture import implements
from src.helpers.data_models import HttpRequestLogRecord, NameKey
from src.helpers.vars import (
    KTP_FIRST_NAME_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    KTP_LAST_NAME_COL,
)


@implements[ControlCentreComponent.BackendPort.RunOutcomePathProperty]()
class RunOutcomePath(StrEnum):
    value: Literal["/completed", "/failed", "/cancelled"]

    COMPLETED = "/completed"
    FAILED = "/failed"
    CANCELLED = "/cancelled"


COMPLETED_PATH = RunOutcomePath.COMPLETED
FAILED_PATH = RunOutcomePath.FAILED
CANCELLED_PATH = RunOutcomePath.CANCELLED
RUN_OUTCOME_PATHS: frozenset[RunOutcomePath] = frozenset(RunOutcomePath)

HTTP_POST_METHOD = "POST"
SYNTHETIC_SCHEME = "http"
SYNTHETIC_HOST = "invalid"
SOURCE_KEY_HEADER = "SourceKey"
NAME_KEY_HEADER = "NameKey"
STRUCTURED_FIELD_STRING = r'"(?:[\x20-\x21\x23-\x5b\x5d-\x7e]|\\["\\])*"'
NAME_KEY_PATTERN = re.compile(
    rf"^{re.escape(KTP_FIRST_NAME_COL)}=(?P<first>{STRUCTURED_FIELD_STRING}), "
    rf"{re.escape(KTP_LAST_NAME_COL)}=(?P<last>{STRUCTURED_FIELD_STRING})$"
)


def structured_field_string(value: str) -> str:
    if any(
        ord(character) < 0x20 or ord(character) > 0x7E for character in value
    ):
        raise ValueError(
            "Structured Field String contains a non-printable-ASCII value"
        )
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def structured_field_string_value(value: str) -> str:
    if re.fullmatch(STRUCTURED_FIELD_STRING, value) is None:
        raise ValueError("Structured Field String is malformed")
    decoded: list[str] = []
    index = 1
    while index < len(value) - 1:
        character = value[index]
        if character == "\\":
            index += 1
            character = value[index]
        decoded.append(character)
        index += 1
    return "".join(decoded)


def name_key_header_value(namekey: NameKey) -> str:
    return (
        f"{KTP_FIRST_NAME_COL}="
        f"{structured_field_string(namekey.first_name)}, "
        f"{KTP_LAST_NAME_COL}={structured_field_string(namekey.last_name)}"
    )


def name_key_from_header_value(value: object) -> NameKey:
    if not isinstance(value, str):
        raise ValueError("NameKey header is missing")
    matched = NAME_KEY_PATTERN.fullmatch(value)
    if matched is None:
        raise ValueError("NameKey header is malformed")
    try:
        namekey = NameKey(**{
            KTP_FIRST_NAME_COL: structured_field_string_value(matched.group("first")),
            KTP_LAST_NAME_COL: structured_field_string_value(matched.group("last")),
        })
    except (TypeError, ValueError) as exc:
        raise ValueError("NameKey header is malformed") from exc
    if value != name_key_header_value(namekey):
        raise ValueError("NameKey header is not canonical")
    return namekey


@implements[ControlCentreComponent.LifecycleProperty]()
class RunLifecycle(StrEnum):
    value: Literal[
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
    ]

    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    STARTED = "started"
    REMOTE_PID_DISCOVERED = "remote_pid_discovered"
    SESSION_DISCOVERED = "session_discovered"
    ROLLOUT_DISCOVERED = "rollout_discovered"
    PUSH_ACCEPTED = "push_accepted"
    CANCEL_REQUESTED = "cancel_requested"
    CODEX_EXITED = "codex_exited"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def is_run_outcome(self) -> bool:
        return self in {
            RunLifecycle.COMPLETED,
            RunLifecycle.FAILED,
            RunLifecycle.CANCELLED,
        }

    def to_run_outcome_path(
        self,
    ) -> RunOutcomePath:
        if self is RunLifecycle.COMPLETED:
            return COMPLETED_PATH
        if self is RunLifecycle.FAILED:
            return FAILED_PATH
        if self is RunLifecycle.CANCELLED:
            return CANCELLED_PATH
        raise ValueError("run lifecycle has no run-outcome HTTP request path")

    @classmethod
    def from_run_outcome_path(
        cls,
        path: str,
    ) -> Self:
        try:
            run_outcome_path = RunOutcomePath(path)
        except ValueError as exc:
            raise ValueError("run-outcome HTTP request path is invalid") from exc
        if run_outcome_path is COMPLETED_PATH:
            return cls.COMPLETED
        if run_outcome_path is FAILED_PATH:
            return cls.FAILED
        if run_outcome_path is CANCELLED_PATH:
            return cls.CANCELLED
        raise ValueError("run-outcome HTTP request path is invalid")


def _http_header_value(
    headers: Mapping[str, str],
    name: str,
) -> str | None:
    normalized_name = name.casefold()
    for key, value in headers.items():
        if key.casefold() == normalized_name:
            return value
    return None


@implements[ControlCentreComponent.BackendPort.RunOutcomeRequestProperty]()
class RunOutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    run_outcome: RunLifecycle
    namekey: NameKey
    http_request_log_record: HttpRequestLogRecord

    @property
    def path(self) -> RunOutcomePath:
        return self.run_outcome.to_run_outcome_path()

    @property
    def request_headers(self) -> Mapping[str, str]:
        return {NAME_KEY_HEADER: name_key_header_value(self.namekey)}

    @classmethod
    def outbound_http(
        cls,
        *,
        run_outcome: RunLifecycle,
        namekey: NameKey,
    ) -> tuple[
        RunOutcomePath,
        Mapping[str, str],
    ]:
        return (
            run_outcome.to_run_outcome_path(),
            {NAME_KEY_HEADER: name_key_header_value(namekey)},
        )

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
    ) -> Self:
        selected_headers = {
            name: value
            for name in (NAME_KEY_HEADER, SOURCE_KEY_HEADER)
            if (value := _http_header_value(request_headers, name)) is not None
        }
        record = HttpRequestLogRecord(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
            received_at_unix_usec=received_at_unix_usec,
            method=method,
            scheme=scheme,
            host=host,
            port=port,
            path=path,
            query=query,
            request_headers=selected_headers,
            request_body=(None if not request_body else request_body.decode()),
            response_code=None,
            response_headers=None,
            response_body=None,
            ready_to_respond_at_unix_usec=None,
            duration_usec=None,
        )
        return cls.from_http_request_log_record(record)

    @classmethod
    def from_http_request_log_record(
        cls,
        record: HttpRequestLogRecord,
    ) -> Self:
        run_outcome = RunLifecycle.from_run_outcome_path(record.path)
        return cls(
            run_outcome=run_outcome,
            namekey=name_key_from_header_value(
                record.request_headers.get(NAME_KEY_HEADER)
            ),
            http_request_log_record=record,
        )

    def validate_http_request_log_record(self) -> Self:
        record = self.http_request_log_record
        if (
            record.schema_version != KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1
            or record.record_id.version != 7
            or record.method != HTTP_POST_METHOD
            or record.scheme != SYNTHETIC_SCHEME
            or record.host != SYNTHETIC_HOST
            or record.port is not None
            or record.ready_to_respond_at_unix_usec is not None
            or record.path not in RUN_OUTCOME_PATHS
            or record.query
            or set(record.request_headers) != {NAME_KEY_HEADER}
            or record.request_body is not None
            or record.response_code is not None
            or record.response_headers is not None
            or record.response_body is not None
            or record.received_at_unix_usec is None
            or record.duration_usec is not None
            or record.path != self.path
            or record.request_headers != self.request_headers
        ):
            raise ValueError("run-outcome HTTP request has an invalid contour")
        namekey = name_key_from_header_value(record.request_headers[NAME_KEY_HEADER])
        if namekey != self.namekey:
            raise ValueError("run-outcome NameKey does not match its request")
        return self

    @model_validator(mode="after")
    def _validate_http_request_log_record(self) -> Self:
        return self.validate_http_request_log_record()
