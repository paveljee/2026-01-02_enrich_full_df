"""HCR award review using only secondary artifacts handed off by seed.py.

Allowed dependencies: stdlib only; no local, pipeline, or third-party imports.
Proofs read the typed seed handoff, never the database or sampling config.
"""

import csv
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal

SCRIPT_DIR = Path(__file__).resolve().parent
WORKDIR = SCRIPT_DIR.parent
SEED_HANDOFF = WORKDIR / "out/seed_handoff.json"
REPO = WORKDIR.parents[4]
CONFIG_REFERENCE = REPO / "resources/learn.chatgpt.com/docs/config-file/config-reference.md"
MODEL_RELEASE = REPO / "resources/openai.com/index/introducing-gpt-6-sol-and-luna.html"
ATTENTION_PAPER = "https://doi.org/10.48550/arxiv.1706.03762"
TEXT_ENCODING = "utf-8"


class ReportQualifier(Enum):
    AI = "✦"
    COMPUTED = "ƒ"
    IMPORTED = "↤"


class ReportText:
    """Format a quoted report value or a column label with one provenance mark."""

    @staticmethod
    def marker(qualifier: ReportQualifier) -> str:
        return f"^{qualifier.value}^"

    @classmethod
    def format(
        cls, value: object, qualifier: ReportQualifier, *, mark: bool = True, quote: str = '"'
    ) -> str:
        quoted = quote + str(value).replace(quote, "\\" + quote) + quote
        return quoted + (cls.marker(qualifier) if mark else "")

    @classmethod
    def label(cls, value: str, qualifier: ReportQualifier) -> str:
        return value + cls.marker(qualifier)

    @classmethod
    def attest(cls, assignee: str, statement: str) -> str:
        """Render one programmatic paragraph as the assignee's template attestation."""
        return MSG_TEMPLATE_ATTESTATION.format(
            assignee=assignee,
            statement=statement,
            imported_marker=cls.marker(ReportQualifier.IMPORTED),
        )


def report_path(path: Path) -> str:
    """Display a local path from WORKDIR without resolving input symlinks."""
    return "./" + path.relative_to(WORKDIR, walk_up=True).as_posix()


def report_link(path: Path) -> str:
    """A Markdown target relative to reports in out/, checked against the real file."""
    target = os.path.relpath(path, WORKDIR / "out")
    if not (WORKDIR / "out" / target).is_file():
        raise FileNotFoundError(path)
    return target


