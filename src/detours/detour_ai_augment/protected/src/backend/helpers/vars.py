import json
from collections.abc import Callable, Mapping
from enum import StrEnum
from pathlib import Path

from src.helpers.vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL

PYDANTIC_TO_PASTE_SOURCE = Path(
    "src/detours/detour_ai_augment/protected/src/backend/helpers/data_models/"
    "pydantic_to_paste.py"
).read_text(encoding="utf-8").rstrip()

AI_AUGMENT_COLUMN_PREFIX = "ktp.ai_augment_"

KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL = f"{AI_AUGMENT_COLUMN_PREFIX}researcher_author"
KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL = f"{AI_AUGMENT_COLUMN_PREFIX}place_of_residence"
KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}race_ethnicity_language_culture"
)
KTP_AI_AUGMENT_GENDER_COL = f"{AI_AUGMENT_COLUMN_PREFIX}gender"
KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}age_first_publication_according_to_openalex_profile"
)
KTP_AI_AUGMENT_EDUCATION_COL = f"{AI_AUGMENT_COLUMN_PREFIX}education"
KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}academic_position_s_"
KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL = f"{AI_AUGMENT_COLUMN_PREFIX}social_capital"
KTP_AI_AUGMENT_LINKS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}links_"
KTP_AI_AUGMENT_COMMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}comments"
AI_AUGMENT_EVIDENCE_COLUMNS = (
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    KTP_AI_AUGMENT_LINKS_COL,
)
AI_AUGMENT_COLUMNS = AI_AUGMENT_EVIDENCE_COLUMNS + (KTP_AI_AUGMENT_COMMENTS_COL,)
AI_AUGMENT_STANDARDIZED_SUFFIX = "_standardized"
AI_AUGMENT_STANDARDIZED_COLUMNS = tuple(
    f"{column}{AI_AUGMENT_STANDARDIZED_SUFFIX}"
    for column in AI_AUGMENT_EVIDENCE_COLUMNS
)
AI_AUGMENT_EVIDENCE_STANDARDIZED_PAIRS = tuple(
    zip(
        AI_AUGMENT_EVIDENCE_COLUMNS,
        AI_AUGMENT_STANDARDIZED_COLUMNS,
        strict=True,
    )
)

KTP_AI_AUGMENT_COMMIT_RECORD_ID_COL = f"{AI_AUGMENT_COLUMN_PREFIX}commit_record_id"
KTP_AI_AUGMENT_COMMIT_REQUEST_BODY_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}commit_request_body"
)
KTP_AI_AUGMENT_SESSION_METADATA_COL = f"{AI_AUGMENT_COLUMN_PREFIX}session_metadata"
KTP_AI_AUGMENT_FOOTNOTES_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnotes"
KTP_AI_AUGMENT_FOOTNOTE_ARGUMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}footnote_arguments"

TEXT_ENCODING = "utf-8"

AI_AUGMENT_RND_START = 1

CONFIG_FILENAME = "config_ai_augment.json"
MAP_SUBSET_0_TO_BATCH_KEY = "map_subset_0_to_batch"
REPLAY_LOG_KEY = "detour_ai_augment_backend_api_replay_log"

# ground truth is defined explicitly by released batch, exclusive of dupe
GROUND_TRUTH_RELEASE_BATCHES = frozenset({"subset 1", "subset 5", "subset 6", "subset 7"})
EXCLUDED_NAMEKEY = json.dumps(
    {KTP_FIRST_NAME_COL: "Mercouri G.", KTP_LAST_NAME_COL: "Kanatzidis"},
    sort_keys=True,
)
GROUND_TRUTH_DEF: Callable[
    [str, Mapping[str, str], tuple[str, ...]],
    bool,
] = lambda namekey, release_batches, draws: (
    namekey != EXCLUDED_NAMEKEY
    and any(release_batches.get(draw) in GROUND_TRUTH_RELEASE_BATCHES for draw in draws)
)
# no ground truth is defined analytically from all unreleased except some
NO_GROUND_TRUTH_PARTITION = 4
NO_GROUND_TRUTH_SSN_COUNT = 1
NO_GROUND_TRUTH_DEF: Callable[
    [int, bool, int],
    bool,
] = lambda partition, xlsx_non_exact, ssn_count: (
    partition == NO_GROUND_TRUTH_PARTITION
    and not xlsx_non_exact
    and ssn_count == NO_GROUND_TRUTH_SSN_COUNT
)

INELIGIBLE_RELEASE_BATCH = "subset 8"

class AiAugmentCohort(StrEnum):
    GROUND_TRUTH = "ground_truth"
    NO_GROUND_TRUTH = "no_ground_truth"
    INELIGIBLE = "ineligible"


class AiAugmentIneligibilityCategory(StrEnum):
    EXCLUDED_DUPLICATE_NAMEKEY = "excluded_duplicate_namekey"
    RELEASE_BATCH_SUBSET_8 = "release_batch_subset_8"
    STAGING_PARTITION_2 = "staging_partition_2"
    STAGING_PARTITION_4_XLSX_NON_EXACT = "staging_partition_4_xlsx_non_exact"
    STAGING_PARTITION_4_MULTIPLE_SSN = "staging_partition_4_multiple_ssn"
