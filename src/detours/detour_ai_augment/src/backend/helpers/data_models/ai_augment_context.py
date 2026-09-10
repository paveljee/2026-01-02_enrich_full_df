from __future__ import annotations

import csv
import json
import re
from collections import Counter
from collections.abc import Mapping
from functools import cached_property
from pathlib import Path
from random import Random
from typing import cast

import duckdb
from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    AI_AUGMENT_RND_START,
    EXCLUDED_NAMEKEY,
    GROUND_TRUTH_DEF,
    INELIGIBLE_RELEASE_BATCH,
    MAP_SUBSET_0_TO_BATCH_KEY,
    NO_GROUND_TRUTH_DEF,
    NO_GROUND_TRUTH_SSN_COUNT,
    TEXT_ENCODING,
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from src.helpers.architecture import implements
from src.helpers.data_models import InnerDict, MatchingProcedure, NameKey
from src.helpers.duckdb_utils import duckdb_quote_identifier
from src.helpers.procedures import (
    DocxMatchProcedure,
    ParquetMatchProcedure,
    XlsxMatchProcedure,
)
from src.helpers.schema import (
    CARD_PARTITION_TABLE,
    DOCX_INNERDICT_TABLE,
    PARQUET_INNERDICT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    BATCH_LABEL,
    DRAW_LABEL,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_NAMEKEY_COL,
    KTP_PARTITION_COL,
    KTP_PARTITION_DOCX_VALUE,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
    KTP_PARTITION_SSN_VALUE,
)

from .ai_augment_outer_dict import AiAugmentOuterDict

MAP_COLUMNS = (DRAW_LABEL, BATCH_LABEL)

EXPECTED_GROUND_TRUTH_RESEARCHERS = 196
EXPECTED_NO_GROUND_TRUTH_RESEARCHERS = 78
EXPECTED_ELIGIBLE_RESEARCHERS = 274
EXPECTED_INELIGIBLE_RESEARCHERS = 33
EXPECTED_SOURCE_RESEARCHERS = (
    EXPECTED_ELIGIBLE_RESEARCHERS + EXPECTED_INELIGIBLE_RESEARCHERS
)
EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS = 5

EXPECTED_INELIGIBILITY_COUNTS = {
    AiAugmentIneligibilityCategory.EXCLUDED_DUPLICATE_NAMEKEY: 1,
    AiAugmentIneligibilityCategory.RELEASE_BATCH_SUBSET_8: 3,
    AiAugmentIneligibilityCategory.STAGING_PARTITION_2: 7,
    AiAugmentIneligibilityCategory.STAGING_PARTITION_4_XLSX_NON_EXACT: 6,
    AiAugmentIneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN: 16,
}
DRAW_PILOT_PREFIX = "pilot."
DRAW_SORT_PART = re.compile(r"\d+|\D+")