NAME_FIRST_COL = "first_name"
NAME_LAST_COL = "last_name"
HCR_RESEARCHER_ID_COL = "hcr.researcher_id"
HCR_UNNAMED_6_COL = "hcr.unnamed_6"
HCR_UNNAMED_7_COL = "hcr.unnamed_7"
HCR_UNNAMED_8_COL = "hcr.unnamed_8"
HCR_INSTITUTIONAL_PROFILE_COL = "hcr.institutional_profile"
HCR_LINKEDIN_COL = "hcr.linkedin"
HCR_ORCID_COL = "hcr.orcid"
HCR_TWITTER_COL = "hcr.twitter"
# Mirror src.helpers.vars names without importing pipeline code here.
KTP_FIRST_NAME_COL = "ktp.first_name"
KTP_LAST_NAME_COL = "ktp.last_name"
KTP_FILENAME_COL = "ktp.filename"
KTP_FRAGMENT_COL = "ktp.fragment"
KTP_FRAGMENT_TYPE_COL = "ktp.fragment_type"
DRAW_LABEL = "ktp.draw_number"
HCR_CATEGORY_COL = "hcr.category"
KTP_HCR_PRIMARY_AFFILIATIONS_COL = "ktp.hcr_primary_affiliations"
KTP_HCR_SECONDARY_AFFILIATIONS_COL = "ktp.hcr_secondary_affiliations"
KTP_ECONOMY_MATCH_COL = "ktp.hcr_world_bank_economies_match"
KTP_ECONOMIES_COL = "ktp.hcr_world_bank_economies"
KTP_ECONOMIES_INCOME_GROUP_COL = "ktp.hcr_world_bank_economies_income_group"
# Review-only comparison handles, not source columns.
NAME_PAIR_REVIEW_KEY = "name_pair"
FULL_NAME_TOKENS_REVIEW_KEY = "full_name_tokens"
REVIEW_SOURCE_COLUMNS = (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_FRAGMENT_COL,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    HCR_CATEGORY_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    HCR_RESEARCHER_ID_COL,
    HCR_UNNAMED_6_COL,
    HCR_UNNAMED_7_COL,
    HCR_UNNAMED_8_COL,
    HCR_INSTITUTIONAL_PROFILE_COL,
    HCR_LINKEDIN_COL,
    HCR_ORCID_COL,
    HCR_TWITTER_COL,
)
NAME_SECTION = "Name review"
AFFILIATIONS_SECTION = "Affiliations review"
CATEGORY_SECTION = "Category review"
IDS_SECTION = "Identifiers and links review"
FIELD_PRESENTATION = {
    KTP_FIRST_NAME_COL: (NAME_SECTION, "First name"),
    KTP_LAST_NAME_COL: (NAME_SECTION, "Last name"),
    NAME_PAIR_REVIEW_KEY: (NAME_SECTION, "HCR name"),
    FULL_NAME_TOKENS_REVIEW_KEY: (NAME_SECTION, "Full-name tokens"),
    KTP_HCR_PRIMARY_AFFILIATIONS_COL: (AFFILIATIONS_SECTION, "Primary affiliations"),
    KTP_HCR_SECONDARY_AFFILIATIONS_COL: (AFFILIATIONS_SECTION, "Secondary affiliations"),
    KTP_ECONOMY_MATCH_COL: (AFFILIATIONS_SECTION, "World Bank economy matches"),
    KTP_ECONOMIES_COL: (AFFILIATIONS_SECTION, "World Bank economies"),
    KTP_ECONOMIES_INCOME_GROUP_COL: (AFFILIATIONS_SECTION, "World Bank income group"),
    HCR_CATEGORY_COL: (CATEGORY_SECTION, "HCR category"),
    HCR_RESEARCHER_ID_COL: (IDS_SECTION, "Researcher ID"),
    HCR_UNNAMED_6_COL: (IDS_SECTION, "HCR unnamed 6"),
    HCR_UNNAMED_7_COL: (IDS_SECTION, "HCR unnamed 7"),
    HCR_UNNAMED_8_COL: (IDS_SECTION, "HCR unnamed 8"),
    HCR_INSTITUTIONAL_PROFILE_COL: (IDS_SECTION, "Institutional profile"),
    HCR_LINKEDIN_COL: (IDS_SECTION, "LinkedIn"),
    HCR_ORCID_COL: (IDS_SECTION, "ORCID"),
    HCR_TWITTER_COL: (IDS_SECTION, "Twitter"),
}
REPORT_SECTIONS = (NAME_SECTION, AFFILIATIONS_SECTION, CATEGORY_SECTION, IDS_SECTION)
FRAGMENT_TYPE_KEY = "type"
EXCEL_ROW_FRAGMENT_TYPE = "excel_row"
ERR_EMPTY_SCOPE = "An HCR name review scope needs at least one name condition"
ERR_REVIEW_DECISIONS = "HCR award review needs candidate and disjoint identity decisions"
ERR_SCRIPT_NAME = "Expected first-draw script filename {stem}.py"
ERR_SOURCE_HASH = "The pinned HCR review source snapshot differs from the reviewed source"
ERR_OUTSIDE_SCOPE = "Reviewed HCR spelling outside candidate scope: {row}"
ERR_UNREVIEWED = "Unreviewed HCR name candidate: {row}"
ERR_YEARS = "HCR award years differ from reviewed evidence: {years}"
ERR_FIELDS = "HCR fields differ from reviewed evidence: {fields}"
ERR_AFFILIATION = (
    "HCR {role} affiliation evidence {affiliation!r} not found "
    "throughout years {years}, fields {fields}"
)
ERR_OVERLAP = "Distinct HCR award overlap differs: {overlap}"
ERR_FIRST_AWARD = "First-draw HCR award not uniquely included: {first_award}"
ERR_DUPLICATE_REVIEWED_AWARD = "Duplicate HCR award reference in reviewed source rows"
ERR_SEED = "First-draw NameKey or seed mismatch: {key}"
ERR_LATER_DRAW = "Later draws of NameKey must stay empty: {key}"
ERR_MASK_LINE = "Mask line {line} is not a single NameKey"
ERR_EARLIER_OWNER = "HCR award already belongs to earlier NameKey {key}"
ERR_MULTIPLE_OWNERS = "HCR award has multiple NameKey owners: {award_ref}"
ERR_MISSING_OWNER = "Some reviewed HCR awards have no NameKey owner"
MSG_ASSIGNED = (
    "**NameKey assignment:** {key} receives "
    "{reviewed} reviewed HCR awards; "
    "excluded {excluded} candidate award(s); unique ownership verified. "
    "The assigned HCR SourceKeys are {sourcekeys}; this is the provisional mask entry."
)
ERR_NAME_CONTEXT = "The recorded name-list events do not cover the current file exactly"
ERR_ROLLOUT_EVENTS = "Printed read-event IDs are absent from the pinned Codex rollout"
ERR_OBSERVED_NAME = "A nominated HCR spelling is absent from the reviewed name list"
ERR_ROLLOUT_IDENTITY = (
    "Codex rollout is missing or has conflicting session model, CLI, or context evidence"
)
ERR_AUDIT_SEED = "The source contains no unique seeded HCR award among nominated spellings"
ERR_NO_AUDIT = "Attest the name context and inspect the source before identity review"
ERR_AUDIT_CANDIDATE = "HCR award is not a unique exact-name candidate: {award}"
ERR_AUDIT_DUPLICATE = "HCR award was attested more than once: {award}"
ERR_AUDIT_SEED_PAIR = "The authoritative seed needs no self-comparison"
ERR_AUDIT_INCOMPLETE = "Non-seed HCR candidates not individually attested: {awards}"
ERR_AUDIT_SELECTION = "Accepted HCR awards must include the seed and belong to the audited rows"
ERR_REJECTED_OWNER = "Rejected HCR awards have no remaining NameKey owner: {awards}"
ERR_AUDIT_FACT = "Requested source-pair fact is absent or false: {fact} for {award}"
ERR_AUDIT_FIELD = "Unknown HCR comparison field key: {field_key}"
ERR_AUDIT_REFLECTION = "Each candidate decision needs a nonempty reflection"
ERR_AUDIT_DECISION = "Candidate decision must be accept or reject"
ERR_SEED_RECOLLECTION = (
    "Attest the authoritative seed recollection once before reviewing candidates"
)
ERR_AUDIT_ASSESSMENT = "Proof file lacks {relation} reasoning for {field_key} in {award}"
ERR_SOURCE_SCHEMA = "HCR review snapshot columns differ from the pinned projection"
ERR_SEED_HANDOFF = "Seed handoff is missing, malformed, or references an invalid artifact"
ERR_SEED_REPORT_HASH = "Seeded report template differs from the handed-off artifact"
ERR_NAMES_HASH = "Draw-order name list differs from the handed-off artifact"
MSG_ATTESTATION = (
    "**{assignee}:** I **attest**, by preapproved template and software code, "
    "that an instance of the {model} model operating through Codex CLI "
    "{cli_version} {statement}{imported_marker}"
)
MSG_NAME_ATTESTATION = (
    '**{assignee}:** "I, by virtue of a preapproved template and software code, **attest** '
    "to the following: An instance of the {model} model operating through Codex CLI "
    "{cli_version} nominated the spellings below for seeded HCR award {seed}. "
    "I deemed it an appropriate method for nomination because, as a transformer-based, "
    "reasoning language model using {paper}, it is capable of identifying "
    "Highly-Cited Researcher (HCR) award rows belonging to the same HCR thanks to "
    "progressive disclosure and prefill of relevant context using agentic "
    "Retrieval-Augmented Generation (RAG) tools. The model reports that the events "
    "associated with this nomination in its session rollout {rollout} span the "
    "interval {interval} I have not personally reviewed this individual attestation, "
    'as it was programmatically derived. See [Appendix][appendix] for more details."'
    "{imported_marker}"
)
MSG_TEMPLATE_ATTESTATION = (
    "**{assignee}:** I **attest**, by preapproved template and software code, "
    "to the following: {statement}{imported_marker}"
)
MSG_NOMINATION_NOTE = "reported the following nomination note: {inference}."
MSG_NAME_FILE = (
    "The name list is {names}; SHA-256 {digest}, {size} bytes, {count} names; "
    "these facts are pinned to the reviewed file."
)
MSG_NOMINATED = "The nominated HCR spellings are {names}; these are exact lookup inputs."
MSG_ROLLOUT = (
    "The Codex rollout is {rollout}; its read-event IDs are {events}; "
    "the generator verifies their presence."
)
MSG_MODEL = (
    "Session {session_id} records Codex CLI "
    "{cli_version}; "
    "turn {model_turn_id} records model {model}; "
    "turn {window_turn_id} records runtime model_context_window={window} tokens. "
    "The context-window field is described in [Codex configuration][config-reference]; "
    "the model is described in [the model release][model-release]."
)
MSG_SOURCE_LOOKUP = (
    "**Lookup procedure.** Inputs: the pinned HCR review snapshot below, the nominated "
    "exact first/last-name pairs above, and first-draw SourceKey {seed}. The script "
    "checks the snapshot hash, selects every row with one of those exact name pairs, "
    "and requires exactly one selected row with the seed SourceKey. Output: {rows} "
    "looked-up HCR awards—one seed and {candidates} non-seed candidates. The seed "
    "is displayed first; each candidate is then compared with that seed by section "
    "and given a reflection and decision. Exact-name lookup proposes candidates; "
    "it does not establish shared identity."
)
MSG_SOURCE_FILE = "The HCR review snapshot is {source}; SHA-256 {digest}, {size} bytes."
MSG_SEED_RECOLLECTION = (
    "reported the following unverified model-weight recollection of the authoritative "
    "HCR row: "
    "{recollection} This recollection is not source evidence."
)
MSG_PAIR_ATTESTATION = (
    "reported the following judgment for this candidate: "
    "**Reflection:** {reflection} **Final decision:** {decision}."
)
MSG_NAME_SECTION = "# AI identity audit of HCR XLSX awards"
MSG_NAME_HEADER = (
    "The seeded first name is {first}, the last name is {last}, and its draw is {draw}; "
    "this is the review's first-draw identifier."
)
MSG_PREAMBLE = (
    "This report compares the first-drawn HCR award "
    "with awards under nominated "
    "name spellings, then records a **provisional** mask assignment. Source values, "
    "computed relations, and AI judgments are labeled in place; no live Internet "
    "or web search informed this identity review. Appendix A gives terms and draw "
    "provenance; the final Footnotes section explains the source marks. "
    "All local paths are shown relative to this workdir with a `./` prefix."
)
MSG_FOOTNOTES_HEADER = "## Footnotes"
MSG_PROVENANCE = (
    "**{ai_marker} Generated text:** {ai_example} is AI-authored reasoning or "
    "assessment, not independently verified evidence. "
    "**{computed_marker} Calculated text:** {computed_example} is a substantive "
    "calculation or comparison by the pipeline or review scripts, not display-only "
    "joining. **{imported_marker} Imported text:** {imported_example} is read from "
    "a preexisting artifact or a fixed operator-supplied report template, possibly "
    "joined or decoded solely for display. "
    "A trailing imported mark on a paragraph identifies its fixed template wording; "
    "embedded values retain their own provenance marks. "
    "The mark describes the immediate origin of each quoted value; it does not "
    "establish that the value is true. Seed and candidate values come from the pinned HCR "
    "review snapshot; the name list and rollout are separately identified in the body. "
    "Joined name pairs and source affiliations are imported values; draw labels "
    "are imported from the seeded draw order, while World Bank economy fields "
    "were calculated upstream. Full-name tokens "
    "are calculated by joining and splitting the name fields. "
    "The pinned draw counts and base template "
    "come from `seed.py`; field relations, SourceKey lists, file hashes, "
    "and mask assignments come from this proof and `shared.py`. Per-field "
    "field observations, one seed recollection, and per-candidate reflections are written "
    "in this NameKey's proof file, not selected from a predefined list. Repeated "
    "observations are collapsed into section-level attestation prose. The seed "
    "recollection draws on model weights but is unverified; none of these AI "
    "judgments is source evidence. The proof invokes "
    "each per-row accept/reject identity decision, which `shared.py` renders pending operator "
    "review. Definitions and draw explanations describe cited code/config, not "
    "independent identity evidence. The nomination interval is verified against the "
    "rollout by code although the assignee's supplied wording marks it as the "
    "model's report."
)
MSG_APPENDIX_HEADER = '<a id="appendix"></a>\n\n## Appendix A — terms and draw provenance'
MSG_DEFINITIONS = (
    "**NameKey:** the JSON-serialized pair of HCR-derived first and last names. "
    "It names an OuterDict entry; equal spelling alone is not proof of one person. "
    "**SourceKey:** one resource and one typed fragment, such as "
    "{sourcekey_example}; here it identifies one original HCR XLSX row. "
    "**InnerDict:** source-row data held under a matching procedure; this mask "
    "initially records each row by its filename and Excel-row fragment. "
    "**OuterDict:** a map from NameKeys to lists of InnerDicts; the pipeline has "
    "one entry per distinct NameKey, while this review's JSONL mask keeps one line "
    "per draw to preserve draw order. Definitions follow {outerdict_source} and "
    "{sourcekey_source}. Local paths use `./` relative to this workdir. "
    "**Template-backed nomination statement.** The seed handoff supplies the "
    "assignee; the proof supplies the model's nomination note and read-event IDs; "
    "and the pinned rollout supplies the model and CLI metadata. The report generator "
    "verifies that those read events cover the complete name list and calculates "
    "their time interval, which the template attributes to the model's report. "
    "Software fills the fixed template without an individual human review. "
    "The attention citation describes a model mechanism, not evidence that any "
    "nominated rows share an identity. "
    "**Draw procedure.** {draw_source} and {config_source} "
    "(SHA-256 {config_sha256}) place the {pilot_draws} configured pilot rows "
    "from {pilot_source} first, in configured name/category order "
    "({pilot_example} onward). "
    "With random seed {sample_seed}, it then draws {replacement_batches} "
    "with replacement, followed by {nonreplacement_batches} without replacement from "
    "indices not previously drawn. Numeric draws follow the pilots. "
    "With-replacement sampling permits repeated rows; the observed result is below. "
    "The operator identified that replacement setting as a configuration error. "
    "**Authority rule for this mask.** {seed_source} "
    "places a NameKey's first drawn HCR row as its first InnerDict solely "
    "because that draw came first. Later draws with the exact same NameKey "
    "retain a JSONL line but receive `[]`; matching SourceKeys belong to the "
    "earliest owner. A later different NameKey whose row is assigned to "
    "that owner likewise becomes `[]`. Draw order is a bookkeeping rule, "
    "not evidence that two rows refer to the same person."
)
MSG_NAME_CONTEXT_SECTION = "## Name nominations and read trace"
MSG_DRAW_OBSERVATION = (
    "**Observed draws:** {total_draws} draws "
    "contain {duplicate_rows} repeated SourceKeys; the first {initial_draws} "
    "pilot-plus-replacement draws contain {initial_duplicate_rows} repeated "
    "SourceKeys. Thus the erroneous with-replacement setting produced "
    "{replacement_duplicate_rows} repeated XLSX rows in its {replacement_draws} "
    "draws. NameKeys nevertheless recur on different rows: {name_repeats}."
)
MSG_NAME_REPEAT = "{name} (draws {draws})"
MSG_NO_NAME_REPEATS = "none"
MSG_SOURCE_SECTION = "## HCR source lookup"
MSG_SEED_SECTION = "## Authoritative seed: {filename} row {row_number}"
MSG_SEED_EXPLANATION = (
    "**First-draw authority:** SourceKey {sourcekey} is the "
    "first InnerDict under NameKey {namekey} "
    "solely because draw {draw} is its earliest occurrence in the mask's "
    "draw order. This priority says nothing about the researcher's identity. "
    "A later draw of the exact same NameKey receives `[]`, while any actual "
    "matching HCR rows are assigned to this first owner. The seed is its "
    "own source row, so no self-comparison is needed."
)
MSG_AWARD_SECTION = "## Candidate award: {filename} row {row_number}"
MSG_AT_GLANCE = "### At a glance"
MSG_SECTION_ATTESTATION = (
    "reviewed the looked-up seed HCR award {seed} against candidate {candidate} "
    "for the fields displayed in this section. The model's section assessment is "
    "{assessment}; it is not a calculated identity fact. "
    "Explicit equality checks invoked by this proof for this section: {fields}. "
    "The model used this section in the candidate reflection and decision below."
)
MSG_NO_EQUALITY_CHECK = "none"
MSG_ASSIGNMENT_SECTION = "## Provisional mask assignment"


