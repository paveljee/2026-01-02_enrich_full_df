from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import tempfile
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from random import Random
from typing import TYPE_CHECKING, Callable, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

import duckdb
from fastapi import status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictStr,
    ValidationError,
    model_validator,
)

from src.detours.detour_ai_augment.protected.src.architecture import BackendComponent
from src.detours.detour_ai_augment.protected.src.backend.helpers import codex_parse
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    AcademicPositionsSubmission,
    AgeFirstPublicationSubmission,
    EducationSubmission,
    EvidenceSubmission,
    EvidenceWithdrawal,
    FieldSubmission,
    GenderSubmission,
    PlaceOfResidenceStandardized,
    PlaceOfResidenceSubmission,
    RaceEthnicityLanguageCultureStandardized,
    RaceEthnicityLanguageCultureSubmission,
    ResearcherAuthorStandardized,
    ResearcherAuthorSubmission,
    ResearcherLinksSubmission,
    SocialCapitalSubmission,
    StandardizedFieldSubmission,
    StandardizedSubmission,
    StandardizedValue,
    WebSearchExcerpt,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_fixture import (  # noqa: E501
    L_FEI_FEI_RETRY_FIXTURE,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.submission_init import (  # noqa: E501
    Submission,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_COLUMNS,
    AI_AUGMENT_EVIDENCE_COLUMNS,
    AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS,
    CODEX_CITE_MARKER_PREFIX,
    CODEX_CITE_MARKER_SUFFIX,
    CODEX_PAYLOAD_KEY,
    CODEX_TYPE_KEY,
    COMPACT_JSON_SEPARATORS,
    EVIDENCE_ITEMS_ACCEPTED_DEF,
    EVIDENCE_OUTCOME_UNMATCHED,
    EVIDENCE_OUTCOME_V1_EXACT,
    EVIDENCE_OUTCOME_V2_NEAR,
    EVIDENCE_OUTCOME_WITHDRAWN,
    EVIDENCE_PROGRESS_PRAISE_DEF,
    HAS_CONTROL_CHARACTER,
    ISO_8601_UTC_OFFSET,
    ISO_8601_UTC_SUFFIX,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL,
    KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_LINKS_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL,
    KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL,
    KTP_AI_AUGMENT_SESSION_METADATA_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL,
    MILLISECONDS_PER_SECOND,
    NOT_AVAILABLE_OR_APPLICABLE_VALUE,
    NOT_REPORTED_VALUE,
    ROLLOUT_FILENAME_PREFIX,
    ROLLOUT_FILENAME_SUFFIX,
    SOURCE_KEY_HEADER,
    STANDARDIZED_SUBMISSION_TYPE,
    SUBMISSION_TYPE,
    TEXT_ENCODING,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.lifecycle import (
    BackendLifecycle,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.model_http_interceptor import (  # noqa: E501
    ModelHttpRequired,
    ReplayInputMissing,
)
from src.detours.detour_ai_augment.src.shared import (
    AppendwatchReportError,
    parse_appendwatch_report,
    require_nonblank_text,
    source_key_from_header_value,
)
from src.helpers.architecture import FrozenStrictModel, LazyResultFactory, implements
from src.helpers.data_models import (
    FragmentType,
    NameKey,
)
from src.helpers.vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
)

if TYPE_CHECKING:
    from src.detours.detour_ai_augment.src.backend.helpers.data_models.validation_request import (  # noqa: E501
        BackendValidationRequestRecord,
    )

logger = logging.getLogger(__name__)


class _PushValidationError(RuntimeError):
    pass


class _ValidationPreparationError(RuntimeError):
    pass


class _CommitConfigFacts(FrozenStrictModel):
    timezone_name: StrictStr
    sample_seed: int
    codex_match_version: int


class _CommitEvaluationInputs(FrozenStrictModel):
    original_pull_response_record: PullResponseRecord
    namekey: NameKey
    config_facts: _CommitConfigFacts
    draw_number: LazyResultFactory[[], str, Exception]
    cas_codex_rollout_record: LazyResultFactory[[], CASCodexRolloutRecord, Exception]


class _RetryBaselineRow(FrozenStrictModel):
    namekey_json: StrictStr
    session_id_text: StrictStr
    attempt_id_text: StrictStr
    obligations_json: StrictStr


class _AppliedRetryAuditRow(FrozenStrictModel):
    submission_json: StrictStr
    assessment_json: StrictStr


class _DetourDbValidationReads(FrozenStrictModel):
    retry_baseline_exists: LazyResultFactory[[], bool, Exception]
    retry_baseline_row: LazyResultFactory[[], _RetryBaselineRow, Exception]
    applied_retry_audit_rows: LazyResultFactory[
        [UUID], tuple[_AppliedRetryAuditRow, ...], Exception
    ]
    output_identity_exists: LazyResultFactory[[], bool, Exception]


RETRY_EVIDENCE_SUBMISSION_EXAMPLE = L_FEI_FEI_RETRY_FIXTURE.submission.model_dump(
    by_alias=True,
    mode="json",
)
RETRY_SUBMISSION_PUBLIC_GUIDANCE = (
    Locale.EVIDENCE_RETRY_STANDARDIZED_VALUES
    + Locale.EVIDENCE_RETRY_EXAMPLE_TEMPLATE.format(
        example=json.dumps(
            RETRY_EVIDENCE_SUBMISSION_EXAMPLE,
            ensure_ascii=False,
            indent=2,
        )
    )
)

AIVM_WORKDIR = PurePosixPath("/home/ai/workdir")

APPENDWATCH_ARCHIVE_FILENAME_TEMPLATE = "appendwatch-tree.{attempt_id}.txt"
ALLOW_MULTIPLE_EVIDENCE_MATCHES = True
WEB_SEARCH_QUERY_ACTION = "search_query"
WEB_OPEN_ACTION = "open"
WEB_CLICK_ACTION = "click"
WEB_FIND_ACTION = "find"
WEB_RESPONSE_LENGTH_ARGUMENT = "response_length"
ELIGIBLE_WEB_ACTIONS = frozenset({
    WEB_SEARCH_QUERY_ACTION,
    WEB_OPEN_ACTION,
    WEB_CLICK_ACTION,
    WEB_FIND_ACTION,
})
CODEX_CALL_ID_KEY = "call_id"
CODEX_ARGUMENTS_KEY = "arguments"
CODEX_SESSION_ID_KEY = "session_id"
CODEX_TIMESTAMP_KEY = "timestamp"
CODEX_MODEL_KEY = "model"
CODEX_REASONING_EFFORT_KEY = "effort"
CODEX_ORIGINATOR_KEY = "originator"
CODEX_SOURCE_FIELD = "source"
CODEX_CLI_VERSION_KEY = "cli_version"
CODEX_MODEL_PROVIDER_KEY = "model_provider"
CODEX_OUTPUT_KEY = "output"
CODEX_TEXT_KEY = "text"
CODEX_NAMESPACE_KEY = "namespace"
CODEX_NAME_KEY = "name"
CODEX_ID_KEY = "id"
CODEX_RESULTS_KEY = "results"
CODEX_REF_ID_KEY = "ref_id"
CODEX_SESSION_META_TYPE = "session_meta"
CODEX_TURN_CONTEXT_TYPE = "turn_context"
CODEX_INPUT_TEXT_TYPE = "input_text"
CODEX_RESPONSE_ITEM_TYPE = "response_item"
CODEX_EVENT_MESSAGE_TYPE = "event_msg"
CODEX_FUNCTION_CALL_TYPE = "function_call"
CODEX_FUNCTION_CALL_OUTPUT_TYPE = "function_call_output"
CODEX_WEB_SEARCH_END_TYPE = "web_search_end"
CODEX_WEB_NAMESPACE = "web"
CODEX_WEB_FUNCTION_NAME = "run"
CODEX_TEXT_RESULT_TYPE = "text_result"
CODEX_TURN_REF_PREFIX = "turn"
SESSION_REASONING_EFFORT_KEY = "reasoning_effort"
HTTP_PUT_METHOD = "PUT"
HTTP_ACCEPT_HEADER = "Accept"
ROLLOUT_TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"
FCO_TIMESTAMP_TIMESPEC = "milliseconds"
PYDANTIC_ERROR_MESSAGE_KEY = "msg"
PYDANTIC_ERROR_LOCATION_KEY = "loc"
PYDANTIC_ERROR_TYPE_KEY = "type"
PYDANTIC_ERROR_INPUT_KEY = "input"
PYDANTIC_MISSING_ERROR_TYPE = "missing"
HTTP_ETAG_HEADER = "ETag"
HTTP_ETAG_SHA256_TEMPLATE = '"sha256:{sha256}"'
HTTP_ETAG_SHA256_PREFIX = '"sha256:'
HTTP_ETAG_SUFFIX = '"'
HTTP_INTERNAL_ERROR_RESPONSE = status.HTTP_500_INTERNAL_SERVER_ERROR
HTTP_BUSY_RESPONSE = status.HTTP_409_CONFLICT
EvidenceOutcome = Literal[  # type: ignore[valid-type]
    EVIDENCE_OUTCOME_V1_EXACT,
    EVIDENCE_OUTCOME_V2_NEAR,
    EVIDENCE_OUTCOME_UNMATCHED,
    EVIDENCE_OUTCOME_WITHDRAWN,
]
EVIDENCE_LOCATION_DEF: Callable[[str, int], str] = lambda field, index: (
    Locale.EVIDENCE_LOCATION_TEMPLATE.format(
        field=field,
        index=index,
    )
)
CODEX_REF_ID_PATTERN = rf"{re.escape(CODEX_TURN_REF_PREFIX)}[0-9]+[A-Za-z_]+[0-9]+"
CODEX_RESULT_SEPARATOR = "-" * 80
FOOTNOTE_CONTEXT_CHARACTERS = 160
DRAW_VALUE_SEPARATOR = ", "

EVIDENCE_RANDOM = Random()

STANDARDIZED_VALUE_FIELD = next(
    field
    for field in StandardizedFieldSubmission.model_fields
    if field not in FieldSubmission.model_fields
)
INITIAL_RESEARCHER_AUTHOR_STANDARDIZED = ResearcherAuthorStandardized(
    first_name=NOT_REPORTED_VALUE,
    last_name=NOT_REPORTED_VALUE,
    orcid=NOT_REPORTED_VALUE,
    openalex_id=NOT_REPORTED_VALUE,
)
INITIAL_PLACE_OF_RESIDENCE_STANDARDIZED = PlaceOfResidenceStandardized(
    place=NOT_REPORTED_VALUE,
    location=NOT_REPORTED_VALUE,
)
INITIAL_RACE_ETHNICITY_LANGUAGE_CULTURE_STANDARDIZED = (
    RaceEthnicityLanguageCultureStandardized(
        race=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
        ethnicity=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
        language=NOT_REPORTED_VALUE,
        culture=NOT_AVAILABLE_OR_APPLICABLE_VALUE,
    )
)
INITIAL_STANDARDIZED_VALUES: Mapping[str, StandardizedValue] = {
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: INITIAL_RESEARCHER_AUTHOR_STANDARDIZED,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: INITIAL_PLACE_OF_RESIDENCE_STANDARDIZED,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL: (
        INITIAL_RACE_ETHNICITY_LANGUAGE_CULTURE_STANDARDIZED
    ),
    KTP_AI_AUGMENT_GENDER_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_EDUCATION_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: NOT_REPORTED_VALUE,
    KTP_AI_AUGMENT_LINKS_COL: NOT_REPORTED_VALUE,
}
DRAW_NUMBER_COLUMN = DRAW_LABEL
FRAGMENT_TYPE_COLUMN = KTP_FRAGMENT_TYPE_COL
DOCX_ROW_FRAGMENT_TYPE = FragmentType.DOCX_ROW.value
ROLLOUT_LINE_FRAGMENT_TYPE = FragmentType.LINE_NUMBER.value


class _RetryEvidenceObligation(FrozenStrictModel):
    outcome: EvidenceOutcome
    excerpt: StrictStr | None = None
    url: StrictStr | None = None
    normalized_tokens: list[StrictStr] = Field(default_factory=list)


class _RetryFieldObligation(FrozenStrictModel):
    value: StrictStr
    evidence: list[_RetryEvidenceObligation]
    accepted: bool


class _RetryObligations(FrozenStrictModel):
    fields: dict[StrictStr, _RetryFieldObligation]


class _EvidenceCandidateAudit(FrozenStrictModel):
    ref_id: StrictStr
    call_id: StrictStr
    cite_text: StrictStr
    excerpt_position: int
    url: StrictStr


class _EvidenceItemAudit(FrozenStrictModel):
    field: StrictStr
    index: int
    outcome: EvidenceOutcome
    excerpt: StrictStr | None
    url: StrictStr | None
    normalized_tokens: list[StrictStr]
    candidates: list[_EvidenceCandidateAudit]


class _EvidenceAttemptAudit(FrozenStrictModel):
    items: list[_EvidenceItemAudit]


class _CodexTextResult(BaseModel):
    """Note `extra="ignore"`"""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    type: Literal["text_result"]
    domain: StrictStr | None = None
    ref_id: StrictStr
    snippet: StrictStr | None = None
    thumbnail_url: StrictStr | None = None
    title: StrictStr | None = None
    url: StrictStr | None = None

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if not self.ref_id.strip():
            raise ValueError(Locale.WEB_RESULT_REF_ID_NONBLANK)
        return self


class _EvidenceAssessmentError(_PushValidationError):
    def __init__(self, message: str, *, public_detail: str) -> None:
        self.public_detail = public_detail
        super().__init__(message)


class _MultipleEvidenceMatches(_PushValidationError):
    def __init__(self, excerpt: str) -> None:
        self.excerpt = excerpt
        super().__init__(Locale.MULTIPLE_EVIDENCE_MATCHES_TEMPLATE.format(excerpt=excerpt))


class _RolloutRecordLine(FrozenStrictModel):
    line_number: int = Field(ge=1)
    line_sha256: StrictStr
    line_value: dict[str, JsonValue]


class _EvidenceMatch(FrozenStrictModel):
    field: str
    evidence_number: int
    excerpt: str
    url: str
    ref_id: str
    call_id: str
    cite_text: str
    excerpt_position: int
    fco_timestamp: str
    arguments_json: str


class _EvidenceItemAssessment(FrozenStrictModel):
    field: str
    index: int
    evidence_number: int
    submission: EvidenceSubmission
    outcome: EvidenceOutcome
    match: _EvidenceMatch | None
    normalized_tokens: tuple[str, ...] = ()
    candidates: tuple[_EvidenceCandidate, ...] = ()


class _EvidenceAssessment(FrozenStrictModel):
    items: tuple[_EvidenceItemAssessment, ...]

    @property
    def validated(self) -> ValidatedEvidence:
        validated: ValidatedEvidence = {field: [] for field in AI_AUGMENT_EVIDENCE_COLUMNS}
        for item in self.items:
            if item.match is not None and item.outcome == EVIDENCE_OUTCOME_V1_EXACT:
                validated[item.field].append(item.match)
        return validated

    @property
    def exact_count(self) -> int:
        return sum(item.outcome == EVIDENCE_OUTCOME_V1_EXACT for item in self.items)

    @property
    def accepted(self) -> bool:
        return all(
            EVIDENCE_ITEMS_ACCEPTED_DEF(
                tuple(item.outcome for item in self.items if item.field == field)
            )
            for field in AI_AUGMENT_EVIDENCE_COLUMNS
        )


ValidatedEvidence = dict[str, list[_EvidenceMatch]]


def _seed_evidence_random(sample_seed: int) -> None:
    EVIDENCE_RANDOM.seed(sample_seed)


def parse_rollout(rollout_path: Path) -> tuple[_RolloutRecordLine, ...]:
    try:
        raw_lines = rollout_path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        raise _PushValidationError(Locale.ROLLOUT_UNREADABLE) from exc

    records: list[_RolloutRecordLine] = []
    for line_number, raw_line in enumerate(raw_lines, start=1):
        completed = raw_line.endswith(b"\n")
        encoded = raw_line[:-1] if completed else raw_line
        if encoded.endswith(b"\r"):
            encoded = encoded[:-1]
        try:
            value: object = json.loads(encoded.decode(TEXT_ENCODING))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if line_number == len(raw_lines) and not completed:
                break
            raise _PushValidationError(
                Locale.ROLLOUT_JSONL_MALFORMED_TEMPLATE.format(line_number=line_number)
            ) from exc
        if not isinstance(value, dict):
            raise _PushValidationError(
                Locale.ROLLOUT_LINE_NON_OBJECT_TEMPLATE.format(line_number=line_number)
            )
        rollout_value: dict[str, JsonValue] = value
        records.append(
            _RolloutRecordLine(
                line_number=line_number,
                line_sha256=hashlib.sha256(raw_line).hexdigest(),
                line_value=rollout_value,
            )
        )
    return tuple(records)


def _timestamp(value: object, *, label: str) -> str:
    raw = require_nonblank_text(
        value,
        _PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label)),
    )
    try:
        parsed = datetime.fromisoformat(raw.replace(ISO_8601_UTC_SUFFIX, ISO_8601_UTC_OFFSET))
    except ValueError as exc:
        raise _PushValidationError(Locale.TIMESTAMP_INVALID_TEMPLATE.format(label=label)) from exc
    if parsed.tzinfo is None:
        raise _PushValidationError(Locale.TIMESTAMP_TIMEZONE_MISSING_TEMPLATE.format(label=label))
    return raw