def _valid_nonblank(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _load_release_batches(path: Path) -> dict[str, str]:
    try:
        with path.open(encoding=TEXT_ENCODING, newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != MAP_COLUMNS:
                raise ValueError(
                    Locale.MAP_COLUMNS_INVALID_TEMPLATE.format(
                        resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
                        columns=MAP_COLUMNS,
                    )
                )
            batches: dict[str, str] = {}
            for row_number, row in enumerate(reader, start=2):
                draw_number = row.get(DRAW_LABEL)
                release_batch = row.get(BATCH_LABEL)
                if not _valid_nonblank(draw_number) or not _valid_nonblank(
                    release_batch
                ):
                    raise ValueError(
                        Locale.MAP_ROW_BLANK_TEMPLATE.format(
                            resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
                            row_number=row_number,
                        )
                    )
                assert isinstance(draw_number, str)
                assert isinstance(release_batch, str)
                if draw_number in batches and batches[draw_number] != release_batch:
                    raise ValueError(
                        Locale.MAP_DRAW_CONFLICT_TEMPLATE.format(
                            resource_key=MAP_SUBSET_0_TO_BATCH_KEY,
                            draw_number=draw_number,
                        )
                    )
                batches[draw_number] = release_batch
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(
            Locale.MAP_CSV_UNREADABLE_TEMPLATE.format(
                resource_key=MAP_SUBSET_0_TO_BATCH_KEY
            )
        ) from exc
    if not batches:
        raise ValueError(
            Locale.MAP_CSV_EMPTY_TEMPLATE.format(
                resource_key=MAP_SUBSET_0_TO_BATCH_KEY
            )
        )
    return batches


def _innerdict_json_rows(
    value: object,
    *,
    table_name: str,
    namekey: str,
) -> tuple[dict[str, object], ...]:
    if not isinstance(value, str):
        raise ValueError(
            Locale.INNERDICTS_NON_TEXT_TEMPLATE.format(
                table_name=table_name,
                namekey=namekey,
            )
        )
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(value.splitlines(), start=1):
        try:
            row: object = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                Locale.INNERDICTS_MALFORMED_TEMPLATE.format(
                    table_name=table_name,
                    namekey=namekey,
                    line_number=line_number,
                )
            ) from exc
        if not isinstance(row, dict):
            raise ValueError(
                Locale.INNERDICTS_NON_OBJECT_TEMPLATE.format(
                    table_name=table_name,
                    namekey=namekey,
                    line_number=line_number,
                )
            )
        rows.append(cast(dict[str, object], row))
    return tuple(rows)


def _draw_sort_key(
    value: str,
) -> tuple[int, tuple[tuple[int, int | str], ...], str]:
    raw = value.strip()
    normalized = raw.casefold()
    if normalized.startswith(DRAW_PILOT_PREFIX):
        group = 0
        sortable = normalized.removeprefix(DRAW_PILOT_PREFIX)
    elif raw.isdecimal():
        group = 1
        sortable = normalized
    elif raw:
        group = 2
        sortable = normalized
    else:
        group = 3
        sortable = normalized
    tokens = tuple(
        (0, int(part)) if part.isdecimal() else (1, part)
        for part in DRAW_SORT_PART.findall(sortable)
    )
    return (group, tokens, normalized)


def _source_innerdicts_by_namekey(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    procedure: MatchingProcedure,
) -> dict[str, tuple[InnerDict, ...]]:
    try:
        table_rows = conn.execute(
            f"SELECT {duckdb_quote_identifier(KTP_NAMEKEY_COL)}, "
            f"{duckdb_quote_identifier(KTP_INNERDICT_JSONLINES_COL)} "
            f"FROM {table_name} "
            f"ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}"
        ).fetchall()
    except duckdb.Error as exc:
        raise ValueError(
            Locale.SOURCE_DUCKDB_TABLE_MISSING_TEMPLATE.format(table_name=table_name)
        ) from exc
    innerdicts_by_namekey: dict[str, tuple[InnerDict, ...]] = {}
    for raw_namekey, jsonlines in table_rows:
        if not isinstance(raw_namekey, str):
            raise ValueError(
                Locale.TABLE_NAMEKEY_NON_TEXT_TEMPLATE.format(table_name=table_name)
            )
        try:
            namekey = NameKey.from_json_key(raw_namekey).to_json_key()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                Locale.TABLE_NAMEKEY_INVALID_TEMPLATE.format(table_name=table_name)
            ) from exc
        if namekey in innerdicts_by_namekey:
            raise ValueError(
                Locale.CONFIGURED_ROWS_DUPLICATE_TEMPLATE.format(table_name=table_name)
            )
        innerdicts_by_namekey[namekey] = tuple(
            InnerDict.from_mapping(row, procedure)
            for row in _innerdict_json_rows(
                jsonlines,
                table_name=table_name,
                namekey=namekey,
            )
        )
    return innerdicts_by_namekey