def _file_facts(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size


def _print_attestation(statement: str) -> None:
    runtime = _rollout_runtime()
    handoff = _seed_handoff()
    print(
        MSG_ATTESTATION.format(
            assignee=handoff.assignee,
            model=ReportText.format(runtime.model, ReportQualifier.IMPORTED, quote="'"),
            cli_version=ReportText.format(
                runtime.cli_version, ReportQualifier.IMPORTED, mark=False, quote="'"
            ),
            statement=statement,
            imported_marker=ReportText.marker(ReportQualifier.IMPORTED),
        )
    )


def _report_field_qualifier(field_key: str) -> ReportQualifier:
    return (
        ReportQualifier.COMPUTED
        if field_key
        in (
            FULL_NAME_TOKENS_REVIEW_KEY,
            KTP_ECONOMY_MATCH_COL,
            KTP_ECONOMIES_COL,
            KTP_ECONOMIES_INCOME_GROUP_COL,
        )
        else ReportQualifier.IMPORTED
    )


def _report_field_value(field_key: str, value: object, *, mark: bool = True) -> str:
    return ReportText.format(
        _report_value(field_key, value), _report_field_qualifier(field_key), mark=mark
    )


@dataclass(frozen=True)
class SeedHandoff:
    """Paths and pinned content exported by seed.py for all later proof reads."""

    version: int
    assignee: str
    total_draws: int
    pilot_draws: int
    source_file: str
    source_sha256: str
    seed_mask_file: str
    seed_mask_sha256: str
    names_file: str
    names_sha256: str
    rollout_file: str
    master_file: str
    report_template_file: str
    report_template_sha256: str

    def artifact(self, relative_file: str) -> Path:
        relative = Path(relative_file)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(ERR_SEED_HANDOFF)
        return WORKDIR / relative

    def dump(self, path: Path = SEED_HANDOFF) -> None:
        path.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding=TEXT_ENCODING)

    @classmethod
    def load(cls, path: Path = SEED_HANDOFF) -> "SeedHandoff":
        try:
            raw = json.loads(path.read_text(encoding=TEXT_ENCODING))
            handoff = cls(**raw)
            if (
                type(handoff.version) is not int
                or handoff.version != 1
                or not isinstance(handoff.assignee, str)
                or not handoff.assignee.strip()
                or "\n" in handoff.assignee
                or type(handoff.total_draws) is not int
                or type(handoff.pilot_draws) is not int
                or not 0 < handoff.pilot_draws <= handoff.total_draws
            ):
                raise ValueError(ERR_SEED_HANDOFF)
            for field in (
                handoff.source_file,
                handoff.seed_mask_file,
                handoff.names_file,
                handoff.rollout_file,
                handoff.master_file,
                handoff.report_template_file,
            ):
                if not isinstance(field, str):
                    raise ValueError(ERR_SEED_HANDOFF)
                handoff.artifact(field)
            if not all(
                isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
                for digest in (
                    handoff.source_sha256,
                    handoff.seed_mask_sha256,
                    handoff.names_sha256,
                    handoff.report_template_sha256,
                )
            ):
                raise ValueError(ERR_SEED_HANDOFF)
        except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError(ERR_SEED_HANDOFF) from exc
        return handoff