def _web_arguments(
    payload: Mapping[str, object], line_number: int,
) -> dict[str, object] | None:
    """Decode arguments; unsupported commands are ineligible, not corrupt evidence.

    Upstream SearchCommands permits multiple action keys. Our evidence subset
    allows any combination of supported actions, plus the response_length option.
    """
    call_id = require_nonblank_text(
        payload.get(CODEX_CALL_ID_KEY),
        _PushValidationError(
            Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=line_number)
        ),
    )
    arguments = payload.get(CODEX_ARGUMENTS_KEY)
    if not isinstance(arguments, str):
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_UNSUPPORTED_TEMPLATE.format(call_id=call_id)
        )
    try:
        decoded_value: object = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_MALFORMED_TEMPLATE.format(call_id=call_id)
        ) from exc
    if not isinstance(decoded_value, dict):
        raise _PushValidationError(
            Locale.WEB_CALL_ARGUMENTS_NON_OBJECT_TEMPLATE.format(call_id=call_id)
        )
    decoded: dict[str, object] = decoded_value
    if (
        decoded.keys() - ELIGIBLE_WEB_ACTIONS - {WEB_RESPONSE_LENGTH_ARGUMENT}
        or not any(decoded.get(action) for action in ELIGIBLE_WEB_ACTIONS)
    ):
        logger.info(Locale.WEB_CALL_EVIDENCE_INELIGIBLE_LOG, call_id, sorted(decoded))
        return None
    return decoded


