from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Self, cast

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import RootModel, model_validator

FIELD_COLUMN = "Variable"
AI_COLUMN = "GPT-5.6-Sol Extra High with tools"
HUMAN_COLUMN = "Hafsa/Daniella"

SUBMISSIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "submissions"

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

APP_CONFIG: dict[str, Any] = {
    "title": "Highly-Cited Researcher Annotation API",
    "description": (
        "Pull a JSONL annotation task, submit completed values, "
        "and compare the submission with ground truth."
    ),
    "version": "1.0.0",
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
    "description": (
        "Validates that every required annotation column is present "
        "and non-null. Returns the submission followed by ground truth."
    ),
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
    },
}

PUSH_BODY = Body(
    openapi_examples={
        "completed": {
            "summary": "Completed annotation",
            "value": SUBMISSION_EXAMPLE,
        },
    },
)

app = FastAPI(**APP_CONFIG)

class Submission(RootModel[dict[str, object]]):
    @model_validator(mode="after")
    def validate_submission(self) -> Self:
        expected = set(COLUMNS)
        actual = set(self.root)

        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        null = sorted(
            column
            for column in COLUMNS
            if column in self.root and self.root[column] is None
        )

        errors: list[str] = []

        if missing:
            errors.append(f"missing keys: {', '.join(missing)}")
        if unexpected:
            errors.append(f"unexpected keys: {', '.join(unexpected)}")
        if null:
            errors.append(f"null values: {', '.join(null)}")

        if errors:
            raise ValueError("; ".join(errors))

        return self


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


def dump_push(
    submission: Mapping[str, object],
    truth: Mapping[str, object],
) -> tuple[str, str]:
    submitted = json_line(submission)
    ground = json_line(truth)

    timestamp = datetime.now(timezone.utc)
    ts_for_file = timestamp.strftime("%Y%m%dT%H%M%S_%fZ")
    output_dir = SUBMISSIONS_DIR / ts_for_file
    output_dir.mkdir(parents=True)

    (output_dir / "response.jsonl").write_text(
        submitted + ground,
        encoding="utf-8",
    )

    def cell(value: object) -> str:
        text = json.dumps(value, ensure_ascii=False)
        return text.replace("|", r"\|").replace("\n", "<br>")

    ts_for_humans = timestamp.strftime("%Y-%m-%d @ %H:%M:%S.%f UTC")
    rows = [
        f"AI response processed at: {ts_for_humans}",
        "",
        f"| {FIELD_COLUMN} | {AI_COLUMN} | {HUMAN_COLUMN} |",
        "|---|---|---|",
        *(
            f"| {column} | {cell(submission[column])} "
            f"| {cell(truth[column])} |"
            for column in submission
        ),
    ]
    (output_dir / "response.md").write_text(
        "\n".join(rows) + "\n",
        encoding="utf-8",
    )

    return submitted, ground


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
def push(submission: Annotated[Submission, PUSH_BODY],
) -> StreamingResponse:
    lines = dump_push(submission.root, ground_truth())
    return StreamingResponse(
        iter(lines),
        media_type=MEDIA_TYPE,
    )