@lru_cache(maxsize=1)
def _seed_handoff() -> SeedHandoff:
    return SeedHandoff.load()


def _source_rows() -> Iterator[dict[str, str]]:
    source = _seed_handoff().artifact(_seed_handoff().source_file)
    with source.open(encoding=TEXT_ENCODING) as file:
        for line in file:
            raw = json.loads(line)
            if tuple(raw) != REVIEW_SOURCE_COLUMNS:
                raise ValueError(ERR_SOURCE_SCHEMA)
            yield {key: "" if value is None else str(value) for key, value in raw.items()}


@dataclass(frozen=True)
class CodexRuntime:
    model: str
    cli_version: str
    context_window: int
    model_turn_id: str
    session_id: str
    window_turn_id: str


@lru_cache(maxsize=1)
def _rollout_runtime() -> CodexRuntime:
    """Read the model, host CLI, and actual context from this session's rollout."""
    models: dict[str, str] = {}
    cli_versions: dict[str, str] = {}
    windows: dict[int, str] = {}
    rollout = _seed_handoff().artifact(_seed_handoff().rollout_file)
    with rollout.open(encoding=TEXT_ENCODING) as file:
        for line in file:
            if not any(
                marker in line[:200]
                for marker in ('"session_meta"', '"turn_context"', '"task_started"')
            ):
                continue
            event = json.loads(line)
            payload = event.get("payload", {})
            if event["type"] == "session_meta" and payload.get("cli_version"):
                cli_versions.setdefault(payload["cli_version"], payload["id"])
            elif event["type"] == "turn_context" and payload.get("model"):
                models.setdefault(payload["model"], payload["turn_id"])
            elif event["type"] == "event_msg" and payload.get("type") == "task_started":
                window = payload.get("model_context_window")
                if window is not None:
                    windows.setdefault(window, payload["turn_id"])
    if any(len(values) != 1 for values in (models, cli_versions, windows)):
        raise ValueError(ERR_ROLLOUT_IDENTITY)
    model, model_turn_id = next(iter(models.items()))
    cli_version, session_id = next(iter(cli_versions.items()))
    window, window_turn_id = next(iter(windows.items()))
    return CodexRuntime(model, cli_version, window, model_turn_id, session_id, window_turn_id)


def _verified_name_read_interval(event_ids: tuple[str, ...], lines: list[str]) -> str:
    requested = set(event_ids)
    events: dict[str, tuple[int, int, str]] = {}
    handoff = _seed_handoff()
    names = handoff.artifact(handoff.names_file)
    rollout = handoff.artifact(handoff.rollout_file)
    with rollout.open(encoding=TEXT_ENCODING) as file:
        for line in file:
            if '"item_completed"' not in line or names.name not in line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "event_msg":
                continue
            item = event["payload"]["item"]
            event_id = item.get("id")
            if event_id not in requested:
                continue
            command = item["command"][-1]
            match = re.fullmatch(
                r"sed -n '(\d+),(\d+)p' " + re.escape(str(names.relative_to(REPO))),
                command,
            )
            if (
                not match
                or item["status"] != "completed"
                or item["exit_code"] != 0
                or Path(item["cwd"].removeprefix("file://")) != REPO
            ):
                raise ValueError(ERR_NAME_CONTEXT)
            start, end = map(int, match.groups())
            if item["stdout"] != "".join(lines[start - 1 : end]):
                raise ValueError(ERR_NAME_CONTEXT)
            events[event_id] = (start, end, event["timestamp"])
    if len(events) != len(requested):
        raise ValueError(ERR_NAME_CONTEXT)
    ranges = sorted((start, end) for start, end, _ in events.values())
    if not ranges or ranges[0][0] != 1 or ranges[-1][1] != len(lines):
        raise ValueError(ERR_NAME_CONTEXT)
    if any(left[1] + 1 != right[0] for left, right in zip(ranges, ranges[1:])):
        raise ValueError(ERR_NAME_CONTEXT)
    times = [
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        for _, _, timestamp in events.values()
    ]
    return "–".join(
        time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        for time in (min(times), max(times))
    )


def assert_printed_read_events_in_rollout(event_ids: tuple[str, ...]) -> None:
    """Assert that every reported read-event ID exists in the pinned rollout."""
    expected = set(event_ids)
    found: set[str] = set()
    handoff = _seed_handoff()
    with handoff.artifact(handoff.rollout_file).open(encoding=TEXT_ENCODING) as file:
        for line in file:
            if '"item_completed"' not in line or not any(
                event_id in line for event_id in expected - found
            ):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "event_msg":
                continue
            item = event.get("payload", {}).get("item", {})
            event_id = item.get("id")
            if event_id in expected:
                found.add(event_id)
            if found == expected:
                break
    assert found == expected, ERR_ROLLOUT_EVENTS


def hcr_review_script_name(draw_label: str, first_name: str, last_name: str) -> str:
    """Use the same filename serialization as src.helpers.cards.card_filename."""
    label = f"{draw_label}: {first_name} {last_name}"
    stem = re.sub(r"\s+", "_", re.sub(r"[^A-Za-z0-9\s]+", "", label)).strip("_")
    return f"{stem}.py"


def _hcr_name(row: dict[str, str]) -> tuple[str, str]:
    # Spelling comparison only; this does not establish person identity.
    return (
        row[KTP_FIRST_NAME_COL].strip().removesuffix(".").casefold(),
        row[KTP_LAST_NAME_COL].strip().casefold(),
    )


def _hcr_award_ref(inner: dict) -> tuple[str, int]:
    return inner[KTP_FILENAME_COL], inner[KTP_FRAGMENT_COL][EXCEL_ROW_FRAGMENT_TYPE]


def _hcr_award_year(row: dict[str, str]) -> int:
    return int(row[KTP_FILENAME_COL][:4])


def _hcr_primary_affiliation(row: dict[str, str]) -> str:
    return row[KTP_HCR_PRIMARY_AFFILIATIONS_COL]


@dataclass(frozen=True)
class HcrAward:
    """One original HCR source row exposed as domain facts for pair review."""

    row: dict[str, str]

    @property
    def reference(self) -> tuple[str, int]:
        return self.row[KTP_FILENAME_COL], int(self.row[KTP_FRAGMENT_COL])

    @property
    def name(self) -> tuple[str, str]:
        return self.row[KTP_FIRST_NAME_COL], self.row[KTP_LAST_NAME_COL]

    @property
    def full_name_tokens(self) -> tuple[str, ...]:
        return tuple(" ".join(self.name).split())

    @property
    def category(self) -> str:
        return self.row[HCR_CATEGORY_COL]

    def value(self, field_key: str) -> object:
        if field_key == NAME_PAIR_REVIEW_KEY:
            return self.name
        if field_key == FULL_NAME_TOKENS_REVIEW_KEY:
            return self.full_name_tokens
        return self.row[field_key]