def _session_metadata(
    records: tuple[_RolloutRecordLine, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str | None,
) -> _SessionMetadata:
    session_records = [
        record for record in records
        if record.line_value.get(CODEX_TYPE_KEY) == CODEX_SESSION_META_TYPE
    ]
    if len(session_records) != 1:
        raise _PushValidationError(Locale.SESSION_META_COUNT_INVALID)
    session_record = session_records[0]
    payload = session_record.line_value.get(CODEX_PAYLOAD_KEY)
    if not isinstance(payload, dict):
        raise _PushValidationError(Locale.SESSION_META_PAYLOAD_MALFORMED)
    session_id_text = require_nonblank_text(
        payload.get(CODEX_SESSION_ID_KEY),
        _PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID),
    )
    try:
        session_id = UUID(session_id_text)
    except ValueError as exc:
        raise _PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID) from exc
    if str(session_id) != session_id_text:
        raise _PushValidationError(Locale.SESSION_META_SESSION_ID_INVALID)
    payload_timestamp = _timestamp(
        payload.get(CODEX_TIMESTAMP_KEY),
        label=Locale.SESSION_META_PAYLOAD_LABEL,
    )
    response_timestamp = _timestamp(
        session_record.line_value.get(CODEX_TIMESTAMP_KEY),
        label=Locale.SESSION_META_RESPONSE_LABEL,
    )
    local_timestamp = datetime.fromisoformat(
        payload_timestamp.replace(ISO_8601_UTC_SUFFIX, ISO_8601_UTC_OFFSET)
    ).astimezone(
        ZoneInfo(timezone_name)
    )
    rollout_timestamp = local_timestamp.strftime(ROLLOUT_TIMESTAMP_FORMAT)
    rollout_filename = (
        f"{ROLLOUT_FILENAME_PREFIX}{rollout_timestamp}-{session_id}{ROLLOUT_FILENAME_SUFFIX}"
    )
    if configured_rollout_basename is not None and rollout_filename != configured_rollout_basename:
        raise _PushValidationError(Locale.SESSION_META_ROLLOUT_MISMATCH)

    turn_context_payload: Mapping[str, object] | None = None
    for record in records:
        candidate = record.line_value.get(CODEX_PAYLOAD_KEY)
        if (
            record.line_value.get(CODEX_TYPE_KEY) == CODEX_TURN_CONTEXT_TYPE
            and isinstance(candidate, dict)
        ):
            turn_context_payload = candidate
            break
    if turn_context_payload is None:
        raise _PushValidationError(Locale.TURN_CONTEXT_MISSING)
    model = turn_context_payload.get(CODEX_MODEL_KEY)
    reasoning_effort = turn_context_payload.get(CODEX_REASONING_EFFORT_KEY)
    try:
        summary_json = CodexRolloutRecord.build_summary_json({
            CODEX_ORIGINATOR_KEY: payload.get(CODEX_ORIGINATOR_KEY),
            CODEX_SOURCE_FIELD: payload.get(CODEX_SOURCE_FIELD),
            CODEX_CLI_VERSION_KEY: payload.get(CODEX_CLI_VERSION_KEY),
            CODEX_MODEL_PROVIDER_KEY: payload.get(CODEX_MODEL_PROVIDER_KEY),
            CODEX_MODEL_KEY: model,
            SESSION_REASONING_EFFORT_KEY: reasoning_effort,
            CODEX_SESSION_ID_KEY: str(session_id),
            CODEX_TIMESTAMP_KEY: response_timestamp,
        })
    except ValidationError as exc:
        raise _PushValidationError(Locale.SESSION_META_FIELDS_INCOMPLETE) from exc
    return _SessionMetadata(
        session_id=session_id,
        timestamp=response_timestamp,
        rollout_filename=rollout_filename,
        summary_json=summary_json,
    )


def _has_cite_marker(payload: Mapping[str, object]) -> bool:
    output = payload.get(CODEX_OUTPUT_KEY)
    marker_start = f"{CODEX_CITE_MARKER_PREFIX}turn"
    if isinstance(output, list):
        for block in output:
            if not isinstance(block, dict):
                continue
            block_text = block.get(CODEX_TEXT_KEY)
            if isinstance(block_text, str) and marker_start in block_text:
                return True
    elif isinstance(output, str):
        return marker_start in output
    return False


def _cited_fco_text(record: _RolloutRecordLine, payload: Mapping[str, object]) -> str:
    output = payload.get(CODEX_OUTPUT_KEY)
    if not isinstance(output, list) or len(output) != 1:
        raise _PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    output_block = output[0]
    if not isinstance(output_block, dict):
        raise _PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    output_text = output_block.get(CODEX_TEXT_KEY)
    if (
        output_block.get(CODEX_TYPE_KEY) != CODEX_INPUT_TEXT_TYPE
        or not isinstance(output_text, str)
    ):
        raise _PushValidationError(
            Locale.CITED_OUTPUT_BLOCK_INVALID_TEMPLATE.format(line_number=record.line_number)
        )
    return output_text


def build_rollout_index(
    records: tuple[_RolloutRecordLine, ...],
    *,
    timezone_name: str,
    configured_rollout_basename: str | None,
) -> _RolloutIndex:
    session = _session_metadata(
        records,
        timezone_name=timezone_name,
        configured_rollout_basename=configured_rollout_basename,
    )
    calls: dict[str, list[_RolloutRecordLine]] = {}
    events: dict[str, list[_RolloutRecordLine]] = {}
    cited_outputs: list[tuple[_RolloutRecordLine, Mapping[str, object]]] = []

    for record in records:
        value = record.line_value
        payload = value.get(CODEX_PAYLOAD_KEY)
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get(CODEX_TYPE_KEY)
        if (
            value.get(CODEX_TYPE_KEY) == CODEX_RESPONSE_ITEM_TYPE
            and payload_type == CODEX_FUNCTION_CALL_TYPE
            and payload.get(CODEX_NAMESPACE_KEY) == CODEX_WEB_NAMESPACE
            and payload.get(CODEX_NAME_KEY) == CODEX_WEB_FUNCTION_NAME
        ):
            call_id = require_nonblank_text(
                payload.get(CODEX_CALL_ID_KEY),
                _PushValidationError(
                    Locale.WEB_CALL_ID_INVALID_TEMPLATE.format(line_number=record.line_number)
                ),
            )
            calls.setdefault(call_id, []).append(record)
        elif (
            value.get(CODEX_TYPE_KEY) == CODEX_EVENT_MESSAGE_TYPE
            and payload_type == CODEX_WEB_SEARCH_END_TYPE
        ):
            call_id = require_nonblank_text(
                payload.get(CODEX_CALL_ID_KEY),
                _PushValidationError(
                    Locale.WEB_EVENT_CALL_ID_INVALID_TEMPLATE.format(line_number=record.line_number)
                ),
            )
            events.setdefault(call_id, []).append(record)
        elif (
            value.get(CODEX_TYPE_KEY) == CODEX_RESPONSE_ITEM_TYPE
            and payload_type == CODEX_FUNCTION_CALL_OUTPUT_TYPE
        ):
            if _has_cite_marker(payload):
                cited_outputs.append((record, payload))

    fc_rows: list[_CodexFcRow] = []
    fco_rows: list[_CodexFcoRow] = []
    turn_ref_rows: list[_CodexTurnRefRow] = []
    seen_fc_ids: set[str] = set()
    seen_fco_ids: set[str] = set()
    seen_call_ids: set[str] = set()
    for output_record, output_payload in cited_outputs:
        call_id = require_nonblank_text(
            output_payload.get(CODEX_CALL_ID_KEY),
            _PushValidationError(
                Locale.CITED_OUTPUT_IDS_INVALID_TEMPLATE.format(
                    line_number=output_record.line_number
                )
            ),
        )
        fco_id = require_nonblank_text(
            output_payload.get(CODEX_ID_KEY),
            _PushValidationError(
                Locale.CITED_OUTPUT_IDS_INVALID_TEMPLATE.format(
                    line_number=output_record.line_number
                )
            ),
        )
        if call_id in seen_call_ids or fco_id in seen_fco_ids:
            raise _PushValidationError(Locale.CITED_OUTPUT_IDS_DUPLICATE)
        seen_call_ids.add(call_id)
        seen_fco_ids.add(fco_id)
        fco_timestamp = _timestamp(
            output_record.line_value.get(CODEX_TIMESTAMP_KEY),
            label=Locale.FUNCTION_OUTPUT_LABEL_TEMPLATE.format(fco_id=fco_id),
        )

        matching_calls = calls.get(call_id, [])
        matching_events = events.get(call_id, [])
        if len(matching_calls) != 1 or len(matching_events) != 1:
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_COUNT_TEMPLATE.format(call_id=call_id)
            )
        call_record = matching_calls[0]
        event_record = matching_events[0]
        if not (call_record.line_number < event_record.line_number < output_record.line_number):
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_ORDER_TEMPLATE.format(call_id=call_id)
            )
        call_payload_value = call_record.line_value.get(CODEX_PAYLOAD_KEY)
        if not isinstance(call_payload_value, dict):
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_COUNT_TEMPLATE.format(call_id=call_id)
            )
        call_payload: Mapping[str, object] = call_payload_value
        fc_id = require_nonblank_text(
            call_payload.get(CODEX_ID_KEY),
            _PushValidationError(
                Locale.WEB_CALL_FC_ID_INVALID_TEMPLATE.format(call_id=call_id)
            ),
        )
        if fc_id in seen_fc_ids:
            raise _PushValidationError(
                Locale.WEB_CALL_FC_ID_INVALID_TEMPLATE.format(call_id=call_id)
            )
        seen_fc_ids.add(fc_id)
        arguments = _web_arguments(call_payload, call_record.line_number)
        if arguments is None:
            continue
        output_text = _cited_fco_text(output_record, output_payload)
        arguments_json = json.dumps(
            arguments,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )
        fc_rows.append(
            _CodexFcRow(
                timestamp=_timestamp(
                    call_record.line_value.get(CODEX_TIMESTAMP_KEY),
                    label=Locale.FUNCTION_CALL_LABEL_TEMPLATE.format(fc_id=fc_id),
                ),
                fc_id=fc_id,
                call_id=call_id,
                name=CODEX_WEB_FUNCTION_NAME,
                namespace=CODEX_WEB_NAMESPACE,
                arguments_json=arguments_json,
            )
        )
        fco_rows.append(
            _CodexFcoRow(
                timestamp=fco_timestamp,
                fco_id=fco_id,
                call_id=call_id,
            )
        )

        try:
            sections = codex_parse.extract_cite_sections(
                output_text,
                marker_prefix=CODEX_CITE_MARKER_PREFIX,
                marker_suffix=CODEX_CITE_MARKER_SUFFIX,
                ref_id_pattern=CODEX_REF_ID_PATTERN,
                result_separator=CODEX_RESULT_SEPARATOR,
            )
        except ValueError as exc:
            raise _PushValidationError(str(exc)) from exc
        event_payload_value = event_record.line_value.get(CODEX_PAYLOAD_KEY)
        if not isinstance(event_payload_value, dict):
            raise _PushValidationError(
                Locale.CITED_WEB_CHAIN_COUNT_TEMPLATE.format(call_id=call_id)
            )
        event_payload: Mapping[str, object] = event_payload_value
        results = event_payload.get(CODEX_RESULTS_KEY)
        if not isinstance(results, list):
            raise _PushValidationError(
                Locale.WEB_EVENT_RESULTS_UNSUPPORTED_TEMPLATE.format(call_id=call_id)
            )
        for section in sections:
            matching_results = [
                result
                for result in results
                if isinstance(result, dict)
                and result.get(CODEX_TYPE_KEY) == CODEX_TEXT_RESULT_TYPE
                and result.get(CODEX_REF_ID_KEY) == section.ref_id
            ]
            if len(matching_results) != 1:
                raise _PushValidationError(
                    Locale.CITATION_RESULT_COUNT_TEMPLATE.format(ref_id=section.ref_id)
                )
            try:
                result = _CodexTextResult.model_validate(matching_results[0])
            except ValidationError as exc:
                raise _PushValidationError(
                    Locale.CITATION_RESULT_METADATA_UNSUPPORTED_TEMPLATE.format(
                        ref_id=section.ref_id
                    )
                ) from exc
            result_url = result.url
            if (
                not isinstance(result_url, str)
                or not result_url.strip()
                or result_url != result_url.strip()
                or HAS_CONTROL_CHARACTER(result_url)
            ):
                continue
            turn_ref_rows.append(
                _CodexTurnRefRow(
                    ref_id=section.ref_id,
                    call_id=call_id,
                    domain=result.domain,
                    snippet=result.snippet,
                    thumbnail_url=result.thumbnail_url,
                    title=result.title,
                    url=result_url,
                    cite_text=section.text,
                )
            )

    return _RolloutIndex(
        session=session,
        fc_rows=tuple(fc_rows),
        fco_rows=tuple(fco_rows),
        turn_ref_rows=tuple(turn_ref_rows),
    )


