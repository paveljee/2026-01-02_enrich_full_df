from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import AsyncGenerator, Iterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Self, cast
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictStr,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    model_validator,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
load_dotenv(REPOSITORY_ROOT / ".env")

logger = logging.getLogger(__name__)

FIELD_COLUMN = "Variable"
AI_COLUMN = "GPT-5.6-Sol Extra High with tools"
HUMAN_COLUMN = "Hafsa/Daniella"
REPORT_FILENAME = "response.md"

SUBMISSIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "submissions"
ATTEMPTS_DIR = SUBMISSIONS_DIR / "attempts"

ROLLOUT_ENV_NAME = "FASTAPI_DETOUR_ROLLOUT_JSONL"
ROLLOUT_JSONL = os.environ.get(ROLLOUT_ENV_NAME, "")
CODEX_SESSIONS_ROOT = PurePosixPath("/home/ai/.codex/sessions")
APPENDWATCH_REPORT = Path(
    os.environ.get(
        "FASTAPI_DETOUR_APPENDWATCH_REPORT",
        "/Volumes/home/aicode/aivm/home/ai/.aivm-control/appendwatch/appendwatch-tree.txt",
    )
).expanduser()

AIVM_INSTANCE = os.environ.get("FASTAPI_DETOUR_AIVM_INSTANCE", "aivm")
AIVM_USER = os.environ.get("FASTAPI_DETOUR_AIVM_USER", "ai")
AIVM_SSH_PORT = os.environ.get("FASTAPI_DETOUR_AIVM_SSH_PORT", "22022")
AIVM_KEY_DIR = Path.home() / ".local" / "share" / "aivm" / ".ssh"
AIVM_IDENTITY_FILE = Path(
    os.environ.get("FASTAPI_DETOUR_AIVM_IDENTITY_FILE", AIVM_KEY_DIR / "id_ed25519")
).expanduser()
AIVM_KNOWN_HOSTS_FILE = Path(
    os.environ.get("FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE", AIVM_KEY_DIR / "known_hosts")
).expanduser()
LIMA_SSH_CONFIG_PATH = Path(
    os.environ.get(
        "FASTAPI_DETOUR_LIMA_SSH_CONFIG",
        Path.home() / ".lima" / AIVM_INSTANCE / "ssh.config",
    )
).expanduser()
AIVM_SSH_TARGET = f"{AIVM_INSTANCE}-{AIVM_USER}"
AIVM_HOST_KEY_ALIAS = f"lima-{AIVM_INSTANCE}-{AIVM_USER}"

MAX_PUSH_BODY_BYTES = 2 * 1024 * 1024
MAX_EXCERPT_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_EXCERPTS_PER_FIELD = MAX_PUSH_BODY_BYTES
ARCHIVE_HASH_CHUNK_BYTES = 1024 * 1024
SCP_TIMEOUT_SECONDS = 60
MIN_TCP_PORT = 1
MAX_TCP_PORT = 65_535
CONTROL_CHARACTER_CEILING = 32
DELETE_CHARACTER_CODEPOINT = 127
APPENDWATCH_STATUS_WIDTH = 11
TREE_INDENT_WIDTH = len("│   ")
APPENDWATCH_OK_PREFIX = f"{'OK':<{APPENDWATCH_STATUS_WIDTH}} "
APPENDWATCH_COMPROMISED_PREFIX = f"{'COMPROMISED':<{APPENDWATCH_STATUS_WIDTH}} "
CONFIGURATION_ERROR_DETAIL = "API is not properly configured. Contact the human operator."
VALIDATION_ERROR_DETAIL = "Submission did not pass validation. Verify all details and try again."
ELIGIBLE_WEB_ACTIONS = frozenset({"search_query", "open", "click"})
TREE_LINE = re.compile(r"^(?P<indent>(?:(?:│   )|(?:    ))*)(?:├── |└── )(?P<body>.*)$")

SOURCE_FILE = Path("tmp/sheikh.jsonl")
DRAW_NUMBER_COLUMN = "ktp.draw_number"
TARGET_DRAW_NUMBER = "146"
FRAGMENT_TYPE_COLUMN = "ktp.fragment_type"
DOCX_ROW_FRAGMENT_TYPE = "docx_row"
COLUMNS = (
    "ktp.table_1_researcher_author",
    "ktp.table_1_place_of_residence",
    "ktp.table_1_gender",
    "ktp.table_1_age_first_publication_according_to_openalex_profile",
    "ktp.table_1_education",
    "ktp.table_1_academic_position_s_",
    "ktp.table_1_social_capital",
    "ktp.table_1_links_",
    "ktp.table_1_comments",
)

MEDIA_TYPE = "application/x-ndjson"