@dataclass(frozen=True)
class HcrComparison:
    field_key: str
    seed_value: object
    candidate_value: object

    @property
    def label(self) -> str:
        return FIELD_PRESENTATION[self.field_key][1]

    @property
    def matches(self) -> bool:
        return bool(self.seed_value) and self.seed_value == self.candidate_value


def same_hcr_value(field_key: str, seed_value: object, candidate_value: object) -> HcrComparison:
    """Retain both visible operands of a source-pair equality check."""
    if field_key not in FIELD_PRESENTATION:
        raise ValueError(ERR_AUDIT_FIELD.format(field_key=field_key))
    return HcrComparison(field_key, seed_value, candidate_value)


def _hcr_secondary_affiliation(row: dict[str, str]) -> str:
    return row[KTP_HCR_SECONDARY_AFFILIATIONS_COL]


def _report_value(field_key: str, value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, tuple):
        value = " · ".join(str(part) for part in value)
    if field_key == KTP_ECONOMIES_COL and isinstance(value, str):
        value = ", ".join(json.loads(value))
    elif field_key == KTP_ECONOMY_MATCH_COL and isinstance(value, str):
        match = json.loads(value)
        value = "; ".join(
            f"{affiliation} → {', '.join(countries)}" for affiliation, countries in match.items()
        )
    return str(value).replace("|", "\\|").replace("\n", "<br>").replace("`", "\\`") or "—"


def _assessed_comparisons(
    seed: HcrAward,
    candidate: HcrAward,
    assessments: dict[str, dict[str, str]],
    checked: set[str],
) -> dict[str, tuple[str, str]]:
    """Render only source relations whose interpretation the proof file supplies."""
    result: dict[str, tuple[str, str]] = {}
    for field_key in FIELD_PRESENTATION:
        left, right = seed.value(field_key), candidate.value(field_key)
        if not left and not right:
            relation = "both_absent"
        elif not left or not right:
            relation = "one_absent"
        elif left == right:
            relation = "equal"
        else:
            relation = "different"
        reason = assessments.get(field_key, {}).get(relation, "")
        if not reason.strip():
            raise ValueError(
                ERR_AUDIT_ASSESSMENT.format(
                    relation=relation, field_key=field_key, award=candidate.reference
                )
            )
        label = "Checked equal" if relation == "equal" and field_key in checked else relation
        result[field_key] = (
            ReportText.format(
                label.replace("_", " ").capitalize(), ReportQualifier.COMPUTED, mark=False
            ),
            reason.strip(),
        )
    return result


def _print_at_glance(seed: HcrAward, candidate: HcrAward | None = None) -> None:
    print(MSG_AT_GLANCE)
    print()
    print(
        ReportText.attest(
            _seed_handoff().assignee,
            "The following at-a-glance table transcribes fields of the pinned HCR awards; "
            "its Seed and Candidate headings identify imported values.",
        )
    )
    print()
    if candidate is None:
        print(
            f"| {ReportText.label('Field', ReportQualifier.IMPORTED)} | "
            f"{ReportText.label('Seed', ReportQualifier.IMPORTED)} |"
        )
        print("|---|---|")
    else:
        print(
            f"| {ReportText.label('Field', ReportQualifier.IMPORTED)} | "
            f"{ReportText.label('Seed', ReportQualifier.IMPORTED)} | "
            f"{ReportText.label('Candidate', ReportQualifier.IMPORTED)} |"
        )
        print("|---|---|---|")
    facts = (
        ("Source award", KTP_FILENAME_COL),
        ("Fragment type", KTP_FRAGMENT_TYPE_COL),
        ("Excel row", KTP_FRAGMENT_COL),
        ("Name", NAME_PAIR_REVIEW_KEY),
        ("HCR category", HCR_CATEGORY_COL),
        ("Primary affiliations", KTP_HCR_PRIMARY_AFFILIATIONS_COL),
    )
    for label, field_key in facts:
        seed_value = _report_field_value(field_key, seed.value(field_key), mark=False)
        if candidate is None:
            print(f"| {label} | {seed_value} |")
        else:
            candidate_value = _report_field_value(field_key, candidate.value(field_key), mark=False)
            print(f"| {label} | {seed_value} | {candidate_value} |")
    print()


def _print_review_sections(
    seed: HcrAward,
    candidate: HcrAward | None = None,
    comparisons: tuple[HcrComparison, ...] = (),
    proof_comparisons: dict[str, tuple[str, str]] | None = None,
) -> None:
    for section in REPORT_SECTIONS:
        print(f"### {section}")
        print()
        print(
            ReportText.attest(
                _seed_handoff().assignee,
                "The following tables show the seed and, where present, the candidate. "
                "Column marks distinguish source values, upstream calculations, and proof "
                "comparisons; the model's assessment follows in section prose.",
            )
        )
        print()
        for qualifier in (ReportQualifier.IMPORTED, ReportQualifier.COMPUTED):
            fields = [
                (field_key, label)
                for field_key, (group, label) in FIELD_PRESENTATION.items()
                if group == section and _report_field_qualifier(field_key) == qualifier
            ]
            if not fields:
                continue
            if candidate is None:
                print(
                    f"| {ReportText.label('Field', ReportQualifier.IMPORTED)} | "
                    f"{ReportText.label('Seed', qualifier)} |"
                )
                print("|---|---|")
            else:
                print(
                    f"| {ReportText.label('Field', ReportQualifier.IMPORTED)} | "
                    f"{ReportText.label('Seed', qualifier)} | "
                    f"{ReportText.label('Candidate', qualifier)} |"
                )
                print("|---|---|---|")
            for field_key, label in fields:
                seed_value = _report_field_value(field_key, seed.value(field_key), mark=False)
                if candidate is None:
                    print(f"| {label} | {seed_value} |")
                else:
                    candidate_value = _report_field_value(
                        field_key, candidate.value(field_key), mark=False
                    )
                    print(f"| {label} | {seed_value} | {candidate_value} |")
            print()
        if candidate is not None:
            if proof_comparisons is None:
                raise ValueError(
                    ERR_AUDIT_ASSESSMENT.format(
                        relation="missing", field_key=section, award=candidate.reference
                    )
                )
            print(
                f"| {ReportText.label('Field', ReportQualifier.IMPORTED)} | "
                f"{ReportText.label('Proof comparison', ReportQualifier.COMPUTED)} |"
            )
            print("|---|---|")
            for field_key, (group, label) in FIELD_PRESENTATION.items():
                if group == section:
                    status, _ = proof_comparisons[field_key]
                    print(f"| {label} | {status} |")
            print()
            section_assessment = " ".join(
                dict.fromkeys(
                    proof_comparisons[field_key][1]
                    for field_key, (group, _) in FIELD_PRESENTATION.items()
                    if group == section
                )
            )
            checked = [
                comparison.label
                for comparison in comparisons
                if FIELD_PRESENTATION[comparison.field_key][0] == section
            ]
            seed_sourcekey = f"{seed.reference[0]}#{EXCEL_ROW_FRAGMENT_TYPE}:{seed.reference[1]}"
            candidate_sourcekey = (
                f"{candidate.reference[0]}#{EXCEL_ROW_FRAGMENT_TYPE}:{candidate.reference[1]}"
            )
            _print_attestation(
                MSG_SECTION_ATTESTATION.format(
                    seed=ReportText.format(seed_sourcekey, ReportQualifier.IMPORTED, quote="'"),
                    candidate=ReportText.format(
                        candidate_sourcekey, ReportQualifier.IMPORTED, quote="'"
                    ),
                    assessment=ReportText.format(section_assessment, ReportQualifier.AI, quote="'"),
                    fields=ReportText.format(
                        ", ".join(checked) if checked else MSG_NO_EQUALITY_CHECK,
                        ReportQualifier.COMPUTED,
                        quote="'",
                    ),
                ),
            )
            print()