def _render_fco_timestamp(value: datetime) -> str:
    return (
        value
        .astimezone(timezone.utc)
        .isoformat(timespec=FCO_TIMESTAMP_TIMESPEC)
        .replace(ISO_8601_UTC_OFFSET, ISO_8601_UTC_SUFFIX)
    )


def _normalized_evidence_tokens(excerpt: str) -> tuple[str, ...]:
    unaccented = unicodedata.normalize("NFKD", excerpt.lower())
    text = "".join(
        " " if unicodedata.category(character).startswith("P") or character.isspace()
        else "" if unicodedata.combining(character)
        else character
        for character in unaccented
    )
    return tuple(text.split())


def _evidence_candidates(
    rollout_index: _RolloutIndex,
    position_for: Callable[[_CodexTurnRefRow], int | None],
) -> tuple[_EvidenceCandidate, ...]:
    fc_by_call = {row.call_id: row for row in rollout_index.fc_rows}
    fco_by_call = {row.call_id: row for row in rollout_index.fco_rows}
    candidates: list[_EvidenceCandidate] = []
    for row in rollout_index.turn_ref_rows:
        position = position_for(row)
        if position is None:
            continue
        candidates.append(_EvidenceCandidate(
            ref_id=row.ref_id,
            call_id=row.call_id,
            cite_text=row.cite_text,
            excerpt_position=position,
            url=row.url,
            fco_timestamp=datetime.fromisoformat(
                fco_by_call[row.call_id].timestamp.replace(ISO_8601_UTC_SUFFIX, ISO_8601_UTC_OFFSET)
            ),
            arguments_json=fc_by_call[row.call_id].arguments_json,
        ))
    return tuple(candidates)


def _exact_evidence_candidates(
    rollout_index: _RolloutIndex,
    *,
    excerpt: str,
) -> tuple[_EvidenceCandidate, ...]:
    return _evidence_candidates(
        rollout_index,
        lambda row: position + 1 if (position := row.cite_text.find(excerpt)) >= 0 else None,
    )


def _near_evidence_candidates(
    rollout_index: _RolloutIndex,
    *,
    url: str,
    submitted_tokens: tuple[str, ...],
) -> tuple[_EvidenceCandidate, ...]:
    if not submitted_tokens:
        return ()

    def position_for(row: _CodexTurnRefRow) -> int | None:
        if row.url != url:
            return None
        tokens = _normalized_evidence_tokens(row.cite_text)
        width = len(submitted_tokens)
        return next(
            (
                index + 1
                for index in range(len(tokens) - width + 1)
                if tokens[index:index + width] == submitted_tokens
            ),
            None,
        )

    return _evidence_candidates(rollout_index, position_for)


def _candidate_match(
    candidate: _EvidenceCandidate,
    *,
    field: str,
    evidence_number: int,
    evidence: WebSearchExcerpt,
) -> _EvidenceMatch:
    arguments_json = candidate.arguments_json
    if not isinstance(arguments_json, str):
        arguments_json = json.dumps(
            arguments_json,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )
    return _EvidenceMatch(
        field=field,
        evidence_number=evidence_number,
        excerpt=evidence.excerpt,
        url=evidence.url,
        ref_id=candidate.ref_id,
        call_id=candidate.call_id,
        cite_text=candidate.cite_text,
        excerpt_position=candidate.excerpt_position - 1,
        fco_timestamp=_render_fco_timestamp(candidate.fco_timestamp),
        arguments_json=arguments_json,
    )


def assess_submission_evidence(
    rollout_index: _RolloutIndex,
    submission_payload: Submission | StandardizedSubmission,
    *,
    codex_match_version: int,
) -> _EvidenceAssessment:
    assessments: list[_EvidenceItemAssessment] = []
    evidence_number = 0
    for field, field_submission in submission_payload.evidence_items():
        for index, evidence in enumerate(field_submission.web_search_excerpts):
            evidence_number += 1
            if isinstance(evidence, EvidenceWithdrawal):
                assessments.append(
                    _EvidenceItemAssessment(
                        field=field,
                        index=index,
                        evidence_number=evidence_number,
                        submission=evidence,
                        outcome=EVIDENCE_OUTCOME_WITHDRAWN,
                        match=None,
                    )
                )
                continue

            exact_candidates = _exact_evidence_candidates(
                rollout_index,
                excerpt=evidence.excerpt,
            )
            exact_url_candidates = tuple(
                candidate for candidate in exact_candidates if candidate.url == evidence.url
            )
            if exact_url_candidates:
                if len(exact_url_candidates) > 1 and not ALLOW_MULTIPLE_EVIDENCE_MATCHES:
                    raise _MultipleEvidenceMatches(evidence.excerpt)
                candidate = (
                    EVIDENCE_RANDOM.choice(exact_url_candidates)
                    if len(exact_url_candidates) > 1
                    else exact_url_candidates[0]
                )
                assessments.append(
                    _EvidenceItemAssessment(
                        field=field,
                        index=index,
                        evidence_number=evidence_number,
                        submission=evidence,
                        outcome=EVIDENCE_OUTCOME_V1_EXACT,
                        match=_candidate_match(
                            candidate,
                            field=field,
                            evidence_number=evidence_number,
                            evidence=evidence,
                        ),
                        candidates=exact_url_candidates,
                    )
                )
                continue

            normalized_tokens: tuple[str, ...] = ()
            near_candidates: tuple[_EvidenceCandidate, ...] = ()
            if codex_match_version == 2:
                normalized_tokens = _normalized_evidence_tokens(evidence.excerpt)
                near_candidates = _near_evidence_candidates(
                    rollout_index,
                    url=evidence.url,
                    submitted_tokens=normalized_tokens,
                )
            assessments.append(
                _EvidenceItemAssessment(
                    field=field,
                    index=index,
                    evidence_number=evidence_number,
                    submission=evidence,
                    outcome=(
                        EVIDENCE_OUTCOME_V2_NEAR if near_candidates else EVIDENCE_OUTCOME_UNMATCHED
                    ),
                    match=None,
                    normalized_tokens=normalized_tokens,
                    candidates=near_candidates or exact_candidates,
                )
            )
    return _EvidenceAssessment(items=tuple(assessments))