# Note: generated via chatgpt.com on 2026-07-27 UTC,
# using GPT-5.6-Sol-High with tools (context lost)
SUBMISSION_EXAMPLE: dict[str, object] = {
    COLUMNS[0]: "Fei-Fei Li; publishes as L. Fei-Fei.",
    COLUMNS[1]: "Stanford campus, Stanford, California.",
    COLUMNS[2]: "Female.",
    COLUMNS[3]: (
        "28–29; born in 1976, with the earliest visible work on the "
        "OpenAlex profile dated 2005."
    ),
    COLUMNS[4]: (
        "B.A. Physics, Princeton University, 1999; M.S. Electrical "
        "Engineering, Caltech, 2001; Ph.D. Electrical Engineering, "
        "Caltech, 2005."
    ),
    COLUMNS[5]: (
        "Sequoia Capital Professor of Computer Science, Stanford; Senior "
        "Fellow, Stanford HAI; Professor by courtesy, Stanford Graduate "
        "School of Business; former Director, Stanford AI Lab, 2013–2018; "
        "former Vice President and Chief Scientist of AI/ML, Google Cloud, "
        "2017–2018; Co-founder and CEO, World Labs."
    ),
    COLUMNS[6]: (
        "Founding Co-Director, Stanford HAI; Co-founder and Chair, AI4ALL; "
        "member of the National Academy of Engineering, National Academy "
        "of Medicine, American Academy of Arts and Sciences, and Council "
        "on Foreign Relations; ACM Fellow; UN special adviser."
    ),
    COLUMNS[7]: (
        "Stanford profile: https://profiles.stanford.edu/fei-fei-li; "
        "OpenAlex: https://openalex.org/A5100450462; "
        "AI4ALL: https://ai-4-all.org/our-people/fei-fei-li/"
    ),
    COLUMNS[8]: (
        "OpenAlex appears to conflate this author with unrelated researchers "
        "and institutions; age at first publication is therefore provisional."
    ),
}

NULL_SUBMISSION_EXAMPLE = dict.fromkeys(COLUMNS)
EVIDENCE_SUBMISSION_EXAMPLE = {
    column: {
        "value": value,
        "web_search_excerpts": ["Exact contiguous excerpt from an eligible web-tool output."],
    }
    for column, value in SUBMISSION_EXAMPLE.items()
}


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        push_configuration()
    except PushConfigurationError as exc:
        logger.error("push is disabled: %s", exc)
    yield


APP_CONFIG: dict[str, Any] = {
    "title": "Highly-Cited Researcher Annotation API",
    "description": (
        "Pull a JSONL annotation task, submit completed values, "
        "and compare the submission with ground truth."
    ),
    "version": "1.0.0",
    "lifespan": lifespan,
}

PULL_ROUTE: dict[str, Any] = {
    "path": "/pull",
    "response_class": StreamingResponse,
    "summary": "Pull the annotation task",
    "description": (
        "Streams the source JSONL through the selected row. "
        "The selected row contains only the annotation columns "
        "with all values replaced by null."
    ),
    "responses": {
        200: {
            "description": "JSON Lines annotation task",
            "content": {
                MEDIA_TYPE: {
                    "example": (
                        json.dumps(NULL_SUBMISSION_EXAMPLE, ensure_ascii=False)
                        + "\n"
                    ),
                },
            },
        },
    },
}

PUSH_ROUTE: dict[str, Any] = {
    "path": "/push",
    "response_class": StreamingResponse,
    "summary": "Submit completed annotations",
    "description": "Validates and stores the completed submission.",
    "responses": {
        200: {
            "description": "Submission followed by ground truth",
            "content": {
                MEDIA_TYPE: {
                    "example": (
                        json.dumps(SUBMISSION_EXAMPLE, ensure_ascii=False)
                        + "\n"
                        + json.dumps(SUBMISSION_EXAMPLE, ensure_ascii=False)
                        + "\n"
                    ),
                },
            },
        },
        422: {"description": VALIDATION_ERROR_DETAIL},
        503: {"description": CONFIGURATION_ERROR_DETAIL},
    },
    "openapi_extra": {
        "requestBody": {
            "required": True,
            "content": {"application/json": {"example": EVIDENCE_SUBMISSION_EXAMPLE}},
        }
    },
}

app = FastAPI(**APP_CONFIG)

Excerpt = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=MAX_EXCERPT_CHARACTERS),
]


class FieldSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    value: object
    web_search_excerpts: list[Excerpt] = Field(
        min_length=1,
        max_length=MAX_EXCERPTS_PER_FIELD,
    )

    @model_validator(mode="after")
    def validate_field(self) -> Self:
        if self.value is None:
            raise ValueError("value must not be null")
        if any(not excerpt.strip() for excerpt in self.web_search_excerpts):
            raise ValueError("web_search_excerpts must not contain blank strings")
        if len(set(self.web_search_excerpts)) != len(self.web_search_excerpts):
            raise ValueError("web_search_excerpts must be unique")
        return self


