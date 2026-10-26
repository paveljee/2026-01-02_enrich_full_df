from __future__ import annotations

import json
import re
from collections.abc import Callable
from enum import StrEnum

from src.detours.detour_ai_augment.protected.src.backend.helpers import codex_parse
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS,
    COMPACT_JSON_SEPARATORS,
    DOCX_TO_AI_AUGMENT_COLUMNS,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_FOOTNOTES_COL,
)
from src.helpers.cards import MARKDOWN_CODE_DELIMITER
from src.helpers.data_models import InnerDict
from src.helpers.vars import KTP_FILENAME_COL

from ....backend.helpers.data_models.ai_augment_singular_outer_dict import (
    AiAugmentSingularOuterDict,
)


class TableColumn(StrEnum):
    RESEARCHER_VARIABLE = "researcher_variable"
    MANUAL_TABLE_1_VALUE = "manual_table_1_value"
    AI_AUGMENT_VALUE = "ai_augment_value"
    AI_AUGMENT_FOOTNOTES = "ai_augment_footnotes"


MISSING_MANUAL_EXTRACTION = "[MISSING MANUAL EXTRACTION]"
MISSING_AI_FOOTNOTES = "[MISSING AI FOOTNOTES]"
AI_WEB_SEARCH_EXCERPTS_PREFIX = "AI web search excerpts:\n\n"
EXTRACTED_LABEL_TEMPLATE = "**{names} extracted**:"
AI_SECTION_MISSING_FIELD_TEMPLATE = "AI section lacks {column}"
DOCX_EXTRACTOR_MISSING_TEMPLATE = "DOCX filename has no DR/HI extractor: {filename}"

FOOTNOTE_MARKER = re.compile(r"\^(?P<numbers>[0-9]+(?:,[0-9]+)*)\^")
EXTRACTOR_INITIALS_PATTERN = re.compile(r"(?<![A-Za-z])(?:DR|HI)(?![A-Za-z])")
COMMENTER_NAME_PATTERN = re.compile(r"\*\*([^*]+)\*\*\s+commented on\b")

NARRATIVE_VALUE_DEF: Callable[[str], str] = lambda value: (
    value.removeprefix(codex_parse.AI_GENERATED_TEXT_PREFIX).removeprefix(" ")
)


def martin_serialize_standardized_cell(cell: str) -> str:
    opening = f"{codex_parse.AI_GENERATED_TEXT_PREFIX} {MARKDOWN_CODE_DELIMITER}"
    if not (cell.startswith(opening) and cell.endswith(MARKDOWN_CODE_DELIMITER)):
        return cell

    value = json.loads(cell[len(opening):-len(MARKDOWN_CODE_DELIMITER)])

    def inline(item: object) -> str:
        if isinstance(item, str):
            return item
        if isinstance(item, (dict, list)):
            parts = item.values() if isinstance(item, dict) else item
            if all(not isinstance(part, (dict, list)) for part in parts):
                return ", ".join(inline(part) for part in parts)
        return json.dumps(item, ensure_ascii=False, separators=COMPACT_JSON_SEPARATORS)

    def block(item: object) -> str:
        return (
            "\n".join(inline(part) for part in item.values())
            if isinstance(item, dict) else inline(item)
        )

    if isinstance(value, list):
        separator = "\n\n" if all(isinstance(item, dict) for item in value) else "\n"
        body = separator.join(block(item) for item in value)
    else:
        body = block(value)
    if not isinstance(value, (dict, list)) or "\n" not in body:
        return cell
    fence = MARKDOWN_CODE_DELIMITER * 3
    return f"{codex_parse.AI_GENERATED_TEXT_PREFIX}\n\n{fence}\n{body}\n{fence}"


def pipe_table(rows: list[list[str]]) -> str:
    def code_span(line: str) -> str:
        if not line:
            return ""
        longest = max((len(match.group()) for match in re.finditer(r"`+", line)), default=0)
        ticks = "`" * (longest + 1)
        return ticks + line + ticks

    def cell_markdown(cell: str) -> str:
        parts = re.split(r"```\n(.*?)\n```", str(cell), flags=re.DOTALL)
        rendered = []
        for index, part in enumerate(parts):
            if index % 2:
                rendered.append("<br>".join(
                    code_span(line)
                    for line in part.split("\n")
                ))
            else:
                rendered.append(
                    part.replace(r"\|", "|").replace("|", r"\|")
                    .replace(r"\_", "_").replace("_", r"\_")
                    .replace("\n", "<br>")
                )
        return "".join(rendered)

    return "\n".join(
        ["| " + " | ".join(cell_markdown(cell) for cell in rows[0]) + " |",
         "| " + " | ".join("---" for _ in rows[0]) + " |",
         *("| " + " | ".join(cell_markdown(cell) for cell in row) + " |"
           for row in rows[1:])]
    )