def _retry_evidence_obligation(
    item: _EvidenceItemAssessment,
) -> _RetryEvidenceObligation:
    if isinstance(item.submission, WebSearchExcerpt):
        excerpt = item.submission.excerpt
        url = item.submission.url
    else:
        excerpt = None
        url = None
    return _RetryEvidenceObligation(
        outcome=item.outcome,
        excerpt=excerpt,
        url=url,
        normalized_tokens=list(item.normalized_tokens),
    )


def _retry_obligations_from_assessment(
    submission_payload: Submission | StandardizedSubmission,
    assessment: _EvidenceAssessment,
) -> _RetryObligations:
    fields: dict[str, _RetryFieldObligation] = {}
    for field, field_submission in submission_payload.evidence_items():
        evidence = [
            _retry_evidence_obligation(item) for item in assessment.items if item.field == field
        ]
        fields[field] = _RetryFieldObligation(
            value=field_submission.value,
            evidence=evidence,
            accepted=EVIDENCE_ITEMS_ACCEPTED_DEF(tuple(item.outcome for item in evidence)),
        )
    return _RetryObligations(fields=fields)


def _assessment_audit(assessment: _EvidenceAssessment) -> _EvidenceAttemptAudit:
    items: list[_EvidenceItemAudit] = []
    for item in assessment.items:
        if isinstance(item.submission, WebSearchExcerpt):
            excerpt = item.submission.excerpt
            url = item.submission.url
        else:
            excerpt = None
            url = None
        items.append(
            _EvidenceItemAudit(
                field=item.field,
                index=item.index,
                outcome=item.outcome,
                excerpt=excerpt,
                url=url,
                normalized_tokens=list(item.normalized_tokens),
                candidates=[
                    _EvidenceCandidateAudit(
                        ref_id=candidate.ref_id,
                        call_id=candidate.call_id,
                        cite_text=candidate.cite_text,
                        excerpt_position=candidate.excerpt_position,
                        url=candidate.url,
                    )
                    for candidate in item.candidates
                ],
            )
        )
    return _EvidenceAttemptAudit(items=items)


def _log_evidence_assessment(
    assessment: _EvidenceAssessment,
    *,
    commit_request_record: BackendCommitRequestRecord,
) -> None:
    for item in assessment.items:
        if isinstance(item.submission, WebSearchExcerpt):
            excerpt = item.submission.excerpt
            url = item.submission.url
        else:
            excerpt = None
            url = None
        candidate_diagnostics = tuple(
            (
                candidate.ref_id,
                candidate.call_id,
                candidate.cite_text,
                candidate.excerpt_position,
                candidate.url,
            )
            for candidate in item.candidates
        )
        logger.info(
            Locale.EVIDENCE_ITEM_ASSESSMENT_LOG,
            commit_request_record.record_id,
            item.field,
            item.index,
            item.outcome,
            excerpt,
            url,
            candidate_diagnostics,
        )


def _assessment_public_detail(
    assessment: _EvidenceAssessment,
    *,
    violations: Sequence[str] = (),
    include_retry_contract: bool = False,
) -> str:
    total = len(assessment.items)
    outcomes = tuple(item.outcome for item in assessment.items)
    progress_template = (
        Locale.EVIDENCE_GOOD_PROGRESS_TEMPLATE
        if EVIDENCE_PROGRESS_PRAISE_DEF(outcomes)
        else Locale.EVIDENCE_PROGRESS_TEMPLATE
    )
    lines = [
        progress_template.format(
            exact=assessment.exact_count,
            total=total,
        )
    ]
    non_exact_items = tuple(
        item for item in assessment.items if item.outcome != EVIDENCE_OUTCOME_V1_EXACT
    )
    if non_exact_items:
        lines.append(Locale.EVIDENCE_REVIEW_HEADER)
    for item in non_exact_items:
        location = EVIDENCE_LOCATION_DEF(item.field, item.index)
        if item.outcome == EVIDENCE_OUTCOME_V2_NEAR:
            lines.append(Locale.EVIDENCE_NEAR_ITEM_TEMPLATE.format(location=location))
        elif item.outcome == EVIDENCE_OUTCOME_UNMATCHED:
            lines.append(Locale.EVIDENCE_UNMATCHED_ITEM_TEMPLATE.format(location=location))
        elif item.outcome == EVIDENCE_OUTCOME_WITHDRAWN:
            lines.append(Locale.EVIDENCE_WITHDRAWN_ITEM_TEMPLATE.format(location=location))
    if violations:
        lines.append(
            Locale.EVIDENCE_RETRY_VIOLATION_HEADER
            if len(violations) == 1
            else Locale.EVIDENCE_RETRY_VIOLATIONS_HEADER_TEMPLATE.format(count=len(violations))
        )
        lines.extend(f"- {violation}" for violation in violations)
    lines.append(Locale.EVIDENCE_RETRY_INSTRUCTION)
    if include_retry_contract:
        lines.append(RETRY_SUBMISSION_PUBLIC_GUIDANCE)
    return "\n".join(lines)


def _obligation_item_is_unchanged(
    previous: _RetryEvidenceObligation,
    current: EvidenceSubmission,
) -> bool:
    if previous.outcome == EVIDENCE_OUTCOME_V1_EXACT:
        return (
            isinstance(current, WebSearchExcerpt)
            and current.excerpt == previous.excerpt
            and current.url == previous.url
        )
    return previous.outcome == EVIDENCE_OUTCOME_WITHDRAWN and isinstance(
        current, EvidenceWithdrawal
    )


def _apply_retry_obligations(
    submission: StandardizedSubmission,
    assessment: _EvidenceAssessment,
    previous: _RetryObligations,
) -> tuple[_RetryObligations, tuple[str, ...]]:
    next_fields: dict[str, _RetryFieldObligation] = {}
    violations: list[str] = []
    assessed_items = {(item.field, item.index): item for item in assessment.items}
    for field, field_submission in submission.evidence_items():
        previous_field = previous.fields[field]
        current_evidence = field_submission.web_search_excerpts
        if previous_field.accepted:
            unchanged = (
                field_submission.value == previous_field.value
                and len(current_evidence) == len(previous_field.evidence)
                and all(
                    _obligation_item_is_unchanged(previous_item, current_item)
                    for previous_item, current_item in zip(
                        previous_field.evidence,
                        current_evidence,
                        strict=True,
                    )
                )
            )
            if not unchanged:
                violations.append(
                    Locale.EVIDENCE_ACCEPTED_FIELD_IMMUTABLE_TEMPLATE.format(immutable=field)
                )
            next_fields[field] = previous_field
            continue

        if len(current_evidence) < len(previous_field.evidence):
            violations.append(Locale.EVIDENCE_COUNT_DECREASED_TEMPLATE.format(field=field))

        next_evidence: list[_RetryEvidenceObligation] = []
        withdrew_item = False
        for index, previous_item in enumerate(previous_field.evidence):
            if index >= len(current_evidence):
                next_evidence.append(previous_item)
                continue
            current_item = current_evidence[index]
            assessment_item = assessed_items[(field, index)]
            location = EVIDENCE_LOCATION_DEF(field, index)
            if previous_item.outcome == EVIDENCE_OUTCOME_V1_EXACT:
                if not _obligation_item_is_unchanged(previous_item, current_item):
                    violations.append(
                        Locale.EVIDENCE_EXACT_IMMUTABLE_TEMPLATE.format(immutable=location)
                    )
                next_evidence.append(previous_item)
                continue
            if previous_item.outcome == EVIDENCE_OUTCOME_V2_NEAR:
                if isinstance(current_item, EvidenceWithdrawal):
                    violations.append(
                        Locale.EVIDENCE_WITHDRAWAL_NOT_ALLOWED_TEMPLATE.format(location=location)
                    )
                    next_evidence.append(previous_item)
                    continue
                current_tokens = assessment_item.normalized_tokens
                if assessment_item.outcome == EVIDENCE_OUTCOME_V1_EXACT:
                    current_tokens = _normalized_evidence_tokens(current_item.excerpt)
                if (
                    current_item.url != previous_item.url
                    or list(current_tokens) != previous_item.normalized_tokens
                ):
                    violations.append(
                        Locale.EVIDENCE_MINOR_CHANGE_ONLY_TEMPLATE.format(location=location)
                    )
                    next_evidence.append(previous_item)
                    continue
                if assessment_item.outcome not in {
                    EVIDENCE_OUTCOME_V1_EXACT,
                    EVIDENCE_OUTCOME_V2_NEAR,
                }:
                    violations.append(
                        Locale.EVIDENCE_MINOR_CHANGE_ONLY_TEMPLATE.format(location=location)
                    )
                    next_evidence.append(previous_item)
                    continue
                next_evidence.append(_retry_evidence_obligation(assessment_item))
                continue
            if previous_item.outcome == EVIDENCE_OUTCOME_UNMATCHED:
                if isinstance(current_item, EvidenceWithdrawal):
                    withdrew_item = True
                next_evidence.append(_retry_evidence_obligation(assessment_item))
                continue
            if not isinstance(current_item, EvidenceWithdrawal):
                violations.append(
                    Locale.EVIDENCE_WITHDRAWAL_NOT_ALLOWED_TEMPLATE.format(location=location)
                )
            next_evidence.append(previous_item)

        for index in range(len(previous_field.evidence), len(current_evidence)):
            assessment_item = assessed_items[(field, index)]
            if isinstance(assessment_item.submission, EvidenceWithdrawal):
                violations.append(Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE)
            next_evidence.append(_retry_evidence_obligation(assessment_item))

        if withdrew_item and field_submission.value == previous_field.value:
            violations.append(
                Locale.EVIDENCE_WITHDRAWAL_VALUE_UNCHANGED_TEMPLATE.format(field=field)
            )
        next_fields[field] = _RetryFieldObligation(
            value=field_submission.value,
            evidence=next_evidence,
            accepted=EVIDENCE_ITEMS_ACCEPTED_DEF(tuple(item.outcome for item in next_evidence)),
        )
    return _RetryObligations(fields=next_fields), tuple(violations)