class HcrAwardReview:
    """Assign reviewed HCR awards to one first-draw NameKey, leaving later keys present."""

    def __init__(
        self,
        *,
        draw: str,
        namekey: tuple[str, str],
        first_award: tuple[str, int],
        script_path: str,
    ) -> None:
        self.draw = draw
        self.namekey = namekey
        self.first_award = first_award
        self.script_stem = Path(script_path).stem
        self._considered: list[dict[str, str]] = []
        self._included: set[tuple[str, str]] = set()
        self._excluded: set[tuple[str, str]] = set()
        self._expected_years: set[int] | None = None
        self._expected_fields: set[str] | None = None
        self._expected_affiliations: list[tuple[str, str, set[int], set[str] | None]] = []
        self._expected_distinct_overlap: set[int] | None = None
        self._observed_spellings: tuple[tuple[str, str], ...] = ()
        self._audit_rows: list[dict[str, str]] = []
        self._audit_seed: dict[str, str] | None = None
        self._attested_awards: set[tuple[str, int]] = set()
        self._accepted_awards: set[tuple[str, int]] = set()
        self._seed_recollection: str | None = None
        self._seed_report_template: str | None = None

    def attest_name_context(
        self,
        *,
        observed_spellings: tuple[tuple[str, str], ...],
        rollout_event_ids: tuple[str, ...],
        inference: str,
    ) -> None:
        """Attest only nominations actually in the file and a complete logged read."""
        handoff = _seed_handoff()
        names = handoff.artifact(handoff.names_file)
        rollout = handoff.artifact(handoff.rollout_file)
        report_template = handoff.artifact(handoff.report_template_file)
        if _file_facts(names)[0] != handoff.names_sha256:
            raise ValueError(ERR_NAMES_HASH)
        if _file_facts(report_template)[0] != handoff.report_template_sha256:
            raise ValueError(ERR_SEED_REPORT_HASH)
        lines = names.read_text(encoding=TEXT_ENCODING).splitlines(keepends=True)
        interval = _verified_name_read_interval(rollout_event_ids, lines)
        with names.open(encoding=TEXT_ENCODING, newline="") as file:
            listed = {
                (row[NAME_FIRST_COL], row[NAME_LAST_COL])
                for row in csv.DictReader(file, delimiter="\t")
            }
        if not observed_spellings or not set(observed_spellings) <= listed:
            raise ValueError(ERR_OBSERVED_NAME)
        self._observed_spellings = observed_spellings
        self._seed_report_template = report_template.read_text(encoding=TEXT_ENCODING).rstrip()
        runtime = _rollout_runtime()
        digest, size = _file_facts(names)
        print(MSG_NAME_SECTION)
        print()
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_NAME_HEADER.format(
                    first=ReportText.format(self.namekey[0], ReportQualifier.IMPORTED),
                    last=ReportText.format(self.namekey[1], ReportQualifier.IMPORTED),
                    draw=ReportText.format(self.draw, ReportQualifier.IMPORTED),
                ),
            )
        )
        print()
        print(ReportText.attest(handoff.assignee, MSG_PREAMBLE))
        print()
        print(MSG_NAME_CONTEXT_SECTION)
        print()
        print(
            MSG_NAME_ATTESTATION.format(
                assignee=handoff.assignee,
                model=ReportText.format(runtime.model, ReportQualifier.IMPORTED, quote="'"),
                cli_version=ReportText.format(
                    runtime.cli_version, ReportQualifier.IMPORTED, mark=False, quote="'"
                ),
                seed=ReportText.format(
                    f"{self.first_award[0]}#{self.first_award[1]}",
                    ReportQualifier.IMPORTED,
                    quote="'",
                ),
                paper="[attention][attention-paper]",
                rollout=ReportText.format(
                    report_path(rollout), ReportQualifier.IMPORTED, quote="'"
                ),
                interval=ReportText.format(interval, ReportQualifier.AI),
                imported_marker=ReportText.marker(ReportQualifier.IMPORTED),
            )
        )
        print()
        _print_attestation(
            MSG_NOMINATION_NOTE.format(
                inference=ReportText.format(inference, ReportQualifier.AI, quote="'")
            ),
        )
        print()
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_NAME_FILE.format(
                    names=ReportText.format(report_path(names), ReportQualifier.IMPORTED),
                    digest=ReportText.format(digest, ReportQualifier.COMPUTED),
                    size=ReportText.format(size, ReportQualifier.COMPUTED),
                    count=ReportText.format(len(listed), ReportQualifier.COMPUTED),
                ),
            )
        )
        print()
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_MODEL.format(
                    model=ReportText.format(runtime.model, ReportQualifier.IMPORTED),
                    model_turn_id=ReportText.format(
                        runtime.model_turn_id, ReportQualifier.IMPORTED
                    ),
                    cli_version=ReportText.format(runtime.cli_version, ReportQualifier.IMPORTED),
                    session_id=ReportText.format(runtime.session_id, ReportQualifier.IMPORTED),
                    window=ReportText.format(runtime.context_window, ReportQualifier.IMPORTED),
                    window_turn_id=ReportText.format(
                        runtime.window_turn_id, ReportQualifier.IMPORTED
                    ),
                ),
            )
        )
        print()
        nominated = ", ".join(
            ReportText.format(f"{first} | {last}", ReportQualifier.IMPORTED)
            for first, last in observed_spellings
        )
        print(ReportText.attest(handoff.assignee, MSG_NOMINATED.format(names=nominated)))
        print()
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_ROLLOUT.format(
                    rollout=ReportText.format(report_path(rollout), ReportQualifier.IMPORTED),
                    events=", ".join(
                        ReportText.format(event_id, ReportQualifier.IMPORTED)
                        for event_id in rollout_event_ids
                    ),
                ),
            )
        )
        print()

    def find_exact_hcr_awards(self) -> None:
        """Retrieve exact-name source candidates without adjudicating their identity."""
        if not self._observed_spellings:
            raise ValueError(ERR_NO_AUDIT)
        handoff = _seed_handoff()
        source = handoff.artifact(handoff.source_file)
        if _file_facts(source)[0] != handoff.source_sha256:
            raise ValueError(ERR_SOURCE_HASH)
        self._audit_rows = [
            row
            for row in _source_rows()
            if (row[KTP_FIRST_NAME_COL], row[KTP_LAST_NAME_COL]) in self._observed_spellings
        ]
        seeds = [
            row
            for row in self._audit_rows
            if (row[KTP_FILENAME_COL], int(row[KTP_FRAGMENT_COL])) == self.first_award
        ]
        if len(seeds) != 1:
            raise ValueError(ERR_AUDIT_SEED)
        self._audit_seed = seeds[0]
        digest, size = _file_facts(source)
        print(MSG_SOURCE_SECTION)
        print()
        seed_sourcekey = f"{self.first_award[0]}#{EXCEL_ROW_FRAGMENT_TYPE}:{self.first_award[1]}"
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_SOURCE_LOOKUP.format(
                    seed=ReportText.format(seed_sourcekey, ReportQualifier.IMPORTED),
                    rows=ReportText.format(len(self._audit_rows), ReportQualifier.COMPUTED),
                    candidates=ReportText.format(
                        len(self._audit_rows) - 1, ReportQualifier.COMPUTED
                    ),
                ),
            )
        )
        print()
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_SOURCE_FILE.format(
                    source=ReportText.format(report_path(source), ReportQualifier.IMPORTED),
                    digest=ReportText.format(digest, ReportQualifier.COMPUTED),
                    size=ReportText.format(size, ReportQualifier.COMPUTED),
                ),
            )
        )
        print()
        print(MSG_SEED_SECTION.format(filename=self.first_award[0], row_number=self.first_award[1]))
        print()
        namekey = json.dumps(
            {KTP_FIRST_NAME_COL: self.namekey[0], KTP_LAST_NAME_COL: self.namekey[1]},
            sort_keys=True,
        )
        sourcekey = f"{self.first_award[0]}#{EXCEL_ROW_FRAGMENT_TYPE}:{self.first_award[1]}"
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_SEED_EXPLANATION.format(
                    sourcekey=ReportText.format(sourcekey, ReportQualifier.IMPORTED),
                    namekey=ReportText.format(namekey, ReportQualifier.IMPORTED),
                    draw=ReportText.format(self.draw, ReportQualifier.IMPORTED),
                ),
            )
        )
        print()
        seed = HcrAward(self._audit_seed)
        _print_at_glance(seed)
        _print_review_sections(seed)

    def attest_seed_recollection(self, recollection: str) -> None:
        """Record one model-weight recollection after the full authoritative row."""
        if self._audit_seed is None or self._seed_recollection is not None:
            raise ValueError(ERR_SEED_RECOLLECTION)
        if not recollection.strip():
            raise ValueError(ERR_SEED_RECOLLECTION)
        self._seed_recollection = recollection
        _print_attestation(
            MSG_SEED_RECOLLECTION.format(
                recollection=ReportText.format(recollection, ReportQualifier.AI, quote="'")
            ),
        )
        print()

    @property
    def seed_hcr_award(self) -> HcrAward:
        if self._audit_seed is None:
            raise ValueError(ERR_NO_AUDIT)
        return HcrAward(self._audit_seed)

    def hcr_award(self, reference: tuple[str, int]) -> HcrAward:
        if self._audit_seed is None:
            raise ValueError(ERR_NO_AUDIT)
        matches = [
            row
            for row in self._audit_rows
            if (row[KTP_FILENAME_COL], int(row[KTP_FRAGMENT_COL])) == reference
        ]
        if len(matches) != 1:
            raise ValueError(ERR_AUDIT_CANDIDATE.format(award=reference))
        return HcrAward(matches[0])

    def attest_candidate(
        self,
        candidate: HcrAward,
        *,
        comparisons: tuple[HcrComparison, ...],
        assessments: dict[str, dict[str, str]],
        reflection: str,
        decision: Literal["accept", "reject"],
    ) -> None:
        """Compare one candidate, reflect, and explicitly accept or reject it."""
        if self._audit_seed is None or self._seed_recollection is None:
            raise ValueError(ERR_SEED_RECOLLECTION)
        award = candidate.reference
        if award == self.first_award:
            raise ValueError(ERR_AUDIT_SEED_PAIR)
        if candidate.row is not self.hcr_award(award).row:
            raise ValueError(ERR_AUDIT_CANDIDATE.format(award=award))
        if award in self._attested_awards:
            raise ValueError(ERR_AUDIT_DUPLICATE.format(award=award))
        if not comparisons:
            raise ValueError(ERR_AUDIT_FACT.format(fact="<none>", award=award))
        if not reflection.strip():
            raise ValueError(ERR_AUDIT_REFLECTION)
        if decision not in ("accept", "reject"):
            raise ValueError(ERR_AUDIT_DECISION)
        for comparison in comparisons:
            if (
                not comparison.matches
                or comparison.seed_value != self.seed_hcr_award.value(comparison.field_key)
                or comparison.candidate_value != candidate.value(comparison.field_key)
            ):
                raise ValueError(ERR_AUDIT_FACT.format(fact=comparison.label, award=award))
        proof_comparisons = _assessed_comparisons(
            self.seed_hcr_award,
            candidate,
            assessments,
            {comparison.field_key for comparison in comparisons},
        )

        print(MSG_AWARD_SECTION.format(filename=award[0], row_number=award[1]))
        print()
        _print_at_glance(self.seed_hcr_award, candidate)
        _print_review_sections(
            self.seed_hcr_award,
            candidate,
            comparisons,
            proof_comparisons,
        )
        _print_attestation(
            MSG_PAIR_ATTESTATION.format(
                reflection=ReportText.format(reflection, ReportQualifier.AI, quote="'"),
                decision=ReportText.format(decision, ReportQualifier.AI, quote="'"),
            ),
        )
        print()
        self._attested_awards.add(award)
        if decision == "accept":
            self._accepted_awards.add(award)

    def assign_attested_awards_to_first_draw(self) -> None:
        """Claim only accepted source rows after all exact candidates are decided."""
        if self._audit_seed is None or self._seed_recollection is None:
            raise ValueError(ERR_SEED_RECOLLECTION)
        candidates = {
            (row[KTP_FILENAME_COL], int(row[KTP_FRAGMENT_COL])) for row in self._audit_rows
        }
        non_seed_candidates = candidates - {self.first_award}
        if non_seed_candidates != self._attested_awards:
            raise ValueError(
                ERR_AUDIT_INCOMPLETE.format(
                    awards=sorted(non_seed_candidates - self._attested_awards)
                )
            )
        print(MSG_ASSIGNMENT_SECTION)
        print()
        self.assign_awards_to_first_draw(
            selected_award_refs={self.first_award, *self._accepted_awards}
        )
        if self._seed_report_template is None:
            raise ValueError(ERR_NO_AUDIT)
        print()
        print(self._seed_report_template)
        print()
        print(MSG_FOOTNOTES_HEADER)
        print()
        print(
            ReportText.attest(
                _seed_handoff().assignee,
                MSG_PROVENANCE.format(
                    ai_marker=ReportText.marker(ReportQualifier.AI),
                    computed_marker=ReportText.marker(ReportQualifier.COMPUTED),
                    imported_marker=ReportText.marker(ReportQualifier.IMPORTED),
                    ai_example=ReportText.format("Generated text", ReportQualifier.AI),
                    computed_example=ReportText.format("Calculated text", ReportQualifier.COMPUTED),
                    imported_example=ReportText.format("Imported text", ReportQualifier.IMPORTED),
                ),
            )
        )
        print()
        print(f"[config-reference]: {report_link(CONFIG_REFERENCE)}")
        print(f"[model-release]: {report_link(MODEL_RELEASE)}")
        print(f"[attention-paper]: {ATTENTION_PAPER}")
        print("[appendix]: #appendix")

    def consider_hcr_names(
        self,
        *,
        first: str | None = None,
        first_starts: str | None = None,
        first_contains: str | None = None,
        last: str | None = None,
        last_starts: str | None = None,
    ) -> None:
        """Define a candidate spelling scope; every row in it must be adjudicated."""
        scope: dict[str, str] = {}
        for name, value in (
            ("first", first),
            ("first_starts", first_starts),
            ("first_contains", first_contains),
            ("last", last),
            ("last_starts", last_starts),
        ):
            if value is not None:
                spelling = value.strip().casefold()
                scope[name] = spelling.removesuffix(".") if name.startswith("first") else spelling
        if not scope:
            raise ValueError(ERR_EMPTY_SCOPE)
        self._considered.append(scope)

    def include_awards_named(self, first: str, last: str) -> None:
        """Claim rows with this HCR spelling, allowing one terminal given-name period."""
        self._included.add(_hcr_name({KTP_FIRST_NAME_COL: first, KTP_LAST_NAME_COL: last}))

    def exclude_awards_named(self, first: str, last: str) -> None:
        """Record a reviewed, distinct HCR spelling within the candidate scope."""
        self._excluded.add(_hcr_name({KTP_FIRST_NAME_COL: first, KTP_LAST_NAME_COL: last}))

    def expect_hcr_award_years(self, *years: int) -> None:
        self._expected_years = set(years)

    def expect_hcr_fields(self, *fields: str) -> None:
        self._expected_fields = set(fields)

    def expect_hcr_affiliation(
        self,
        text: str,
        *,
        in_years: tuple[int, ...],
        in_fields: tuple[str, ...] | None = None,
    ) -> None:
        self._expected_affiliations.append((
            "primary",
            text.casefold(),
            set(in_years),
            set(in_fields) if in_fields is not None else None,
        ))

    def expect_hcr_secondary_affiliation(self, text: str, *, in_years: tuple[int, ...]) -> None:
        self._expected_affiliations.append(("secondary", text.casefold(), set(in_years), None))

    def expect_distinct_hcr_awards_in_same_years(self, *years: int) -> None:
        self._expected_distinct_overlap = set(years)

    def _in_review_scope(self, spelling: tuple[str, str]) -> bool:
        first, last = spelling
        return any(
            ("first" not in scope or first == scope["first"])
            and ("first_starts" not in scope or first.startswith(scope["first_starts"]))
            and ("first_contains" not in scope or scope["first_contains"] in first)
            and ("last" not in scope or last == scope["last"])
            and ("last_starts" not in scope or last.startswith(scope["last_starts"]))
            for scope in self._considered
        )

    def assign_awards_to_first_draw(
        self, *, selected_award_refs: set[tuple[str, int]] | None = None
    ) -> None:
        if selected_award_refs is None and (
            not self._considered or not self._included or self._included & self._excluded
        ):
            raise ValueError(ERR_REVIEW_DECISIONS)
        first, last = self.namekey
        stem = Path(hcr_review_script_name(self.draw, first, last)).stem
        if self.script_stem not in {stem, f"{stem}_alt"}:
            raise ValueError(ERR_SCRIPT_NAME.format(stem=stem))

        handoff = _seed_handoff()
        source = handoff.artifact(handoff.source_file)
        master = handoff.artifact(handoff.master_file)
        master_temp = master.with_name(master.name + ".tmp")
        if _file_facts(source)[0] != handoff.source_sha256:
            raise ValueError(ERR_SOURCE_HASH)
        selected: list[dict[str, str]] = []
        distinct_awards: list[dict[str, str]] = []
        if selected_award_refs is not None:
            audited = {
                (row[KTP_FILENAME_COL], int(row[KTP_FRAGMENT_COL])) for row in self._audit_rows
            }
            if self.first_award not in selected_award_refs or not selected_award_refs <= audited:
                raise ValueError(ERR_AUDIT_SELECTION)
            for row in self._audit_rows:
                ref = (row[KTP_FILENAME_COL], int(row[KTP_FRAGMENT_COL]))
                (selected if ref in selected_award_refs else distinct_awards).append(row)
        else:
            for row in _source_rows():
                spelling = _hcr_name(row)
                in_scope = self._in_review_scope(spelling)
                included = spelling in self._included
                excluded = spelling in self._excluded
                if (included or excluded) and not in_scope:
                    raise ValueError(ERR_OUTSIDE_SCOPE.format(row=row))
                if not in_scope:
                    continue
                if included:
                    selected.append(row)
                elif excluded:
                    distinct_awards.append(row)
                else:
                    raise ValueError(ERR_UNREVIEWED.format(row=row))

        years = {_hcr_award_year(row) for row in selected}
        if self._expected_years is not None and years != self._expected_years:
            raise ValueError(ERR_YEARS.format(years=years))
        fields = {row[HCR_CATEGORY_COL] for row in selected}
        if self._expected_fields is not None and fields != self._expected_fields:
            raise ValueError(ERR_FIELDS.format(fields=fields))
        for role, affiliation, expected_years, expected_fields in self._expected_affiliations:
            relevant = [
                row
                for row in selected
                if _hcr_award_year(row) in expected_years
                and (expected_fields is None or row[HCR_CATEGORY_COL] in expected_fields)
            ]
            actual_years = {_hcr_award_year(row) for row in relevant}
            affiliation_for = (
                _hcr_primary_affiliation if role == "primary" else _hcr_secondary_affiliation
            )
            if actual_years != expected_years or any(
                affiliation not in affiliation_for(row).casefold() for row in relevant
            ):
                raise ValueError(
                    ERR_AFFILIATION.format(
                        role=role,
                        affiliation=affiliation,
                        years=sorted(expected_years),
                        fields=sorted(expected_fields) if expected_fields is not None else "all",
                    )
                )
        overlap = years & {_hcr_award_year(row) for row in distinct_awards}
        if (
            self._expected_distinct_overlap is not None
            and overlap != self._expected_distinct_overlap
        ):
            raise ValueError(ERR_OVERLAP.format(overlap=overlap))

        seed_rows = [
            row
            for row in selected
            if (row[KTP_FILENAME_COL], int(row[KTP_FRAGMENT_COL])) == self.first_award
        ]
        if len(seed_rows) != 1:
            raise ValueError(ERR_FIRST_AWARD.format(first_award=self.first_award))
        ordered = seed_rows + [row for row in selected if row is not seed_rows[0]]
        reviewed = [
            {
                KTP_FILENAME_COL: row[KTP_FILENAME_COL],
                KTP_FRAGMENT_COL: {
                    FRAGMENT_TYPE_KEY: EXCEL_ROW_FRAGMENT_TYPE,
                    EXCEL_ROW_FRAGMENT_TYPE: int(row[KTP_FRAGMENT_COL]),
                },
            }
            for row in ordered
        ]
        wanted = {_hcr_award_ref(inner) for inner in reviewed}
        if len(wanted) != len(reviewed):
            raise ValueError(ERR_DUPLICATE_REVIEWED_AWARD)

        entries = [
            json.loads(line) for line in master.read_text(encoding=TEXT_ENCODING).splitlines()
        ]
        key = json.dumps({KTP_FIRST_NAME_COL: first, KTP_LAST_NAME_COL: last}, sort_keys=True)
        positions = [i for i, entry in enumerate(entries) if key in entry]
        if not positions or entries[positions[0]][key][0] != reviewed[0]:
            raise ValueError(ERR_SEED.format(key=key))
        position = positions[0]
        if any(entries[i][key] for i in positions[1:]):
            raise ValueError(ERR_LATER_DRAW.format(key=key))
        for i, entry in enumerate(entries):
            if len(entry) != 1:
                raise ValueError(ERR_MASK_LINE.format(line=i + 1))
            other_key, awards = next(iter(entry.items()))
            if (
                i < position
                and other_key != key
                and any(_hcr_award_ref(award) in wanted for award in awards)
            ):
                raise ValueError(ERR_EARLIER_OWNER.format(key=other_key))
            entry[other_key] = (
                reviewed
                if i == position
                else [award for award in awards if _hcr_award_ref(award) not in wanted]
            )

        owned: set[tuple[str, int]] = set()
        for entry in entries:
            for award in next(iter(entry.values())):
                award_ref = _hcr_award_ref(award)
                if award_ref in owned:
                    raise ValueError(ERR_MULTIPLE_OWNERS.format(award_ref=award_ref))
                owned.add(award_ref)
        if not wanted <= owned:
            raise ValueError(ERR_MISSING_OWNER)
        if selected_award_refs is not None:
            rejected_refs = audited - selected_award_refs
            if not rejected_refs <= owned:
                raise ValueError(ERR_REJECTED_OWNER.format(awards=sorted(rejected_refs - owned)))
        master_temp.write_text(
            "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
            encoding=TEXT_ENCODING,
        )
        master_temp.replace(master)
        sourcekeys = ", ".join(
            ReportText.format(
                f"{filename}#{EXCEL_ROW_FRAGMENT_TYPE}:{row_number}",
                ReportQualifier.IMPORTED,
            )
            for filename, row_number in map(_hcr_award_ref, reviewed)
        )
        print(
            ReportText.attest(
                handoff.assignee,
                MSG_ASSIGNED.format(
                    key=ReportText.format(key, ReportQualifier.IMPORTED),
                    reviewed=ReportText.format(len(reviewed), ReportQualifier.COMPUTED),
                    excluded=ReportText.format(len(distinct_awards), ReportQualifier.COMPUTED),
                    sourcekeys=sourcekeys,
                ),
            )
        )