def _namekeys_and_draws(
    *source_innerdicts: Mapping[str, tuple[InnerDict, ...]],
) -> dict[str, tuple[NameKey, tuple[str, ...]]]:
    draws_by_namekey: dict[str, set[str]] = {}
    names_by_namekey: dict[str, NameKey] = {}
    for innerdicts_by_namekey in source_innerdicts:
        for namekey, innerdicts in innerdicts_by_namekey.items():
            names_by_namekey[namekey] = NameKey.from_json_key(namekey)
            namekey_draws = draws_by_namekey.setdefault(namekey, set())
            for innerdict in innerdicts:
                draw_number = innerdict.data.get(DRAW_LABEL)
                if draw_number is not None:
                    draw_text = str(draw_number).strip()
                    if draw_text:
                        namekey_draws.add(draw_text)
    return {
        namekey: (
            name_key,
            tuple(sorted(draws_by_namekey[namekey], key=_draw_sort_key)),
        )
        for namekey, name_key in names_by_namekey.items()
    }


def _derive_ai_augment_outerdicts(
    conn: duckdb.DuckDBPyConnection,
    release_batches: Mapping[str, str],
    *,
    sample_seed: int,
) -> tuple[AiAugmentOuterDict, ...]:
    xlsx_innerdicts = _source_innerdicts_by_namekey(
        conn,
        table_name=XLSX_INNERDICT_TABLE,
        procedure=XlsxMatchProcedure(),
    )
    ssn_innerdicts = _source_innerdicts_by_namekey(
        conn,
        table_name=PARQUET_INNERDICT_TABLE,
        procedure=ParquetMatchProcedure(),
    )
    docx_innerdicts = _source_innerdicts_by_namekey(
        conn,
        table_name=DOCX_INNERDICT_TABLE,
        procedure=DocxMatchProcedure(),
    )
    researchers_by_namekey = _namekeys_and_draws(
        xlsx_innerdicts,
        ssn_innerdicts,
        docx_innerdicts,
    )
    rnd_values = list(
        range(
            AI_AUGMENT_RND_START,
            len(researchers_by_namekey) + AI_AUGMENT_RND_START,
        )
    )
    Random(sample_seed).shuffle(rnd_values)
    rnd_by_namekey = dict(zip(sorted(researchers_by_namekey), rnd_values, strict=True))
    ground_truth = {
        namekey
        for namekey, (_name_key, draws) in researchers_by_namekey.items()
        if GROUND_TRUTH_DEF(namekey, release_batches, draws)
    }
    try:
        partition_rows = conn.execute(
            f"""
            SELECT
                {duckdb_quote_identifier(KTP_NAMEKEY_COL)},
                {duckdb_quote_identifier(KTP_PARTITION_COL)},
                {duckdb_quote_identifier(KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL)},
                {duckdb_quote_identifier(KTP_PARTITION_FLAG_SSN_COUNT_COL)}
            FROM {CARD_PARTITION_TABLE}
            ORDER BY {duckdb_quote_identifier(KTP_NAMEKEY_COL)}
            """
        ).fetchall()
    except duckdb.Error as exc:
        raise ValueError(
            Locale.ELIGIBILITY_FLAGS_MISSING_TEMPLATE.format(
                table_name=CARD_PARTITION_TABLE
            )
        ) from exc
    partition_flags: dict[str, tuple[int, bool, int]] = {}
    for namekey, partition, xlsx_non_exact, ssn_count in partition_rows:
        if (
            not isinstance(namekey, str)
            or not isinstance(partition, int)
            or not isinstance(xlsx_non_exact, bool)
            or not isinstance(ssn_count, int)
            or namekey in partition_flags
        ):
            raise ValueError(
                Locale.SOURCE_CLASSIFICATIONS_INVALID_TEMPLATE.format(
                    table_name=CARD_PARTITION_TABLE
                )
            )
        partition_flags[namekey] = (partition, xlsx_non_exact, ssn_count)
    no_ground_truth = {
        namekey
        for namekey, (partition, xlsx_non_exact, ssn_count) in partition_flags.items()
        if NO_GROUND_TRUTH_DEF(partition, xlsx_non_exact, ssn_count)
    }
    missing_namekeys = no_ground_truth - researchers_by_namekey.keys()
    overlap = ground_truth & no_ground_truth
    if missing_namekeys:
        raise ValueError(Locale.CARD_PARTITION_UNKNOWN_NAMEKEYS)
    if overlap:
        raise ValueError(Locale.COHORTS_OVERLAP)
    if len(ground_truth) != EXPECTED_GROUND_TRUTH_RESEARCHERS:
        raise ValueError(
            Locale.GROUND_TRUTH_CARDINALITY_TEMPLATE.format(
                expected=EXPECTED_GROUND_TRUTH_RESEARCHERS,
                actual=len(ground_truth),
            )
        )
    if len(no_ground_truth) != EXPECTED_NO_GROUND_TRUTH_RESEARCHERS:
        raise ValueError(
            Locale.NO_GROUND_TRUTH_CARDINALITY_TEMPLATE.format(
                expected=EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
                actual=len(no_ground_truth),
            )
        )
    if len(ground_truth | no_ground_truth) != EXPECTED_ELIGIBLE_RESEARCHERS:
        raise ValueError(Locale.ELIGIBLE_COHORT_CARDINALITY_INVALID)
    if set(partition_flags) != set(researchers_by_namekey):
        raise ValueError(Locale.CARD_PARTITION_NAMEKEYS_MISMATCH)

    outerdicts: list[AiAugmentOuterDict] = []
    for namekey, (name_key, draws) in researchers_by_namekey.items():
        ineligibility_category: AiAugmentIneligibilityCategory | None = None
        if namekey in ground_truth:
            cohort = AiAugmentCohort.GROUND_TRUTH
        elif namekey in no_ground_truth:
            cohort = AiAugmentCohort.NO_GROUND_TRUTH
        else:
            cohort = AiAugmentCohort.INELIGIBLE
            partition, xlsx_non_exact, ssn_count = partition_flags[namekey]
            if namekey == EXCLUDED_NAMEKEY:
                ineligibility_category = (
                    AiAugmentIneligibilityCategory.EXCLUDED_DUPLICATE_NAMEKEY
                )
            elif any(
                release_batches.get(draw) == INELIGIBLE_RELEASE_BATCH
                for draw in draws
            ):
                ineligibility_category = (
                    AiAugmentIneligibilityCategory.RELEASE_BATCH_SUBSET_8
                )
            elif partition == KTP_PARTITION_SSN_VALUE:
                ineligibility_category = (
                    AiAugmentIneligibilityCategory.STAGING_PARTITION_2
                )
            elif partition == KTP_PARTITION_DOCX_VALUE and xlsx_non_exact:
                ineligibility_category = (
                    AiAugmentIneligibilityCategory.STAGING_PARTITION_4_XLSX_NON_EXACT
                )
            elif (
                partition == KTP_PARTITION_DOCX_VALUE
                and ssn_count > NO_GROUND_TRUTH_SSN_COUNT
            ):
                ineligibility_category = (
                    AiAugmentIneligibilityCategory.STAGING_PARTITION_4_MULTIPLE_SSN
                )
            else:
                raise ValueError(Locale.INELIGIBILITY_CATEGORY_UNKNOWN)
        outerdicts.append(
            AiAugmentOuterDict(
                namekey=name_key,
                xlsx_innerdicts=xlsx_innerdicts.get(namekey, ()),
                ssn_innerdicts=ssn_innerdicts.get(namekey, ()),
                docx_innerdicts=docx_innerdicts.get(namekey, ()),
                committed_innerdicts=(),
                ai_augment_rnd=rnd_by_namekey[namekey],
                ai_augment_cohort=cohort,
                ai_augment_ineligibility_category=ineligibility_category,
            )
        )

    outerdicts.sort(
        key=lambda outerdict: (
            tuple(_draw_sort_key(draw) for draw in outerdict.draw_numbers),
            outerdict.namekey.first_name.casefold(),
            outerdict.namekey.last_name.casefold(),
            outerdict.namekey.to_json_key(),
        )
    )
    cohort_counts = Counter(outerdict.ai_augment_cohort for outerdict in outerdicts)
    ineligibility_counts = Counter(
        outerdict.ai_augment_ineligibility_category
        for outerdict in outerdicts
        if outerdict.ai_augment_ineligibility_category is not None
    )
    if cohort_counts != {
        AiAugmentCohort.GROUND_TRUTH: EXPECTED_GROUND_TRUTH_RESEARCHERS,
        AiAugmentCohort.NO_GROUND_TRUTH: EXPECTED_NO_GROUND_TRUTH_RESEARCHERS,
        AiAugmentCohort.INELIGIBLE: EXPECTED_INELIGIBLE_RESEARCHERS,
    }:
        raise ValueError(Locale.SOURCE_POPULATION_COHORTS_INVALID)
    if ineligibility_counts != EXPECTED_INELIGIBILITY_COUNTS:
        raise ValueError(Locale.SOURCE_POPULATION_INELIGIBILITY_INVALID)
    if len(outerdicts) != EXPECTED_SOURCE_RESEARCHERS:
        raise ValueError(Locale.SOURCE_POPULATION_CARDINALITY_INVALID)
    if {outerdict.ai_augment_rnd for outerdict in outerdicts} != set(
        range(
            AI_AUGMENT_RND_START,
            EXPECTED_SOURCE_RESEARCHERS + AI_AUGMENT_RND_START,
        )
    ):
        raise ValueError(Locale.SOURCE_POPULATION_RND_INVALID)
    if (
        sum(len(outerdict.draw_numbers) > 1 for outerdict in outerdicts)
        != EXPECTED_MULTIDRAW_SOURCE_RESEARCHERS
    ):
        raise ValueError(Locale.SOURCE_POPULATION_MULTIDRAW_INVALID)
    return tuple(outerdicts)