def _assessment_from_audit(
    submission: StandardizedSubmission,
    audit: _EvidenceAttemptAudit,
) -> _EvidenceAssessment:
    submission_fields = dict(submission.evidence_items())
    items: list[_EvidenceItemAssessment] = []
    for evidence_number, audit_item in enumerate(audit.items, start=1):
        evidence = submission_fields[audit_item.field].web_search_excerpts[audit_item.index]
        items.append(
            _EvidenceItemAssessment(
                field=audit_item.field,
                index=audit_item.index,
                evidence_number=evidence_number,
                submission=evidence,
                outcome=audit_item.outcome,
                match=None,
                normalized_tokens=tuple(audit_item.normalized_tokens),
            )
        )
    return _EvidenceAssessment(items=tuple(items))


def _derive_retry_obligations(
    *,
    baseline_json: str,
    baseline_attempt_id: UUID,
    db_reads: _DetourDbValidationReads,
) -> _RetryObligations:
    try:
        obligations = _RetryObligations.model_validate_json(baseline_json)
        rows, error = db_reads.applied_retry_audit_rows(baseline_attempt_id)
        if error is not None:
            assert rows is None
            raise error
        assert rows is not None
        for row in rows:
            submission = StandardizedSubmission.model_validate_with_http_records(
                row.submission_json
            )
            assessment = _assessment_from_audit(
                submission,
                _EvidenceAttemptAudit.model_validate_json(row.assessment_json),
            )
            obligations, violations = _apply_retry_obligations(
                submission,
                assessment,
                obligations,
            )
            if violations:
                raise _ValidationPreparationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED)
        return obligations
    except (IndexError, KeyError, ValidationError) as exc:
        raise _ValidationPreparationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED) from exc


def _process_retry_attempt(
    *,
    commit_request_record: BackendCommitRequestRecord,
    namekey: NameKey,
    submission_payload: Submission | StandardizedSubmission,
    assessment: _EvidenceAssessment,
    db_reads: _DetourDbValidationReads,
) -> tuple[tuple[str, ...], _ValidationProjection]:
    session_id = commit_request_record.commit_request_body.codex_session_record.session_id
    assert session_id is not None
    session_id_text = str(session_id)
    namekey_json = namekey.to_json_key()
    initial_obligations = _retry_obligations_from_assessment(
        submission_payload,
        assessment,
    )
    submission_json = submission_payload.model_dump_json(by_alias=True)
    assessment_json = _assessment_audit(assessment).model_dump_json()
    baseline_row, error = db_reads.retry_baseline_row()
    if error is not None:
        assert baseline_row is None
        raise error

    violations: tuple[str, ...] = ()
    baseline_obligations_json = None
    if baseline_row is None:
        if not assessment.accepted:
            baseline_obligations_json = initial_obligations.model_dump_json()
            violations = tuple(
                Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE
                for item in assessment.items
                if item.outcome == EVIDENCE_OUTCOME_WITHDRAWN
            )
    else:
        if (
            baseline_row.namekey_json != namekey_json
            or baseline_row.session_id_text != session_id_text
        ):
            raise _PushValidationError(Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH)
        try:
            baseline_attempt_id = UUID(baseline_row.attempt_id_text)
        except ValueError as exc:
            raise _PushValidationError(
                Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH
            ) from exc
        if str(baseline_attempt_id) != baseline_row.attempt_id_text:
            raise _PushValidationError(
                Locale.EVIDENCE_RETRY_IDENTITY_MISMATCH
            )
        obligations = _derive_retry_obligations(
            baseline_json=baseline_row.obligations_json,
            baseline_attempt_id=baseline_attempt_id,
            db_reads=db_reads,
        )
        if not isinstance(submission_payload, StandardizedSubmission):
            raise _ValidationPreparationError(Locale.EVIDENCE_AUDIT_REPLAY_FAILED)
        _next_obligations, violations = _apply_retry_obligations(
            submission_payload,
            assessment,
            obligations,
        )

    applied = not violations
    accepted = assessment.accepted and applied
    return violations, _ValidationProjection(
        commit_request_record=commit_request_record,
        baseline_obligations_json=baseline_obligations_json,
        submission_json=submission_json,
        assessment_json=assessment_json,
        applied=applied,
        accepted=accepted,
    )


def _rollout_ref_urls(
    rollout_index: _RolloutIndex,
) -> dict[str, str]:
    rows_by_ref: dict[str, set[tuple[str, str]]] = {}
    for row in rollout_index.turn_ref_rows:
        rows_by_ref.setdefault(row.ref_id, set()).add((row.call_id, row.url))
    return {
        ref_id: next(iter(ref_rows))[1]
        for ref_id, ref_rows in rows_by_ref.items()
        if len(ref_rows) == 1
    }


def validate_submission_evidence(
    rollout_index: _RolloutIndex,
    submission_payload: Submission | StandardizedSubmission,
    *,
    codex_match_version: int = 1,
) -> ValidatedEvidence:
    assessment = assess_submission_evidence(
        rollout_index,
        submission_payload,
        codex_match_version=codex_match_version,
    )
    if assessment.accepted:
        return assessment.validated
    failed = next(item for item in assessment.items if item.outcome != EVIDENCE_OUTCOME_V1_EXACT)
    if isinstance(failed.submission, EvidenceWithdrawal):
        raise _PushValidationError(Locale.EVIDENCE_WITHDRAWAL_WITHOUT_BASELINE)
    detail_template = (
        Locale.EVIDENCE_URL_MISMATCH_TEMPLATE
        if failed.candidates
        else Locale.EVIDENCE_NO_MATCH_TEMPLATE
    )
    raise _PushValidationError(
        detail_template.format(
            field=failed.field,
            excerpt=failed.submission.excerpt,
            url=failed.submission.url,
        )
    )


def _failed_post_commit_validation(
    *,
    commit_request_record: BackendCommitRequestRecord,
    stage: BackendLifecycle,
    error: Exception,
) -> tuple[PostCommitValidation, _ValidationProjection]:
    logger.error(
        Locale.POST_COMMIT_VALIDATION_FAILED_LOG,
        commit_request_record.record_id,
        stage,
        error,
    )
    return (
        PostCommitValidation(
            stage=stage,
            result=BackendLifecycle.CONFIGURATION_ERROR,
            detail=Locale.CONFIGURATION_ERROR_DETAIL,
            submission_type=None,
            submission=None,
        ),
        _ValidationProjection(commit_request_record=commit_request_record),
    )


def render_codex_values(
    submission: StandardizedSubmission,
    evidence: ValidatedEvidence,
    *,
    attempt_timestamp: datetime,
    argument_ref_urls: Mapping[str, str],
) -> dict[str, str | None]:
    rendered: dict[str, str | None] = {}
    ordered_matches: list[_EvidenceMatch] = []
    standardized_columns = dict(AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS)
    for column, field_submission in submission.evidence_items():
        matches = evidence[column]
        ordered_matches.extend(matches)
        rendered[column] = codex_parse.render_ai_value(
            field_submission.value,
            tuple(match.evidence_number for match in matches),
        )
        standardized_value = field_submission.model_dump(mode="json")[STANDARDIZED_VALUE_FIELD]
        rendered[standardized_columns[column]] = json.dumps(
            standardized_value,
            ensure_ascii=False,
            separators=COMPACT_JSON_SEPARATORS,
        )
    rendered[KTP_AI_AUGMENT_FOOTNOTES_COL] = "\n".join(
        codex_parse.render_footnote(
            number=match.evidence_number,
            cite_text=match.cite_text,
            citation_marker=(f"{CODEX_CITE_MARKER_PREFIX}{match.ref_id}{CODEX_CITE_MARKER_SUFFIX}"),
            marker_prefix=CODEX_CITE_MARKER_PREFIX,
            marker_suffix=CODEX_CITE_MARKER_SUFFIX,
            excerpt=match.excerpt,
            excerpt_position=match.excerpt_position,
            context_characters=FOOTNOTE_CONTEXT_CHARACTERS,
            fco_timestamp=match.fco_timestamp,
            url=match.url,
        )
        for match in ordered_matches
    )
    rendered[KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL] = "\n".join(
        codex_parse.render_footnote_argument(
            match.evidence_number,
            match.arguments_json,
            argument_ref_urls,
            ref_id_pattern=CODEX_REF_ID_PATTERN,
        )
        for match in ordered_matches
    )
    rendered[KTP_AI_AUGMENT_COMMENTS_COL] = (
        None
        if submission.comments is None
        else codex_parse.render_comment(
            submission.comments.value,
            _render_fco_timestamp(attempt_timestamp),
        )
    )
    return rendered


