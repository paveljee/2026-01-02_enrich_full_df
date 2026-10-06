import re
from pathlib import Path, PurePosixPath

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    APPENDWATCH_BLANK_LINE,
    APPENDWATCH_COMPROMISED_BODY_PREFIX,
    APPENDWATCH_COMPROMISED_DIRECTORY_PATTERN,
    APPENDWATCH_COMPROMISED_FILE_PATTERN,
    APPENDWATCH_COMPROMISED_ROOT_PREFIX,
    APPENDWATCH_COMPROMISED_STATUS,
    APPENDWATCH_DIRECTORY_SUFFIX,
    APPENDWATCH_EXPECTED_TARGET_ENTRIES,
    APPENDWATCH_NAME_GROUP,
    APPENDWATCH_OK_BODY_PREFIX,
    APPENDWATCH_OK_FILE_PATTERN,
    APPENDWATCH_OK_STATUS,
    APPENDWATCH_PATH_GROUP,
    APPENDWATCH_REMOVED_ENTRY_PATTERN,
    APPENDWATCH_REMOVED_SECTION_HEADER,
    APPENDWATCH_REMOVED_SECTION_HEADER_LINES,
    APPENDWATCH_ROOT_ENTRY,
    APPENDWATCH_TREE_START_INDEX,
    NAME_KEY_PATTERN,
    ROLLOUT_LINE_FRAGMENT_TYPE,
    SOURCE_KEY_PATTERN,
    STRUCTURED_FIELD_STRING,
    TEXT_ENCODING,
    TREE_BODY_GROUP,
    TREE_INDENT_GROUP,
    TREE_INDENT_WIDTH,
    TREE_LINE,
    VALID_NONBLANK,
)
from src.helpers.data_models import NameKey
from src.helpers.vars import (
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_LAST_NAME_COL,
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


def source_key_header_value(filename: str, line_count: int) -> str:
    return (
        f"{KTP_FILENAME_COL}={structured_field_string(filename)}, "
        f'{KTP_FRAGMENT_COL};type="{ROLLOUT_LINE_FRAGMENT_TYPE}";'
        f"{ROLLOUT_LINE_FRAGMENT_TYPE}={structured_field_string(str(line_count))}"
    )


def source_key_from_header_value(value: object) -> tuple[str, int]:
    if not isinstance(value, str):
        raise ValueError("SourceKey header is missing")
    matched = SOURCE_KEY_PATTERN.fullmatch(value)
    if matched is None:
        raise ValueError("SourceKey header is malformed")
    try:
        filename = structured_field_string_value(matched.group("filename"))
        fragment = structured_field_string_value(matched.group("fragment"))
        line_count = int(fragment)
    except ValueError as exc:
        raise ValueError("SourceKey header is malformed") from exc
    if (
        not filename
        or PurePosixPath(filename).name != filename
        or line_count < 1
        or value != source_key_header_value(filename, line_count)
    ):
        raise ValueError("SourceKey header is not canonical")
    return filename, line_count


def require_nonblank_text(value: object, error: Exception) -> str:
    if not VALID_NONBLANK(value):
        raise error
    assert isinstance(value, str)
    return value


class AppendwatchReportError(RuntimeError):
    pass


def parse_appendwatch_report(
    report_path: Path,
    rollout_relative_path: PurePosixPath,
) -> None:
    try:
        report = report_path.read_bytes()
    except OSError as exc:
        raise AppendwatchReportError(Locale.APPENDWATCH_REPORT_UNREADABLE) from exc
    parse_appendwatch_report_bytes(report, rollout_relative_path)


def parse_appendwatch_report_bytes(
    report_bytes: bytes,
    rollout_relative_path: PurePosixPath,
) -> None:
    try:
        report = report_bytes.decode(TEXT_ENCODING)
    except UnicodeError as exc:
        raise AppendwatchReportError(Locale.APPENDWATCH_REPORT_UNREADABLE) from exc
    if not report.endswith("\n"):
        raise AppendwatchReportError(Locale.APPENDWATCH_REPORT_INCOMPLETE)

    lines = report.splitlines()
    if not lines or lines[0] != APPENDWATCH_ROOT_ENTRY:
        if lines and lines[0].startswith(APPENDWATCH_COMPROMISED_ROOT_PREFIX):
            raise AppendwatchReportError(Locale.APPENDWATCH_GLOBAL_DEGRADATION)
        raise AppendwatchReportError(Locale.APPENDWATCH_ROOT_MALFORMED)

    target = rollout_relative_path.parts
    match_target_by_filename = len(target) == 1
    directories: list[tuple[str, bool]] = []
    seen_paths: set[tuple[str, ...]] = set()
    target_entries: list[tuple[str, bool]] = []
    line_index = APPENDWATCH_TREE_START_INDEX

    while line_index < len(lines) and lines[line_index] != APPENDWATCH_BLANK_LINE:
        match = TREE_LINE.fullmatch(lines[line_index])
        if match is None:
            raise AppendwatchReportError(Locale.APPENDWATCH_TREE_LINE_MALFORMED)
        indent = match.group(TREE_INDENT_GROUP)
        depth = len(indent) // TREE_INDENT_WIDTH
        if depth > len(directories):
            raise AppendwatchReportError(Locale.APPENDWATCH_NESTING_INVALID)
        directories = directories[:depth]
        parent_parts = tuple(name for name, _compromised in directories)
        parent_compromised = any(compromised for _name, compromised in directories)
        body = match.group(TREE_BODY_GROUP)

        compromised_directory = APPENDWATCH_COMPROMISED_DIRECTORY_PATTERN.fullmatch(body)
        if compromised_directory is not None:
            name = compromised_directory.group(APPENDWATCH_NAME_GROUP)
            path = (*parent_parts, name)
            if path in seen_paths:
                raise AppendwatchReportError(Locale.APPENDWATCH_PATH_DUPLICATE)
            seen_paths.add(path)
            directories.append((name, True))
            line_index += 1
            continue

        if body.endswith(APPENDWATCH_DIRECTORY_SUFFIX) and not body.startswith((
            APPENDWATCH_OK_BODY_PREFIX,
            APPENDWATCH_COMPROMISED_BODY_PREFIX,
        )):
            name = body.removesuffix(APPENDWATCH_DIRECTORY_SUFFIX)
            if not name or APPENDWATCH_DIRECTORY_SUFFIX in name:
                raise AppendwatchReportError(Locale.APPENDWATCH_DIRECTORY_MALFORMED)
            path = (*parent_parts, name)
            if path in seen_paths:
                raise AppendwatchReportError(Locale.APPENDWATCH_PATH_DUPLICATE)
            seen_paths.add(path)
            directories.append((name, parent_compromised))
            line_index += 1
            continue

        ok_file = APPENDWATCH_OK_FILE_PATTERN.fullmatch(body)
        compromised_file = APPENDWATCH_COMPROMISED_FILE_PATTERN.fullmatch(body)
        if ok_file is None and compromised_file is None:
            raise AppendwatchReportError(Locale.APPENDWATCH_FILE_ENTRY_MALFORMED)
        name = (ok_file or compromised_file).group(  # type: ignore[union-attr]
            APPENDWATCH_NAME_GROUP
        )
        path = (*parent_parts, name)
        if path in seen_paths:
            raise AppendwatchReportError(Locale.APPENDWATCH_PATH_DUPLICATE)
        seen_paths.add(path)
        if path == target or (match_target_by_filename and path[-1:] == target):
            target_entries.append((
                (APPENDWATCH_OK_STATUS if ok_file is not None else APPENDWATCH_COMPROMISED_STATUS),
                parent_compromised,
            ))
        line_index += 1

    if line_index < len(lines):
        if lines[line_index:] == [APPENDWATCH_BLANK_LINE]:
            raise AppendwatchReportError(Locale.APPENDWATCH_STRAY_BLANK_LINE)
        if lines[line_index : line_index + APPENDWATCH_REMOVED_SECTION_HEADER_LINES] != [
            APPENDWATCH_BLANK_LINE,
            APPENDWATCH_REMOVED_SECTION_HEADER,
        ]:
            raise AppendwatchReportError(Locale.APPENDWATCH_REMOVED_SECTION_MALFORMED)
        for removed_line in lines[line_index + APPENDWATCH_REMOVED_SECTION_HEADER_LINES :]:
            removed = APPENDWATCH_REMOVED_ENTRY_PATTERN.fullmatch(removed_line)
            if removed is None:
                raise AppendwatchReportError(Locale.APPENDWATCH_REMOVED_ENTRY_MALFORMED)
            removed_parts = PurePosixPath(removed.group(APPENDWATCH_PATH_GROUP)).parts
            if removed_parts == target or (
                match_target_by_filename and removed_parts[-1:] == target
            ):
                raise AppendwatchReportError(Locale.ROLLOUT_REMOVED_OR_REPLACED)

    if len(target_entries) != APPENDWATCH_EXPECTED_TARGET_ENTRIES:
        reason = (
            Locale.ROLLOUT_STATUS_MISSING if not target_entries else Locale.ROLLOUT_STATUS_AMBIGUOUS
        )
        raise AppendwatchReportError(Locale.ROLLOUT_STATUS_INVALID_TEMPLATE.format(reason=reason))
    status, compromised_ancestor = target_entries[0]
    if status != APPENDWATCH_OK_STATUS or compromised_ancestor:
        raise AppendwatchReportError(Locale.ROLLOUT_NOT_OK)