class Submission(RootModel[dict[str, FieldSubmission]]):
    model_config = ConfigDict(strict=True)

    @model_validator(mode="after")
    def validate_submission(self, info: ValidationInfo) -> Self:
        expected = set(COLUMNS)
        actual = set(self.root)

        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)

        errors: list[str] = []

        if missing:
            errors.append(f"missing keys: {', '.join(missing)}")
        if unexpected:
            errors.append(f"unexpected keys: {', '.join(unexpected)}")

        if errors:
            raise ValueError("; ".join(errors))

        context = info.context or {}
        evidence_index = context.get("evidence_index")
        validated_evidence = context.get("validated_evidence")
        if not isinstance(evidence_index, EvidenceIndex) or not isinstance(
            validated_evidence, dict
        ):
            raise ValueError("eligible rollout evidence is required")

        for column in COLUMNS:
            field_evidence = []
            for excerpt in self.root[column].web_search_excerpts:
                matches = evidence_index.matches(excerpt)
                if not matches:
                    raise ValueError(f"{column}: excerpt has no eligible web-tool match")
                field_evidence.append((excerpt, matches))
            validated_evidence[column] = field_evidence

        return self


class PushConfigurationError(RuntimeError):
    pass


class PushValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PushConfiguration:
    rollout_guest_path: str
    rollout_relative_path: PurePosixPath
    appendwatch_report: Path
    lima_ssh_config: Path
    identity_file: Path
    known_hosts_file: Path
    ssh_target: str
    host_key_alias: str


@dataclass(frozen=True)
class ArchivedFile:
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class RolloutRecord:
    line_number: int
    line_sha256: str
    value: dict[str, object]


@dataclass(frozen=True)
class EvidencePair:
    call_id: str
    call: RolloutRecord
    output: RolloutRecord
    events: tuple[RolloutRecord, ...]
    text_blocks: tuple[str, ...]

    @property
    def identity(self) -> tuple[str, int, int]:
        return (self.call_id, self.call.line_number, self.output.line_number)


@dataclass(frozen=True)
class EvidenceIndex:
    pairs: tuple[EvidencePair, ...]

    def matches(self, excerpt: str) -> tuple[EvidencePair, ...]:
        return tuple(
            pair
            for pair in self.pairs
            if any(excerpt in text for text in pair.text_blocks)
        )


ValidatedEvidence = dict[
    str,
    list[tuple[str, tuple[EvidencePair, ...]]],
]


def _has_control_character(value: str) -> bool:
    return any(
        ord(character) < CONTROL_CHARACTER_CEILING
        or ord(character) == DELETE_CHARACTER_CODEPOINT
        for character in value
    )


def _valid_nonblank(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and not _has_control_character(value)
    )


def _configuration_file(path: Path, setting: str) -> Path:
    if not path.is_absolute():
        raise PushConfigurationError(f"{setting} must be an absolute path")
    if path.is_symlink() or not path.is_file() or not os.access(path, os.R_OK):
        raise PushConfigurationError(
            f"{setting} is not a readable regular file; rerun deploy.sh or correct .env"
        )
    return path


def push_configuration() -> PushConfiguration:
    raw_rollout = ROLLOUT_JSONL
    if not raw_rollout.strip():
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} is not set; add the active chat rollout path "
            "to the repository-root .env and restart the API"
        )
    if raw_rollout != raw_rollout.strip() or _has_control_character(raw_rollout):
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} contains whitespace or control characters; "
            "correct .env and restart the API"
        )

    rollout_path = PurePosixPath(raw_rollout)
    if str(rollout_path) != raw_rollout or any(
        part in {"", ".", ".."} for part in rollout_path.parts
    ):
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} must be normalized without traversal; "
            "correct .env and restart the API"
        )
    try:
        relative_path = rollout_path.relative_to(CODEX_SESSIONS_ROOT)
    except ValueError as exc:
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} must be below {CODEX_SESSIONS_ROOT}; "
            "correct .env and restart the API"
        ) from exc
    if (
        relative_path == PurePosixPath(".")
        or not relative_path.name.startswith("rollout-")
        or relative_path.suffix != ".jsonl"
    ):
        raise PushConfigurationError(
            f"{ROLLOUT_ENV_NAME} must name a rollout-*.jsonl file; "
            "correct .env and restart the API"
        )

    if not _valid_nonblank(AIVM_INSTANCE):
        raise PushConfigurationError(
            "FASTAPI_DETOUR_AIVM_INSTANCE is invalid; correct .env and restart the API"
        )
    if not _valid_nonblank(AIVM_USER):
        raise PushConfigurationError(
            "FASTAPI_DETOUR_AIVM_USER is invalid; correct .env and restart the API"
        )
    if (
        not AIVM_SSH_PORT.isdecimal()
        or not MIN_TCP_PORT <= int(AIVM_SSH_PORT) <= MAX_TCP_PORT
    ):
        raise PushConfigurationError(
            "FASTAPI_DETOUR_AIVM_SSH_PORT is invalid; correct .env and restart the API"
        )

    return PushConfiguration(
        rollout_guest_path=raw_rollout,
        rollout_relative_path=relative_path,
        appendwatch_report=_configuration_file(
            APPENDWATCH_REPORT,
            "FASTAPI_DETOUR_APPENDWATCH_REPORT",
        ),
        lima_ssh_config=_configuration_file(
            LIMA_SSH_CONFIG_PATH,
            "FASTAPI_DETOUR_LIMA_SSH_CONFIG",
        ),
        identity_file=_configuration_file(
            AIVM_IDENTITY_FILE,
            "FASTAPI_DETOUR_AIVM_IDENTITY_FILE",
        ),
        known_hosts_file=_configuration_file(
            AIVM_KNOWN_HOSTS_FILE,
            "FASTAPI_DETOUR_AIVM_KNOWN_HOSTS_FILE",
        ),
        ssh_target=f"{AIVM_INSTANCE}-{AIVM_USER}",
        host_key_alias=f"lima-{AIVM_INSTANCE}-{AIVM_USER}",
    )