def _standardized_initial_submission(
    submission: Submission,
) -> StandardizedSubmission:
    return StandardizedSubmission.model_validate({
        KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL: ResearcherAuthorSubmission(
            value=submission.researcher_author.value,
            web_search_excerpts=submission.researcher_author.web_search_excerpts,
            standardized_value=INITIAL_RESEARCHER_AUTHOR_STANDARDIZED,
        ),
        KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL: PlaceOfResidenceSubmission(
            value=submission.place_of_residence.value,
            web_search_excerpts=submission.place_of_residence.web_search_excerpts,
            standardized_value=INITIAL_PLACE_OF_RESIDENCE_STANDARDIZED,
        ),
        KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL: (
            RaceEthnicityLanguageCultureSubmission(
                value=submission.race_ethnicity_language_culture.value,
                web_search_excerpts=(
                    submission.race_ethnicity_language_culture.web_search_excerpts
                ),
                standardized_value=(
                    INITIAL_RACE_ETHNICITY_LANGUAGE_CULTURE_STANDARDIZED
                ),
            )
        ),
        KTP_AI_AUGMENT_GENDER_COL: GenderSubmission(
            value=submission.gender.value,
            web_search_excerpts=submission.gender.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL: AgeFirstPublicationSubmission(
            value=submission.age_first_publication.value,
            web_search_excerpts=submission.age_first_publication.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_EDUCATION_COL: EducationSubmission(
            value=submission.education.value,
            web_search_excerpts=submission.education.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL: AcademicPositionsSubmission(
            value=submission.academic_positions.value,
            web_search_excerpts=submission.academic_positions.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL: SocialCapitalSubmission(
            value=submission.social_capital.value,
            web_search_excerpts=submission.social_capital.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_LINKS_COL: ResearcherLinksSubmission(
            value=submission.links.value,
            web_search_excerpts=submission.links.web_search_excerpts,
            standardized_value=NOT_REPORTED_VALUE,
        ),
        KTP_AI_AUGMENT_COMMENTS_COL: submission.comments,
    })


def _accepted_output_row(
    *,
    submission: StandardizedSubmission,
    evidence: ValidatedEvidence,
    namekey: NameKey,
    draw_number: str,
    rollout_index: _RolloutIndex,
    cas_codex_rollout_record: CASCodexRolloutRecord,
    commit_request_record: BackendCommitRequestRecord,
    attempt_timestamp: datetime,
) -> tuple[tuple[str, str | int | None], ...]:
    commit_request_body = commit_request_record.request_body
    assert commit_request_body is not None
    commit_request_record_id = str(commit_request_record.record_id)
    rendered = render_codex_values(
        submission,
        evidence,
        attempt_timestamp=attempt_timestamp,
        argument_ref_urls=_rollout_ref_urls(rollout_index),
    )
    output_row: dict[str, str | int | None] = {
        KTP_NAMEKEY_COL: namekey.to_json_key(),
        KTP_FILENAME_COL: rollout_index.session.rollout_filename,
        KTP_FRAGMENT_COL: cas_codex_rollout_record.line_count,
        KTP_FRAGMENT_TYPE_COL: ROLLOUT_LINE_FRAGMENT_TYPE,
        DRAW_LABEL: draw_number,
        KTP_FIRST_NAME_COL: namekey.first_name,
        KTP_LAST_NAME_COL: namekey.last_name,
        KTP_AI_AUGMENT_COMMIT_REQUEST_RECORD_ID_COL: commit_request_record_id,
        KTP_AI_AUGMENT_VALIDATION_RECORD_ID_COL: None,
        KTP_AI_AUGMENT_RUN_OUTCOME_RECORD_ID_COL: None,
        KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_RECORD_COL: None,
        KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL: commit_request_body,
        KTP_AI_AUGMENT_SESSION_METADATA_COL: rollout_index.session.summary_json,
        **rendered,
    }

    return tuple(output_row.items())


def _execute_attempt(
    *,
    commit_request_record: BackendCommitRequestRecord,
    cas_codex_rollout_record: CASCodexRolloutRecord,
    inputs: _CommitEvaluationInputs,
    db_reads: _DetourDbValidationReads,
) -> tuple[PostCommitValidation, _ValidationProjection]:
    commit_request_body = commit_request_record.request_body
    body = commit_request_record.commit_request_body
    push_request_body = body.push_response_record.request_body
    session_id = body.codex_session_record.session_id
    appendwatch_report = body.codex_session_record.appendwatch_report_record
    rollout_basename = PurePosixPath(source_key_from_header_value(
        commit_request_record.request_headers.get(SOURCE_KEY_HEADER)
    )[0])
    assert commit_request_body is not None
    assert push_request_body is not None
    assert session_id is not None
    assert appendwatch_report is not None

    attempt_timestamp = datetime.fromtimestamp(
        commit_request_record.record_id.time / MILLISECONDS_PER_SECOND,
        tz=timezone.utc,
    )
    retry_submission_expected = False
    stage = BackendLifecycle.APPENDWATCH_REPORT_VALIDATION
    submission_payload: Submission | StandardizedSubmission | None = None
    rollout_index: _RolloutIndex | None = None
    retry_projection = _ValidationProjection(commit_request_record=commit_request_record)
    output_row: tuple[tuple[str, str | int | None], ...] | None = None

    def result(
        *,
        validation_result: BackendLifecycle,
        detail: str | None,
        error: Exception | None,
    ) -> tuple[PostCommitValidation, _ValidationProjection]:
        post_commit_validation = PostCommitValidation(
            stage=stage,
            result=validation_result,
            detail=detail,
            submission_type=(
                None if submission_payload is None
                else STANDARDIZED_SUBMISSION_TYPE
                if isinstance(submission_payload, StandardizedSubmission)
                else SUBMISSION_TYPE
            ),
            submission=(
                None if submission_payload is None
                else submission_payload.model_dump(mode="json", by_alias=True)
            ),
        )
        _log_post_commit_validation(
            body.push_response_record,
            post_commit_validation,
            error,
        )
        assert retry_projection.commit_request_record is commit_request_record
        return post_commit_validation, replace(
            retry_projection,
            rollout_index=rollout_index,
            accepted=(
                retry_projection.accepted
                if validation_result is BackendLifecycle.ACCEPTED
                else False if retry_projection.accepted is not None else None
            ),
            output_row=(output_row if validation_result is BackendLifecycle.ACCEPTED else None),
        )

    with tempfile.TemporaryDirectory() as temporary_directory:
        attempt_dir = Path(temporary_directory)
        try:
            report_path = attempt_dir / APPENDWATCH_ARCHIVE_FILENAME_TEMPLATE.format(
                attempt_id=commit_request_record.record_id
            )
            report_path.write_bytes(appendwatch_report.decoded_bytes())
            try:
                parse_appendwatch_report(report_path, rollout_basename)
            except AppendwatchReportError as exc:
                raise _PushValidationError(str(exc)) from exc
            stage = BackendLifecycle.ROLLOUT_INDEX
            rollout_index = build_rollout_index(
                parse_rollout(cas_codex_rollout_record.cas_path),
                timezone_name=inputs.config_facts.timezone_name,
                configured_rollout_basename=rollout_basename.name,
            )
            if rollout_index.session.session_id != session_id:
                raise _PushValidationError(Locale.CONFIGURED_SESSION_MISMATCH)
            stage = BackendLifecycle.PYDANTIC_VALIDATION
            retry_baseline_exists, error = db_reads.retry_baseline_exists()
            if error is not None:
                assert retry_baseline_exists is None
                raise error
            assert retry_baseline_exists is not None
            retry_submission_expected = retry_baseline_exists
            submission_payload = (
                StandardizedSubmission.model_validate_with_http_records(push_request_body)
                if retry_submission_expected
                else Submission.model_validate_with_http_records(push_request_body)
            )

            stage = BackendLifecycle.DUCKDB_EVIDENCE_VALIDATION
            _seed_evidence_random(inputs.config_facts.sample_seed)
            evidence_assessment = assess_submission_evidence(
                rollout_index,
                submission_payload,
                codex_match_version=inputs.config_facts.codex_match_version,
            )
            _log_evidence_assessment(
                evidence_assessment,
                commit_request_record=commit_request_record,
            )
            retry_violations, retry_projection = _process_retry_attempt(
                commit_request_record=commit_request_record,
                namekey=inputs.namekey,
                submission_payload=submission_payload,
                assessment=evidence_assessment,
                db_reads=db_reads,
            )
            assert retry_projection.commit_request_record is commit_request_record
            if not evidence_assessment.accepted or retry_violations:
                raise _EvidenceAssessmentError(
                    Locale.EVIDENCE_SUBMISSION_REJECTED,
                    public_detail=_assessment_public_detail(
                        evidence_assessment,
                        violations=retry_violations,
                        include_retry_contract=True,
                    ),
                )
            accepted_submission = (
                submission_payload
                if isinstance(submission_payload, StandardizedSubmission)
                else _standardized_initial_submission(submission_payload)
            )

            stage = BackendLifecycle.RESEARCHER_RESOLUTION
            draw_number, error = inputs.draw_number()
            if error is not None:
                assert draw_number is None
                raise error
            if draw_number is None:
                raise _ValidationPreparationError(Locale.CONFIGURED_NAMEKEY_NOT_FOUND)

            stage = BackendLifecycle.INNERDICT_AND_CARD
            submission_payload = accepted_submission
            output_row = _accepted_output_row(
                submission=accepted_submission,
                evidence=evidence_assessment.validated,
                namekey=inputs.namekey,
                draw_number=draw_number,
                rollout_index=rollout_index,
                cas_codex_rollout_record=cas_codex_rollout_record,
                commit_request_record=commit_request_record,
                attempt_timestamp=attempt_timestamp,
            )
            output_identity = dict(output_row)
            assert output_identity[KTP_FILENAME_COL] == rollout_basename.name
            assert output_identity[KTP_FRAGMENT_COL] == (
                cas_codex_rollout_record.line_count
            )
            identity_exists, error = db_reads.output_identity_exists()
            if error is not None:
                assert identity_exists is None
                raise error
            assert identity_exists is not None
            if identity_exists:
                raise _PushValidationError(Locale.ACCEPTED_IDENTITY_DUPLICATE)
            stage = BackendLifecycle.ACCEPTED
            return result(
                validation_result=BackendLifecycle.ACCEPTED,
                detail=None,
                error=None,
            )
        except _ValidationPreparationError as exc:
            return result(
                validation_result=BackendLifecycle.CONFIGURATION_ERROR,
                detail=Locale.CONFIGURATION_ERROR_DETAIL,
                error=exc,
            )
        except _MultipleEvidenceMatches as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=Locale.MULTIPLE_MATCH_DETAIL_TEMPLATE.format(excerpt=exc.excerpt),
                error=exc,
            )
        except _PushValidationError as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=(
                    exc.public_detail
                    if isinstance(exc, _EvidenceAssessmentError)
                    else Locale.VALIDATION_ERROR_DETAIL
                ),
                error=exc,
            )
        except ValidationError as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=Locale.VALIDATION_ERROR_DETAIL
                + (f"\n{RETRY_SUBMISSION_PUBLIC_GUIDANCE}" if retry_submission_expected else ""),
                error=exc,
            )
        except (OSError, ValueError, duckdb.Error, subprocess.SubprocessError) as exc:
            return result(
                validation_result=BackendLifecycle.REJECTED,
                detail=Locale.VALIDATION_ERROR_DETAIL,
                error=exc,
            )


def pydantic_failure(exc: ValidationError) -> tuple[str | None, str, object]:
    errors = exc.errors(
        include_url=False,
        include_context=False,
        include_input=True,
    )
    if not errors:
        return None, Locale.PYDANTIC_FAILURE, Locale.PYDANTIC_MISSING_INPUT
    error = errors[0]
    reason = str(error.get(PYDANTIC_ERROR_MESSAGE_KEY, Locale.PYDANTIC_FAILURE))
    error_location = error.get(PYDANTIC_ERROR_LOCATION_KEY)
    location_items = error_location if isinstance(error_location, tuple) else ()
    field = next(
        (item for item in location_items if isinstance(item, str) and item in AI_AUGMENT_COLUMNS),
        None,
    )
    if field is None:
        field = next(
            (column for column in AI_AUGMENT_COLUMNS if column in reason),
            None,
        )
    failed_input = (
        Locale.PYDANTIC_MISSING_INPUT
        if error.get(PYDANTIC_ERROR_TYPE_KEY) == PYDANTIC_MISSING_ERROR_TYPE
        else error.get(PYDANTIC_ERROR_INPUT_KEY, Locale.PYDANTIC_MISSING_INPUT)
    )
    return field, reason, failed_input


def _log_post_commit_validation(
    push_response_record: PushResponseRecord,
    post_commit_validation: PostCommitValidation,
    error: Exception | None,
) -> None:
    if error is None:
        logger.info(Locale.PUSH_ACCEPTED_LOG, push_response_record.record_id)
    elif isinstance(error, ValidationError):
        field, reason, failed_input = pydantic_failure(error)
        logger.warning(
            Locale.PUSH_PYDANTIC_FAILED_LOG,
            push_response_record.record_id,
            post_commit_validation.stage,
            field or Locale.UNKNOWN_FIELD,
            failed_input,
            reason,
        )
    elif isinstance(error, _ValidationPreparationError):
        logger.error(
            Locale.PUSH_CONFIGURATION_FAILED_LOG,
            push_response_record.record_id,
            post_commit_validation.stage,
            error,
        )
    elif isinstance(error, _PushValidationError):
        logger.warning(
            Locale.PUSH_VALIDATION_FAILED_LOG,
            push_response_record.record_id,
            post_commit_validation.stage,
            error,
        )
    else:
        logger.warning(
            Locale.PUSH_UNEXPECTED_FAILED_LOG,
            push_response_record.record_id,
            post_commit_validation.stage,
            error,
        )


def evaluate_commit(
    commit_request_record: BackendCommitRequestRecord,
    *,
    initial_validation_request_record: BackendValidationRequestRecord | None,
    inputs: _CommitEvaluationInputs,
    db_reads: _DetourDbValidationReads,
) -> tuple[PostCommitValidation, _ValidationProjection]:
    initial_commit = (
        commit_request_record if initial_validation_request_record is None
        else initial_validation_request_record.validation_request_body.commit_request_record
    )
    assert (
        inputs.original_pull_response_record
        is initial_commit.commit_request_body.pull_response_record
    )
    commit = commit_request_record.commit_request_body
    session_id = commit.codex_session_record.session_id
    rollout = commit.codex_session_record.codex_rollout_record
    appendwatch_report = commit.codex_session_record.appendwatch_report_record
    assert session_id is not None
    assert rollout is not None
    assert appendwatch_report is not None
    stage = BackendLifecycle.CONFIGURATION
    try:
        stage = BackendLifecycle.ROLLOUT_INDEX
        try:
            cas_codex_rollout_record, error = inputs.cas_codex_rollout_record()
            if error is not None:
                assert cas_codex_rollout_record is None
                raise error
        except (OSError, ValueError) as exc:
            raise _PushValidationError(str(exc)) from exc
        assert cas_codex_rollout_record is not None
        assert (
            cas_codex_rollout_record.sha256 == rollout.sha256
            and cas_codex_rollout_record.size == rollout.size
            and cas_codex_rollout_record.line_count == rollout.line_count
        )
        stage = BackendLifecycle.APPENDWATCH_REPORT_VALIDATION
        result = _execute_attempt(
            commit_request_record=commit_request_record,
            cas_codex_rollout_record=cas_codex_rollout_record,
            inputs=inputs,
            db_reads=db_reads,
        )
    except (ModelHttpRequired, ReplayInputMissing):
        raise
    except Exception as exc:
        result = _failed_post_commit_validation(
            commit_request_record=commit_request_record,
            stage=stage,
            error=exc,
        )
    assert result[1].commit_request_record is commit_request_record
    return result


@implements[BackendComponent.PostCommitValidationProperty]()
class PostCommitValidation(FrozenStrictModel):
    stage: BackendLifecycle
    result: BackendLifecycle
    detail: StrictStr | None = None
    submission_type: Literal["Submission", "StandardizedSubmission"] | None
    submission: dict[str, JsonValue] | None

    def validate_lifecycle(self) -> Self:
        if not self.stage.is_post_commit_validation_stage():
            raise ValueError(Locale.VALIDATION_STAGE_INVALID)
        if not self.result.is_post_commit_validation_result():
            raise ValueError(Locale.VALIDATION_RESULT_INVALID)
        if (self.stage is BackendLifecycle.ACCEPTED) != (
            self.result is BackendLifecycle.ACCEPTED
        ):
            raise ValueError(Locale.VALIDATION_ACCEPTANCE_MISMATCH)
        if (self.submission_type is None) != (self.submission is None):
            raise ValueError(Locale.VALIDATION_SUBMISSION_TYPE_MISMATCH)
        if self.result is BackendLifecycle.ACCEPTED and self.submission is None:
            raise ValueError(Locale.VALIDATION_SUBMISSION_MISSING)
        return self

    @model_validator(mode="after")
    def _validate_lifecycle(self) -> Self:
        return self.validate_lifecycle()


# Deliberate mid-file imports: validation_request imports the concrete
# PostCommitValidation model, while these dependencies reach commit_request,
# then pull/push/validation_request. Keep this class defined before entering
# that import path. These are real runtime types used by the evaluator;
# postponing their imports avoids a half-initialized module and needs no
# model_rebuild, placeholder type, or change to the by-reference records.
from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_cas import (  # noqa: E402, E501
    CASCodexRolloutRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.commit_request import (  # noqa: E402, E501
    BackendCommitRequestRecord,
    CodexRolloutRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.pull_event import (  # noqa: E402, E501
    PullResponseRecord,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.push_event import (  # noqa: E402, E501
    PushResponseRecord,
)


class _SessionMetadata(FrozenStrictModel):
    session_id: UUID
    timestamp: str
    rollout_filename: str
    summary_json: str


class _CodexFcRow(FrozenStrictModel):
    timestamp: str
    fc_id: str
    call_id: str
    name: str
    namespace: str
    arguments_json: str


class _CodexFcoRow(FrozenStrictModel):
    timestamp: str
    fco_id: str
    call_id: str


class _CodexTurnRefRow(FrozenStrictModel):
    ref_id: str
    call_id: str
    domain: str | None
    snippet: str | None
    thumbnail_url: str | None
    title: str | None
    url: str
    cite_text: str


class _RolloutIndex(FrozenStrictModel):
    session: _SessionMetadata
    fc_rows: tuple[_CodexFcRow, ...]
    fco_rows: tuple[_CodexFcoRow, ...]
    turn_ref_rows: tuple[_CodexTurnRefRow, ...]


class _EvidenceCandidate(FrozenStrictModel):
    ref_id: str
    call_id: str
    cite_text: str
    excerpt_position: int
    url: str
    fco_timestamp: datetime
    arguments_json: object


@dataclass(frozen=True, slots=True, eq=False)
class _ValidationProjection:
    """Transient DB facts borrowing Store's replayed commit by identity."""

    commit_request_record: BackendCommitRequestRecord
    rollout_index: _RolloutIndex | None = None
    baseline_obligations_json: str | None = None
    submission_json: str | None = None
    assessment_json: str | None = None
    applied: bool | None = None
    accepted: bool | None = None
    output_row: tuple[tuple[str, str | int | None], ...] | None = None