def ai_augment_field_renderer(
    researcher: AiAugmentSingularOuterDict,
) -> Callable[[InnerDict, str], str | None]:
    docx_columns = {
        ai_column: docx_column
        for docx_column, ai_column in DOCX_TO_AI_AUGMENT_COLUMNS
    }
    table_columns = {
        column
        for pair in AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS
        for column in pair
    }
    first_narrative = AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS[0][0]
    tables: list[tuple[InnerDict, str]] = []

    for item in researcher.codex_innerdicts:
        values = item.innerdict.data
        if first_narrative not in values:
            raise ValueError(AI_SECTION_MISSING_FIELD_TEMPLATE.format(column=first_narrative))
        rows: list[list[str]] = [[column.value for column in TableColumn]]

        for ai_column, standardized_column in (
            *AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS,
            (KTP_AI_AUGMENT_COMMENTS_COL, None),
        ):
            ground_truth: list[str] = []
            if standardized_column is None:
                ai_value = "" if values[ai_column] is None else str(values[ai_column])
            else:
                standardized = martin_serialize_standardized_cell(
                    str(values[standardized_column])
                )
                narrative = NARRATIVE_VALUE_DEF(str(values[ai_column]))
                ai_value = standardized + "\n\n" + narrative
                multiline = standardized.startswith(
                    codex_parse.AI_GENERATED_TEXT_PREFIX + chr(10) * 2
                )
                docx_column = docx_columns[ai_column]

                for docx in researcher.docx_innerdicts:
                    filename = str(docx.data[KTP_FILENAME_COL])
                    extractors = tuple(dict.fromkeys(EXTRACTOR_INITIALS_PATTERN.findall(filename)))
                    if not extractors:
                        raise ValueError(
                            DOCX_EXTRACTOR_MISSING_TEMPLATE.format(filename=filename)
                        )
                    names_by_initial: dict[str, set[str]] = {}
                    for name in COMMENTER_NAME_PATTERN.findall(
                        str(docx.data.get(
                            docx_columns[KTP_AI_AUGMENT_COMMENTS_COL]
                        ) or ""),
                    ):
                        parts = name.split()
                        if len(parts) >= 2:
                            initials = (parts[0][0] + parts[-1][0]).upper()
                            names_by_initial.setdefault(initials, set()).add(name)
                    labels = [
                        next(iter(names_by_initial[extractor]))
                        if len(names_by_initial.get(extractor, ())) == 1
                        else extractor
                        for extractor in extractors
                    ]
                    prefix = EXTRACTED_LABEL_TEMPLATE.format(
                        names=", ".join(labels)
                    )
                    value = docx.data.get(docx_column)
                    if value is None or not str(value).strip():
                        ground_truth.append(MISSING_MANUAL_EXTRACTION)
                    elif multiline:
                        ground_truth.append(
                            f"{prefix}{chr(10) * 2}```{chr(10)}"
                            f"{value}{chr(10)}```"
                        )
                    else:
                        ground_truth.append(
                            f"{prefix} "
                            f"`{json.dumps(str(value), ensure_ascii=False)}`"
                        )

            match = FOOTNOTE_MARKER.search(str(values[ai_column]))
            prefixes = (
                tuple(
                    f"{number}. "
                    for number in match.group("numbers").split(",")
                )
                if match else ()
            )
            footnotes = "\n\n".join(
                line
                for line in str(values[KTP_AI_AUGMENT_FOOTNOTES_COL]).splitlines()
                if line.startswith(prefixes) and prefixes
            )
            footnotes = (
                AI_WEB_SEARCH_EXCERPTS_PREFIX + footnotes
                if footnotes else MISSING_AI_FOOTNOTES
            )
            row = {
                TableColumn.RESEARCHER_VARIABLE: ai_column,
                TableColumn.MANUAL_TABLE_1_VALUE: "\n\n".join(ground_truth)
                if ground_truth else MISSING_MANUAL_EXTRACTION,
                TableColumn.AI_AUGMENT_VALUE: ai_value,
                TableColumn.AI_AUGMENT_FOOTNOTES: footnotes,
            }
            rows.append([row[column] for column in TableColumn])

        tables.append((item.innerdict, pipe_table(rows)))

    def render_ai_field(inner: InnerDict, column: str) -> str | None:
        for ai_innerdict, table in tables:
            if inner is not ai_innerdict:
                continue
            if column == first_narrative:
                return f"{table}\n\n"
            if column in table_columns or column == KTP_AI_AUGMENT_COMMENTS_COL:
                return ""
            return None
        return None

    return render_ai_field
