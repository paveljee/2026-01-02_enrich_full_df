from dataclasses import dataclass
from enum import StrEnum


class SourceCohort(StrEnum):
    GROUND_TRUTH = "ground_truth"
    NO_GROUND_TRUTH = "no_ground_truth"
    INELIGIBLE = "ineligible"


class IneligibilityCategory(StrEnum):
    EXCLUDED_DUPLICATE_NAMEKEY = "excluded_duplicate_namekey"
    RELEASE_BATCH_SUBSET_8 = "release_batch_subset_8"
    STAGING_PARTITION_2 = "staging_partition_2"
    STAGING_PARTITION_4_XLSX_NON_EXACT = "staging_partition_4_xlsx_non_exact"
    STAGING_PARTITION_4_MULTIPLE_SSN = "staging_partition_4_multiple_ssn"


@dataclass(frozen=True)
class SourceResearcher:
    namekey: str
    first_name: str
    last_name: str
    draw_numbers: tuple[str, ...]
    xlsx_rows: tuple[dict[str, object], ...]
    docx_rows: tuple[dict[str, object], ...]
    ssn_rows: tuple[dict[str, object], ...]
    cohort: str


@dataclass(frozen=True)
class SourcePopulationRow:
    namekey: str
    rnd: int
    first_name: str
    last_name: str
    draw_numbers: tuple[str, ...]
    cohort: SourceCohort
    ineligibility_category: IneligibilityCategory | None