def new_attempt_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return f"{timestamp}_{uuid4().hex}"


def create_attempt(attempt_id: str) -> Path:
    attempt_dir = ATTEMPTS_DIR / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=False)
    return attempt_dir


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _archived_file(path: Path) -> ArchivedFile:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(ARCHIVE_HASH_CHUNK_BYTES):
            size += len(chunk)
            digest.update(chunk)
    return ArchivedFile(path=path, size=size, sha256=digest.hexdigest())


def _publish_archive(temporary: Path, destination: Path) -> ArchivedFile:
    _fsync_file(temporary)
    os.replace(temporary, destination)
    _fsync_directory(destination.parent)
    return _archived_file(destination)


def copy_rollout(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / ".rollout.tmp"
    destination = attempt_dir / f"rollout.{attempt_id}.jsonl"
    command = [
        "scp",
        "-F",
        str(configuration.lima_ssh_config),
        "-o",
        f"ProxyJump=lima-{AIVM_INSTANCE}",
        "-o",
        "HostName=127.0.0.1",
        "-o",
        f"Port={AIVM_SSH_PORT}",
        "-o",
        f"User={AIVM_USER}",
        "-o",
        f"IdentityFile={configuration.identity_file}",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "BatchMode=yes",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "ForwardAgent=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        f"UserKnownHostsFile={configuration.known_hosts_file}",
        "-o",
        f"HostKeyAlias={configuration.host_key_alias}",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "--",
        f"{configuration.ssh_target}:{configuration.rollout_guest_path}",
        str(temporary),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=SCP_TIMEOUT_SECONDS,
        )
        if not temporary.is_file() or temporary.is_symlink():
            raise PushConfigurationError(
                "SCP did not produce a regular rollout archive; verify AIVM deployment"
            )
        return _publish_archive(temporary, destination)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PushConfigurationError(
            "rollout SCP failed; verify the configured rollout and AIVM SSH deployment"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def copy_appendwatch_report(
    configuration: PushConfiguration,
    attempt_dir: Path,
    attempt_id: str,
) -> ArchivedFile:
    temporary = attempt_dir / ".appendwatch-tree.tmp"
    destination = attempt_dir / f"appendwatch-tree.{attempt_id}.txt"
    try:
        shutil.copyfile(configuration.appendwatch_report, temporary)
        return _publish_archive(temporary, destination)
    except OSError as exc:
        raise PushConfigurationError(
            "appendwatch status could not be archived; verify deployment and mounted report"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def parse_appendwatch_report(
    report_path: Path,
    rollout_relative_path: PurePosixPath,
) -> None:
    try:
        report = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PushValidationError("archived appendwatch report is unreadable") from exc
    if not report.endswith("\n"):
        raise PushValidationError("archived appendwatch report is incomplete")

    lines = report.splitlines()
    if not lines or lines[0] != ".":
        if lines and lines[0].startswith(".  [COMPROMISED:"):
            raise PushValidationError("appendwatch reports global monitoring degradation")
        raise PushValidationError("archived appendwatch report has a malformed root")

    target = rollout_relative_path.parts
    directories: list[tuple[str, bool]] = []
    seen_paths: set[tuple[str, ...]] = set()
    target_entries: list[tuple[str, bool]] = []
    line_index = 1

    while line_index < len(lines) and lines[line_index] != "":
        match = TREE_LINE.fullmatch(lines[line_index])
        if match is None:
            raise PushValidationError("archived appendwatch report contains a malformed tree line")
        indent = match.group("indent")
        depth = len(indent) // TREE_INDENT_WIDTH
        if depth > len(directories):
            raise PushValidationError("archived appendwatch report contains invalid nesting")
        directories = directories[:depth]
        parent_parts = tuple(name for name, _compromised in directories)
        parent_compromised = any(compromised for _name, compromised in directories)
        body = match.group("body")

        compromised_directory = re.fullmatch(
            rf"{re.escape(APPENDWATCH_COMPROMISED_PREFIX)}(?P<name>[^/]+)/  \[.+\]",
            body,
        )
        if compromised_directory is not None:
            name = compromised_directory.group("name")
            path = (*parent_parts, name)
            if path in seen_paths:
                raise PushValidationError("archived appendwatch report contains a duplicate path")
            seen_paths.add(path)
            directories.append((name, True))
            line_index += 1
            continue

        if body.endswith("/") and not body.startswith(("OK ", "COMPROMISED ")):
            name = body[:-1]
            if not name or "/" in name:
                raise PushValidationError(
                    "archived appendwatch report contains a malformed directory"
                )
            path = (*parent_parts, name)
            if path in seen_paths:
                raise PushValidationError("archived appendwatch report contains a duplicate path")
            seen_paths.add(path)
            directories.append((name, parent_compromised))
            line_index += 1
            continue

        ok_file = re.fullmatch(
            rf"{re.escape(APPENDWATCH_OK_PREFIX)}(?P<name>[^/]+)",
            body,
        )
        compromised_file = re.fullmatch(
            rf"{re.escape(APPENDWATCH_COMPROMISED_PREFIX)}"
            r"(?P<name>[^/]+?)(?:  \[.*\])?",
            body,
        )
        if ok_file is None and compromised_file is None:
            raise PushValidationError("archived appendwatch report contains a malformed file entry")
        name = (ok_file or compromised_file).group("name")  # type: ignore[union-attr]
        path = (*parent_parts, name)
        if path in seen_paths:
            raise PushValidationError("archived appendwatch report contains a duplicate path")
        seen_paths.add(path)
        if path == target:
            target_entries.append(
                ("OK" if ok_file is not None else "COMPROMISED", parent_compromised)
            )
        line_index += 1

    if line_index < len(lines):
        if lines[line_index:] == [""]:
            raise PushValidationError("archived appendwatch report has a stray blank line")
        if lines[line_index : line_index + 2] != [
            "",
            "removed or replaced (no longer a regular file):",
        ]:
            raise PushValidationError("archived appendwatch report has a malformed removed section")
        for removed_line in lines[line_index + 2 :]:
            removed = re.fullmatch(
                rf"    {re.escape(APPENDWATCH_COMPROMISED_PREFIX)}"
                r"(?P<path>.+?)(?:  \[.*\])?",
                removed_line,
            )
            if removed is None:
                raise PushValidationError(
                    "archived appendwatch report has a malformed removed entry"
                )
            if PurePosixPath(removed.group("path")).parts == target:
                raise PushValidationError("configured rollout was removed or replaced")

    if len(target_entries) != 1:
        reason = "missing" if not target_entries else "ambiguous"
        raise PushValidationError(f"configured rollout status is {reason} in archived report")
    status, compromised_ancestor = target_entries[0]
    if status != "OK" or compromised_ancestor:
        raise PushValidationError("configured rollout is not OK beneath monitored ancestors")


def parse_rollout(rollout_path: Path) -> tuple[RolloutRecord, ...]:
    try:
        raw_lines = rollout_path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        raise PushValidationError("archived rollout is unreadable") from exc

    records: list[RolloutRecord] = []
    for line_number, raw_line in enumerate(raw_lines, start=1):
        completed = raw_line.endswith(b"\n")
        encoded = raw_line[:-1] if completed else raw_line
        if encoded.endswith(b"\r"):
            encoded = encoded[:-1]
        try:
            value: object = json.loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if line_number == len(raw_lines) and not completed:
                break
            raise PushValidationError(
                f"archived rollout contains malformed JSONL at line {line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise PushValidationError(
                f"archived rollout line {line_number} is not a JSON object"
            )
        records.append(
            RolloutRecord(
                line_number=line_number,
                line_sha256=hashlib.sha256(raw_line).hexdigest(),
                value=cast(dict[str, object], value),
            )
        )
    return tuple(records)


def _web_arguments(payload: Mapping[str, object], line_number: int) -> dict[str, object]:
    call_id = payload.get("call_id")
    if not _valid_nonblank(call_id):
        raise PushValidationError(f"web call at rollout line {line_number} has an invalid call_id")
    arguments = payload.get("arguments")
    if not isinstance(arguments, str):
        raise PushValidationError(f"web call {call_id} has unsupported arguments")
    try:
        decoded: object = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise PushValidationError(f"web call {call_id} has malformed arguments") from exc
    if not isinstance(decoded, dict):
        raise PushValidationError(f"web call {call_id} arguments are not a JSON object")
    return cast(dict[str, object], decoded)


def _output_text_blocks(pair_call_id: str, output: object) -> tuple[str, ...]:
    if isinstance(output, str):
        return (output,)
    if not isinstance(output, list) or not output:
        raise PushValidationError(f"web output {pair_call_id} has an unsupported payload")
    blocks: list[str] = []
    for block in output:
        if (
            not isinstance(block, dict)
            or block.get("type") != "input_text"
            or not isinstance(block.get("text"), str)
        ):
            raise PushValidationError(
                f"web output {pair_call_id} has an unsupported text block"
            )
        blocks.append(cast(str, block["text"]))
    return tuple(blocks)


def build_evidence_index(records: tuple[RolloutRecord, ...]) -> EvidenceIndex:
    calls: dict[str, RolloutRecord] = {}
    web_call_ids: set[str] = set()
    outputs: dict[str, list[RolloutRecord]] = {}
    events: dict[str, list[RolloutRecord]] = {}

    for record in records:
        value = record.value
        payload = value.get("payload")
        if not isinstance(payload, dict):
            continue
        payload_type = payload.get("type")
        if (
            value.get("type") == "response_item"
            and payload_type == "function_call"
            and payload.get("namespace") == "web"
            and payload.get("name") == "run"
        ):
            arguments = _web_arguments(payload, record.line_number)
            call_id = cast(str, payload["call_id"])
            if call_id in web_call_ids:
                raise PushValidationError(f"duplicate web call_id {call_id}")
            web_call_ids.add(call_id)
            if not any(arguments.get(action) for action in ELIGIBLE_WEB_ACTIONS):
                continue
            calls[call_id] = record
        elif value.get("type") == "response_item" and payload_type == "function_call_output":
            output_call_id = payload.get("call_id")
            if not _valid_nonblank(output_call_id):
                raise PushValidationError(
                    f"function output at rollout line {record.line_number} has an invalid call_id"
                )
            output_call_id = cast(str, output_call_id)
            if output_call_id in outputs:
                raise PushValidationError(
                    f"duplicate function output call_id {output_call_id}"
                )
            outputs[output_call_id] = [record]
        elif value.get("type") == "event_msg" and payload_type == "web_search_end":
            event_call_id = payload.get("call_id")
            if not _valid_nonblank(event_call_id):
                raise PushValidationError(
                    f"web event at rollout line {record.line_number} has an invalid call_id"
                )
            events.setdefault(cast(str, event_call_id), []).append(record)

    pairs: list[EvidencePair] = []
    for call_id, call in sorted(calls.items(), key=lambda item: item[1].line_number):
        matching_outputs = outputs.get(call_id, [])
        if len(matching_outputs) != 1:
            reason = "missing" if not matching_outputs else "ambiguous"
            raise PushValidationError(f"eligible web output {call_id} is {reason}")
        output = matching_outputs[0]
        payload = cast(dict[str, object], output.value["payload"])
        pairs.append(
            EvidencePair(
                call_id=call_id,
                call=call,
                output=output,
                events=tuple(events.get(call_id, [])),
                text_blocks=_output_text_blocks(call_id, payload.get("output")),
            )
        )
    return EvidenceIndex(tuple(pairs))


def source_rows() -> Iterator[dict[str, object]]:
    try:
        source = SOURCE_FILE.open(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"cannot open {SOURCE_FILE}: {exc}") from exc

    with source:
        for line_number, line in enumerate(source, start=1):
            try:
                value: object = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"invalid JSON in {SOURCE_FILE} at line {line_number}"
                ) from exc

            if not isinstance(value, dict):
                raise RuntimeError(
                    f"expected an object in {SOURCE_FILE} at line {line_number}"
                )

            yield cast(dict[str, object], value)


def select_columns(row: Mapping[str, object]) -> dict[str, object]:
    missing = [column for column in COLUMNS if column not in row]

    if missing:
        raise RuntimeError(
            f"target row is missing keys: {', '.join(missing)}"
        )

    return {column: row[column] for column in COLUMNS}


def json_line(row: Mapping[str, object]) -> str:
    return (
        json.dumps(
            row,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def pull_lines() -> Iterator[str]:
    for row in source_rows():
        if ((row.get(DRAW_NUMBER_COLUMN) == TARGET_DRAW_NUMBER) and
            (row.get(FRAGMENT_TYPE_COLUMN) == DOCX_ROW_FRAGMENT_TYPE)):
            select_columns(row)
            yield json_line(dict.fromkeys(COLUMNS))
            return

        yield json_line(row)


def ground_truth() -> dict[str, object]:
    for row in source_rows():
        if ((row.get(DRAW_NUMBER_COLUMN) == TARGET_DRAW_NUMBER) and
            (row.get(FRAGMENT_TYPE_COLUMN) == DOCX_ROW_FRAGMENT_TYPE)):
            return select_columns(row)

    raise HTTPException(status_code=404, detail="target draw not found")


def _atomic_write_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def record_attempt(
    attempt_dir: Path,
    attempt_id: str,
    stage: str,
    result: str,
    *,
    rollout_archive: ArchivedFile | None = None,
    report_archive: ArchivedFile | None = None,
) -> None:
    artifacts = {}
    for name, artifact in (
        ("rollout", rollout_archive),
        ("appendwatch_report", report_archive),
    ):
        if artifact is not None:
            artifacts[name] = {
                "filename": artifact.path.name,
                "size": artifact.size,
                "sha256": artifact.sha256,
            }
    value = {
        "attempt_id": attempt_id,
        "stage": stage,
        "result": result,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
    }
    _atomic_write_text(
        attempt_dir / "attempt.json",
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
    )


def dump_push(
    submission: Mapping[str, object],
    truth: Mapping[str, object],
    *,
    output_dir: Path,
    evidence: ValidatedEvidence,
    rollout_archive: ArchivedFile,
    report_archive: ArchivedFile,
) -> tuple[str, str]:
    submitted = json_line(submission)
    ground = json_line(truth)

    timestamp = datetime.now(timezone.utc)
    _atomic_write_text(output_dir / "response.jsonl", submitted + ground)

    def escaped_json(value: object) -> str:
        return html.escape(json.dumps(value, ensure_ascii=False, indent=2))

    ts_for_humans = timestamp.strftime("%Y-%m-%d @ %H:%M:%S.%f UTC")
    rows = [
        "# Submission review",
        "",
        f"AI response processed at: {ts_for_humans}",
        "",
        "## Validation artifacts",
        "",
        f"- Rollout: `{rollout_archive.path.name}`",
        f"- Rollout SHA-256: `{rollout_archive.sha256}`",
        f"- Appendwatch snapshot: `{report_archive.path.name}`",
        f"- Appendwatch snapshot SHA-256: `{report_archive.sha256}`",
        "",
    ]
    rendered_pairs: set[tuple[str, int, int]] = set()
    for column in COLUMNS:
        rows.extend(
            [
                f"## {column}",
                "",
                "### AI response",
                "",
                f"<pre><code>{escaped_json(submission[column])}</code></pre>",
                "",
                "### Validated web evidence",
                "",
            ]
        )
        for excerpt_number, (excerpt, matches) in enumerate(evidence[column], start=1):
            rows.extend(
                [
                    f"#### Submitted excerpt {excerpt_number}",
                    "",
                    f"<pre><code>{html.escape(excerpt)}</code></pre>",
                    "",
                ]
            )
            for pair in matches:
                if pair.identity in rendered_pairs:
                    rows.extend(
                        [
                            "This eligible call/output pair is already shown above.",
                            "",
                        ]
                    )
                    continue
                rendered_pairs.add(pair.identity)
                rows.extend(
                    [
                        "<details>",
                        "<summary>Eligible web call/output pair</summary>",
                        "",
                        (
                            f"<p>Call line {pair.call.line_number}; SHA-256 "
                            f"<code>{pair.call.line_sha256}</code></p>"
                        ),
                        f"<pre><code>{escaped_json(pair.call.value)}</code></pre>",
                        (
                            f"<p>Output line {pair.output.line_number}; SHA-256 "
                            f"<code>{pair.output.line_sha256}</code></p>"
                        ),
                        f"<pre><code>{escaped_json(pair.output.value)}</code></pre>",
                    ]
                )
                for event in pair.events:
                    rows.extend(
                        [
                            (
                                f"<p>Web event line {event.line_number}; SHA-256 "
                                f"<code>{event.line_sha256}</code></p>"
                            ),
                            f"<pre><code>{escaped_json(event.value)}</code></pre>",
                        ]
                    )
                rows.extend(["", "</details>", ""])
        rows.extend(
            [
                "### Human/ground-truth response",
                "",
                f"<pre><code>{escaped_json(truth[column])}</code></pre>",
                "",
            ]
        )

    _atomic_write_text(output_dir / REPORT_FILENAME, "\n".join(rows) + "\n")

    return submitted, ground


def validate_transport(request: Request) -> None:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if content_type != "application/json":
        raise PushValidationError("request Content-Type must be application/json")
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_length = int(content_length)
        except ValueError as exc:
            raise PushValidationError("request Content-Length is invalid") from exc
        if declared_length < 0 or declared_length > MAX_PUSH_BODY_BYTES:
            raise PushValidationError("request body exceeds the configured size limit")


async def bounded_request_body(request: Request) -> bytes:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_PUSH_BODY_BYTES:
            raise PushValidationError("request body exceeds the configured size limit")
    return bytes(body)


def pydantic_failure(exc: ValidationError) -> tuple[str | None, str]:
    errors = exc.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )
    if not errors:
        return None, "submission failed Pydantic validation"
    error = errors[0]
    reason = str(error.get("msg", "submission failed Pydantic validation"))
    field = next(
        (item for item in error.get("loc", ()) if isinstance(item, str) and item in COLUMNS),
        None,
    )
    if field is None:
        field = next((column for column in COLUMNS if column in reason), None)
    return field, reason


def safely_record_attempt(
    attempt_dir: Path | None,
    attempt_id: str,
    stage: str,
    result: str,
    *,
    rollout_archive: ArchivedFile | None,
    report_archive: ArchivedFile | None,
) -> None:
    if attempt_dir is None:
        return
    try:
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            result,
            rollout_archive=rollout_archive,
            report_archive=report_archive,
        )
    except OSError:
        logger.exception(
            "push attempt=%s could not record stage=%s result=%s",
            attempt_id,
            stage,
            result,
        )


# curl -N http://127.0.0.1:8000/pull
@app.get(**PULL_ROUTE)
def pull() -> StreamingResponse:
    return StreamingResponse(
        pull_lines(),
        media_type=MEDIA_TYPE,
    )


# curl -N \
#  -H 'Content-Type: application/json' \
#  --data @submission.json \
#  http://127.0.0.1:8000/push
@app.post(**PUSH_ROUTE)
async def push(request: Request) -> StreamingResponse:
    attempt_id = new_attempt_id()
    attempt_dir: Path | None = None
    rollout_archive: ArchivedFile | None = None
    report_archive: ArchivedFile | None = None
    stage = "transport"

    try:
        validate_transport(request)
        stage = "configuration"
        configuration = push_configuration()
        attempt_dir = create_attempt(attempt_id)
        record_attempt(attempt_dir, attempt_id, stage, "pending")

        stage = "rollout_copy"
        record_attempt(attempt_dir, attempt_id, stage, "pending")
        rollout_archive = copy_rollout(configuration, attempt_dir, attempt_id)

        stage = "appendwatch_report_copy"
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "pending",
            rollout_archive=rollout_archive,
        )
        report_archive = copy_appendwatch_report(configuration, attempt_dir, attempt_id)

        stage = "appendwatch_report_validation"
        record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "pending",
            rollout_archive=rollout_archive,
            report_archive=report_archive,
        )
        parse_appendwatch_report(
            report_archive.path,
            configuration.rollout_relative_path,
        )

        stage = "rollout_parse"
        records = parse_rollout(rollout_archive.path)
        evidence_index = build_evidence_index(records)

        stage = "pydantic_validation"
        body = await bounded_request_body(request)
        validated_evidence: ValidatedEvidence = {}
        submission = Submission.model_validate_json(
            body,
            context={
                "evidence_index": evidence_index,
                "validated_evidence": validated_evidence,
            },
        )
        normalized_submission = {
            column: submission.root[column].value
            for column in COLUMNS
        }

        stage = "ground_truth_and_dump"
        truth = ground_truth()
        lines = dump_push(
            normalized_submission,
            truth,
            output_dir=attempt_dir,
            evidence=validated_evidence,
            rollout_archive=rollout_archive,
            report_archive=report_archive,
        )
        record_attempt(
            attempt_dir,
            attempt_id,
            "accepted",
            "accepted",
            rollout_archive=rollout_archive,
            report_archive=report_archive,
        )
        logger.info("push attempt=%s accepted", attempt_id)
        return StreamingResponse(iter(lines), media_type=MEDIA_TYPE)
    except PushConfigurationError as exc:
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "configuration_error",
            rollout_archive=rollout_archive,
            report_archive=report_archive,
        )
        logger.error(
            "push attempt=%s failed stage=%s: %s",
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(status_code=503, detail=CONFIGURATION_ERROR_DETAIL) from None
    except PushValidationError as exc:
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "rejected",
            rollout_archive=rollout_archive,
            report_archive=report_archive,
        )
        logger.warning(
            "push attempt=%s failed stage=%s: %s",
            attempt_id,
            stage,
            exc,
        )
        raise HTTPException(status_code=422, detail=VALIDATION_ERROR_DETAIL) from None
    except ValidationError as exc:
        field, reason = pydantic_failure(exc)
        safely_record_attempt(
            attempt_dir,
            attempt_id,
            stage,
            "rejected",
            rollout_archive=rollout_archive,
            report_archive=report_archive,
        )
        logger.warning(
            "push attempt=%s failed stage=%s field=%s: %s",
            attempt_id,
            stage,
            field or "unknown",
            reason,
        )
        raise HTTPException(status_code=422, detail=VALIDATION_ERROR_DETAIL) from None