@implements[BackendComponent.ContextProperty]()
class AiAugmentBackendContext(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    pipeline_config: AiAugmentDetourConfig
    configured_namekey: NameKey | None = None
    cached_ai_augment_outerdicts: tuple[AiAugmentOuterDict, ...] | None = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    def ai_augment_outerdicts_factory(self) -> tuple[AiAugmentOuterDict, ...]:
        if self.cached_ai_augment_outerdicts is not None:
            return self.cached_ai_augment_outerdicts
        release_map = self.pipeline_config.release_map
        if release_map is None:
            raise ValueError(
                Locale.FILES_CONFIG_RESOURCE_MISSING_TEMPLATE.format(
                    resource_key=MAP_SUBSET_0_TO_BATCH_KEY
                )
            )
        release_batches = _load_release_batches(Path(release_map))
        source_conn: duckdb.DuckDBPyConnection | None = None
        try:
            source_conn = duckdb.connect(
                str(self.pipeline_config.db_file),
                read_only=True,
            )
            return _derive_ai_augment_outerdicts(
                source_conn,
                release_batches,
                sample_seed=self.pipeline_config.sample_seed,
            )
        except duckdb.Error as exc:
            raise ValueError(Locale.SOURCE_DUCKDB_VALIDATION_FAILED) from exc
        finally:
            if source_conn is not None:
                source_conn.close()

    @computed_field(repr=False)  # type: ignore[prop-decorator]
    @cached_property
    def ai_augment_outerdicts(self) -> tuple[AiAugmentOuterDict, ...]:
        return self.ai_augment_outerdicts_factory()

    def configured_ai_augment_outerdict(
        self,
    ) -> AiAugmentOuterDict | None:
        if self.configured_namekey is None:
            return None
        matches = tuple(
            outerdict
            for outerdict in self.ai_augment_outerdicts
            if outerdict.namekey == self.configured_namekey
        )
        if len(matches) != 1:
            raise ValueError("configured AI augment outerdict is missing or duplicated")
        return matches[0]
