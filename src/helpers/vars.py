from __future__ import annotations

from typing import Final

CARD_INTRODUCTION = """## Introduction
**Draw number** is the sequential order in which rows were sampled from HCR tables.

Name is displayed as **Last Name, First Name**.

Last modified (introduction): February 24, 2026

Date of report: {}
"""

HCR_XLSX_KEY_PREFIX = "hcr_xlsx_"
WORLD_BANK_XLSX_KEY = "world_bank_xlsx"
WORLD_BANK_INCOME_FISCAL_YEAR: Final = "FY26"
WORLD_BANK_FORMER_ECONOMY_CODES: Final[set[str]] = {
    "ANT",
    "CSK",
    "MYT",
    "SUN",
    "YUG",
    "YUGf",
}
REQUIRED_FILES_CONFIG_KEYS: Final[set[str]] = {
    "hit_papers_0",
    "hit_papers_1",
    "authors_paper",
    "paper_author_affiliation",
    "affiliations",
    "author_details",
    "authors",
    "fields",
    WORLD_BANK_XLSX_KEY,
}
REQUIRED_FILE_ENTRY_KEYS: Final[set[str]] = {"path", "sha256", "desc"}

KTP_FIRST_NAME_COL: Final = "ktp.first_name"
KTP_LAST_NAME_COL: Final = "ktp.last_name"
KTP_FIRST_NAME_ORIG_COLNAME_COL: Final = "ktp.first_name_original_column_name"
KTP_LAST_NAME_ORIG_COLNAME_COL: Final = "ktp.last_name_original_column_name"
KTP_FILENAME_COL: Final = "ktp.filename"
KTP_FRAGMENT_TYPE_COL: Final = "ktp.fragment_type"
KTP_SOURCE_KEY_COL: Final = "ktp.source_key"
KTP_ECONOMIES_COL: Final = "ktp.hcr_world_bank_economies"
KTP_ECONOMIES_ISO_COL: Final = "ktp.hcr_world_bank_economies_iso"
KTP_ECONOMIES_INCOME_GROUP_COL: Final = "ktp.hcr_world_bank_economies_income_group"
KTP_ECONOMY_MATCH_COL: Final = "ktp.hcr_world_bank_economies_match"
KTP_PRIORITY_COL: Final = "ktp.priority"
KTP_PRIORITY_GROUP_COL: Final = "ktp.priority_label"
KTP_HCR_PRIMARY_AFFILIATIONS_COL: Final = "ktp.hcr_primary_affiliations"
KTP_HCR_SECONDARY_AFFILIATIONS_COL: Final = "ktp.hcr_secondary_affiliations"
DRAW_LABEL: Final = "ktp.draw_number"
RIGHT_NAME_COL: Final = "Researcher/author"
KTP_FRAGMENT_COL: Final = "ktp.fragment"
SSNAD_FILENAME_COL: Final = "ssnad.filename"
SSNAD_DISPLAY_NAME_COL: Final = "ssnad.display_name"
SSNAD_DISPLAY_NAME_ALTERNATIVES_COL: Final = "ssnad.display_name_alternatives"
SSNAD_WORKS_COUNT_COL: Final = "ssnad.works_count"
SSNAD_CITED_BY_COUNT_COL: Final = "ssnad.cited_by_count"
SSNAD_WORKS_API_URL_COL: Final = "ssnad.works_api_url"
SSNAU_FILENAME_COL: Final = "ssnau.filename"
SSNAP_FILENAME_COL: Final = "ssnap.filename"
SSNHPL0_FILENAME_COL: Final = "ssnhpl0.filename"
SSNHPL1_FILENAME_COL: Final = "ssnhpl1.filename"
SSNF_FILENAME_COL: Final = "ssnf.filename"
SSNPAA_FILENAME_COL: Final = "ssnpaa.filename"
SSNAF_FILENAME_COL: Final = "ssnaf.filename"
KTP_SSN_SUM_HIT_1PCT_COL: Final = "ktp.ssn_sum_hit_1pct"
SSN_PAPERIDS_LEVEL0_COL: Final = "ssn.paperids_level0"
SSN_PAPERIDS_LEVEL1_COL: Final = "ssn.paperids_level1"
SSN_FIELD_IDS_LIST_COL: Final = "ssn.field_ids_list"
KTP_SSN_TOP_PAPERS_HIT_1PCT_COL: Final = "ktp.ssn_top_papers_hit_1pct"
KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL: Final = "ktp.ssn_field_display_names_list"
KTP_SSN_TOP_INSTITUTIONS_COL: Final = "ktp.ssn_top_institutions"
SSNPAA_INSTITUTION_ID_COL: Final = "ssnpaa.institution_id"
SSNAF_DISPLAY_NAME_COL: Final = "ssnaf.display_name"
KTP_SSN_COUNT_PAPERID_COL: Final = "ktp.ssn_count_paperid"
TOP_K_WORKS: Final = 5
TOP_K_INSTITUTIONS: Final = 5

STEP_MATCH_PARQUET_LOG_TAG_LEGEND: Final = "LEGEND"
STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET: Final = "TABLE/PARQUET"
STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT: Final = "TABLE/INNERDICT"
STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF: Final = "TABLE/EFF"
STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER: Final = "VIEW/FILTER"
STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT: Final = "VIEW/OUTPUT"
STEP_MATCH_PARQUET_LOG_TAG_OUTERDICT: Final = "OUTERDICT"
STEP_MATCH_PARQUET_LOG_LEGEND_LINES: Final[tuple[str, ...]] = (
    (
        f"[{STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET}]=parquet-derived tables we most want "
        "to preserve; "
    ),
    (
        f"[{STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT}]=materialized tables that feed "
        "recoverable innerdict/output artifacts; "
    ),
    (
        f"[{STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF}]=materialized for efficiency only; "
    ),
    (
        f"[{STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER}]/[{STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT}]"
        "=ephemeral views; "
    ),
    (
        f"[{STEP_MATCH_PARQUET_LOG_TAG_OUTERDICT}]=append/load actions."
    ),
)

HCR_FILENAME_COL: Final = "hcr.filename"
HCR_ROW_COL: Final = "hcr.row_number"
HCR_FIRST_NAME_COL: Final = "hcr.first_name"
HCR_LAST_NAME_COL: Final = "hcr.last_name"
HCR_CATEGORY_COL: Final = "hcr.category"
KTP_POPULATION_INDEX_COL: Final = "ktp.population_index"
DOCX_TABLE_INDEX_COL: Final = "ktp.docx_table_index"
DOCX_ROW_INDEX_COL: Final = "ktp.docx_row_index"
DOCX_FRAGMENT_COL: Final = "ktp.docx_fragment"
CSV_ROW_INDEX_COL: Final = "ktp.csv_row_index"

KTP_XLSX_MATCH_COL: Final = "ktp.xlsx_match"
KTP_DOCX_MATCH_COL: Final = "ktp.docx_match"
KTP_SSNAD_MATCH_COL: Final = "ktp.ssnad_match"
KTP_PARTITION_COL: Final = "ktp.partition"
KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: Final = (
    "ktp.partition_flag_xlsx_non_exact_any"
)
KTP_PARTITION_FLAG_XLSX_ANY_COL: Final = "ktp.partition_flag_xlsx_any"
KTP_PARTITION_FLAG_SCISCINET_COUNT_COL: Final = "ktp.partition_flag_sciscinet_count"
KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: Final = (
    "ktp.partition_flag_docx_table_1_required_all"
)
KTP_PARTITION_FLAG_DOCX_ANY_COL: Final = "ktp.partition_flag_docx_any"
KTP_FF_DISCARD_COL: Final = "ktp.ff_discard"
KTP_FF_NOTE_COL: Final = "ktp.ff_note"
KTP_PARTITION_NO_RESOLUTION_VALUE: Final = 0
KTP_PARTITION_XLSX_VALUE: Final = 1
KTP_PARTITION_SCISCINET_VALUE: Final = 2
KTP_PARTITION_DOCX_VALUE: Final = 4
CARD_PARTITION_ARTIFACT_MODES: Final[set[int]] = {1, 2}
KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY: Final = "ktp.source_key_first_name_norm_tok"
KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY: Final = "ktp.source_key_last_name_norm"
KTP_XLSX_MATCH_FIRST_TOKENS_KEY: Final = "ktp.first_name_norm_tok"
KTP_XLSX_MATCH_LAST_NAME_NORM_KEY: Final = "ktp.last_name_norm"
KTP_DOCX_MATCH_KTP_FIRST_NORM_KEY: Final = "ktp.source_key_first_name_norm"
KTP_DOCX_MATCH_KTP_LAST_NORM_KEY: Final = "ktp.source_key_last_name_norm"
KTP_DOCX_MATCH_DOCX_NAME_NORM_KEY: Final = "ktp.table_1_researcher_author_norm"
KTP_SSNAD_MATCH_KTP_NAME_NORM_KEY: Final = "ktp.source_key_norm"
KTP_SSNAD_MATCH_SSNAD_NAME_NORM_KEY: Final = "ktp.ssnad_display_name_norm"
KTP_DOCX_ROW_NUMBER_COL: Final = "ktp.table_1_row_number"
KTP_DOCX_FOOTNOTES_COL: Final = "ktp.table_1_footnotes"
KTP_DOCX_COMMENTS_COL: Final = "ktp.table_1_comments"
KTP_DOCX_TABLE_1_PREFIX: Final = "ktp.table_1_"
KTP_DOCX_OPTIONAL_EMPTY_COLS: Final[set[str]] = {
    "ktp.table_1_socioeconomic_status",
    "ktp.table_1_race_ethnicity_language_culture",
    "ktp.table_1_topics",
    KTP_DOCX_FOOTNOTES_COL,
    KTP_DOCX_COMMENTS_COL,
}
KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS: Final[set[str]] = {
    "-",
    "–",
    "—",
    "−",
    "NR",
}
CARD_BUILD_SUBSET_DESCRIPTIONS: Final[dict[int, str]] = {
    0: "all name keys (no filtering)",
    1: (
        "Exactly one sciscinet innerdict, at least one present ktp.xlsx_match payload and "
        "all present ktp.xlsx_match payloads are exact, and at least one docx innerdict with "
        "all required present ktp.table_1_* fields non-empty. "
        "For ktp.table_1_* fields, non-empty is required except these " 
        f"allowed-empty fields: {sorted(KTP_DOCX_OPTIONAL_EMPTY_COLS)!r}"
    ),
    2: (
        "Remaining name keys (zero or >1 sciscinet innerdict, no present ktp.xlsx_match "
        "payload, any non-exact ktp.xlsx_match, no docx innerdict, or any empty required "
        "ktp.table_1_* value). "
        "For ktp.table_1_* fields, non-empty is required except these " 
        f"allowed-empty fields: {sorted(KTP_DOCX_OPTIONAL_EMPTY_COLS)!r}"
    ),
    3: (
        "Exactly one sciscinet innerdict, at least one present ktp.xlsx_match payload, and "
        "all present ktp.xlsx_match payloads are exact."
    ),
    4: (
        "Remaining name keys (zero or >1 sciscinet innerdict, no present ktp.xlsx_match "
        "payload, or any non-exact ktp.xlsx_match)."
    ),
}

STEP_REGISTER_RESOURCES: Final = "01_register_resources"
STEP_LOAD_XLSX: Final = "02_load_xlsx"
STEP_INFER_NAMES: Final = "03_infer_names"
STEP_ADD_ECONOMY_PRIORITY: Final = "04_add_economy_priority"
STEP_SAMPLE_POPULATION: Final = "05_sample_population"
STEP_BUILD_OUTERDICT: Final = "06_build_outerdict"
STEP_MATCH_XLSX: Final = "07_match_xlsx"
STEP_MATCH_DOCX: Final = "08_match_docx"
STEP_MATCH_PARQUET: Final = "09_match_parquet"
STEP_BUILD_CARDS: Final = "10_build_cards"
STEP_BUILD_OUTERDICT_EXCLUDED_LOG_MAX_ROWS: Final = 4

STEP_ORDER: Final[list[str]] = [
    STEP_REGISTER_RESOURCES,
    STEP_LOAD_XLSX,
    STEP_INFER_NAMES,
    STEP_ADD_ECONOMY_PRIORITY,
    STEP_SAMPLE_POPULATION,
    STEP_BUILD_OUTERDICT,
    STEP_MATCH_XLSX,
    STEP_MATCH_DOCX,
    STEP_MATCH_PARQUET,
    STEP_BUILD_CARDS,
]

KTP_PRIORITY_GROUP_LABELS: Final[dict[int, str]] = {
    1: "LMICS_NO_GREATER_CHINA_OR_UNKNOWN",
    2: "GREATER_CHINA",
    3: "NON_ENGLISH_NON_EU_HICS_NO_GREATER_CHINA",
    4: "EU_COUNTRIES",
    5: "ENGLISH_HICS",
}

OGHIST_INCOME_LABELS = {
    "H": "High income countries",
    "L": "Low income LMICs",
    "LM": "Lower middle income LMICs",
    "UM": "Upper middle income LMICs",
}

# Source: GPT-5.2 via chatgpt.com, inference date: 2026-02-04
# Updated with GPT-5.2-Codex via Codex app for macOS, same date
# Revised manually by Pavel Zhelnov on the same date
# Keys are as in OGHIST_2025_07_01.xlsx
KTP_COUNTRY_ALIASES = {
    # Big common ones
    "United States": [
        "USA",
        "U.S.A.",
        "US",
        "U.S.",
        "United States of America",
        "America",
        "United State",
        "Stanford University",
        "E.I. Dupont de Nemours Co.",
        "Urban Design 4 Health, Inc.",
    ],
    "United Kingdom": [
        "UK",
        "U.K.",
        "Great Britain",
        "Britain",
        "GB",
        "G.B.",
        "England",
    ],

    # Koreas
    "Korea, Rep.": [
        "South Korea",
        "Republic of Korea",
        "Korea (South)",
        "ROK",
        "KOR",
        "Korea, Republic of",
    ],
    "Korea, Dem. Rep.": ["North Korea", "Democratic People's Republic of Korea", "DPRK", "PRK"],

    # Congo pair
    "Congo, Dem. Rep.": [
        "Democratic Republic of the Congo",
        "DR Congo",
        "D.R. Congo",
        "Congo (DRC)",
        "Congo-Kinshasa",
        "Dem. Rep. Congo",
        "COD",
    ],
    "Congo, Rep.": [
        "Republic of the Congo",
        "Congo Republic",
        "Congo-Brazzaville",
        "COG",
    ],

    # Diacritics / punctuation / common English names
    "Côte d'Ivoire": ["Cote d'Ivoire", "Cote dIvoire", "Ivory Coast"],
    "Curaçao": ["Curacao"],
    "São Tomé and Príncipe": [
        "Sao Tome and Principe",
        "São Tomé & Príncipe",
        "Sao Tome & Principe",
    ],
    "Türkiye": ["Turkey", "Turkiye"],

    # “The” / comma variants
    "Bahamas, The": ["The Bahamas", "Bahamas"],
    "Gambia, The": ["The Gambia", "Gambia"],
    "Egypt, Arab Rep.": ["Egypt", "Arab Republic of Egypt"],
    "Iran, Islamic Rep.": ["Iran", "Islamic Republic of Iran"],
    "Venezuela, RB": ["Venezuela", "Bolivarian Republic of Venezuela"],
    "Yemen, Rep.": ["Yemen", "Republic of Yemen"],
    "Russian Federation": ["Russia", "Russian Fed.", "RF"],
    "Syrian Arab Republic": ["Syria"],
    "Hong Kong SAR, China": ["Hong Kong", "Hong Kong SAR"],
    "Macao SAR, China": ["Macao", "Macau", "Macau SAR", "Macao SAR"],
    "Taiwan, China": ["Taiwan", "Chinese Taipei", "Republic of China", "ROC"],

    # Institution / shorthand aliases seen in HCR affiliations
    "Finland": ["University of Helsinki"],
    "Saudi Arabia": [
        "King Abdullah University of Science and Technology",
    ],

    # Split/long official names commonly shortened
    "Czechia": ["Czech"],
    "Slovak Republic": ["Slovakia"],
    "Kyrgyz Republic": ["Kyrgyzstan"],
    "Lao PDR": ["Laos", "Lao People's Democratic Republic"],
    "Micronesia, Fed. Sts.": ["Federated States of Micronesia", "Micronesia", "FSM"],
    "West Bank and Gaza": [
        "Palestine",
        "State of Palestine",
        "Palestinian Territories",
        "Occupied Palestinian Territory",
        "OPT",
    ],
    "United Arab Emirates": ["UAE", "U.A.E.", "Emirates"],
    "Brunei Darussalam": ["Brunei"],
    "Bolivia": ["Bolivia (Plurinational State of)", "Plurinational State of Bolivia"],
    "Tanzania": ["United Republic of Tanzania", "Tanzania, United Rep."],
    "Viet Nam": ["Vietnam"],
    "Cabo Verde": ["Cape Verde"],
    "Eswatini": ["Swaziland"],

    # Territories / parentheses / common shortenings
    "Virgin Islands (U.S.)": [
        "U.S. Virgin Islands",
        "US Virgin Islands",
        "United States Virgin Islands",
        "USVI",
        "U.S.V.I.",
    ],
    "Puerto Rico (U.S.)": ["Puerto Rico", "PR"],
    "Sint Maarten (Dutch part)": ["Sint Maarten", "St. Maarten"],
    "St. Martin (French part)": ["Saint Martin", "St Martin"],
    "Turks and Caicos Islands": ["Turks & Caicos Islands", "Turks and Caicos", "T&C", "TCI"],
    "British Virgin Islands": ["BVI", "B.V.I.", "Virgin Islands, British"],
    "Faeroe Islands": ["Faroe Islands", "Faroes"],
    # "Channel Islands": ["Jersey", "Guernsey"],  # mismatch with New Jersey

    # “St.” variants (people often type either way)
    "St. Kitts and Nevis": ["Saint Kitts and Nevis", "St Kitts and Nevis", "St Kitts & Nevis"],
    "St. Lucia": ["Saint Lucia", "St Lucia"],
    "St. Vincent and the Grenadines": [
        "Saint Vincent and the Grenadines",
        "St Vincent and the Grenadines",
        "St Vincent & the Grenadines",
    ],
    "Antigua and Barbuda": ["Antigua & Barbuda"],
    "Trinidad and Tobago": ["Trinidad & Tobago"],
}

# Filled later by user: mapping of XLSX filename -> (first_name_col, last_name_col)
HCR_XLSX_NAME_COLS: Final[dict[str, tuple[str, str]]] = {}
# Filled later by user: mapping of XLSX filename -> (primary, secondary) affiliation cols
HCR_XLSX_AFFILIATIONS_COLS: Final[dict[str, tuple[list[str], list[str]]]] = {}

COUNTRY_PREFIX: Final = ", "
ENGLISH_HICS: Final[list[str]] = [
    "United States",
    "United Kingdom",
    "Australia",
    "Canada",
    "New Zealand",
]
GREATER_CHINA: Final[list[str]] = ["China", "Hong Kong", "Macau", "Taiwan"]
EU_COUNTRIES: Final[list[str]] = [
    "Austria",
    "Belgium",
    "Bulgaria",
    "Croatia",
    "Cyprus",
    "Czechia",
    "Denmark",
    "Estonia",
    "Finland",
    "France",
    "Germany",
    "Greece",
    "Hungary",
    "Ireland",
    "Italy",
    "Latvia",
    "Lithuania",
    "Luxembourg",
    "Malta",
    "Netherlands",
    "Poland",
    "Portugal",
    "Romania",
    "Slovakia",
    "Slovenia",
    "Spain",
    "Sweden",
]
HIGH_INCOME_COUNTRIES_FY2025: Final[list[str]] = [
    "American Samoa",
    "Andorra",
    "Antigua and Barbuda",
    "Aruba",
    "Australia",
    "Austria",
    "Bahamas, The",
    "Bahrain",
    "Barbados",
    "Belgium",
    "Bermuda",
    "British Virgin Islands",
    "Brunei Darussalam",
    "Bulgaria",
    "Canada",
    "Cayman Islands",
    "Channel Islands",
    "Chile",
    "Croatia",
    "Curaçao",
    "Cyprus",
    "Czechia",
    "Denmark",
    "Estonia",
    "Faeroe Islands",
    "Finland",
    "France",
    "French Polynesia",
    "Germany",
    "Gibraltar",
    "Greece",
    "Greenland",
    "Guam",
    "Guyana",
    "Hong Kong SAR, China",
    "Hungary",
    "Iceland",
    "Ireland",
    "Isle of Man",
    "Israel",
    "Italy",
    "Japan",
    "Korea, Rep.",
    "Kuwait",
    "Latvia",
    "Liechtenstein",
    "Lithuania",
    "Luxembourg",
    "Macao SAR, China",
    "Malta",
    "Monaco",
    "Nauru",
    "Netherlands",
    "New Caledonia",
    "New Zealand",
    "Northern Mariana Islands",
    "Norway",
    "Oman",
    "Palau",
    "Panama",
    "Poland",
    "Portugal",
    "Puerto Rico (U.S.)",
    "Qatar",
    "Romania",
    "Russian Federation",
    "San Marino",
    "Saudi Arabia",
    "Seychelles",
    "Singapore",
    "Sint Maarten (Dutch part)",
    "Slovak Republic",
    "Slovenia",
    "Spain",
    "St. Kitts and Nevis",
    "St. Martin (French part)",
    "Sweden",
    "Switzerland",
    "Taiwan, China",
    "Trinidad and Tobago",
    "Turks and Caicos Islands",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "Uruguay",
    "Virgin Islands (U.S.)",
]

PILOT_NAME_CATEGORY_TRIPLES: Final[list[tuple[str, str, str]]] = [
    ("Bin", "Gao", "Cross-Field"),
    ("Beatriz Roldan", "Cuenya", "Chemistry"),
    ("Lizhi", "Zhang", "Chemistry"),
    ("Rudolf A.", "de Boer", "Clinical Medicine"),
    ("Hidenori", "Arai", "Cross-Field"),
    ("Mark A.", "Bradford", "Cross-Field"),
    ("Salim", "Yusuf", "Clinical Medicine"),
    ("Nicholas C.", "Turner", "Clinical Medicine"),
    ("Osman M.", "Bakr", "Chemistry"),
    ("Rainer", "Blatt", "Physics"),
]

__all__ = [
    "CSV_ROW_INDEX_COL",
    "DOCX_FRAGMENT_COL",
    "DOCX_ROW_INDEX_COL",
    "DOCX_TABLE_INDEX_COL",
    "DRAW_LABEL",
    "HCR_FILENAME_COL",
    "HCR_FIRST_NAME_COL",
    "HCR_LAST_NAME_COL",
    "HCR_CATEGORY_COL",
    "HCR_ROW_COL",
    "HCR_XLSX_AFFILIATIONS_COLS",
    "HCR_XLSX_NAME_COLS",
    "HCR_XLSX_KEY_PREFIX",
    "WORLD_BANK_XLSX_KEY",
    "WORLD_BANK_FORMER_ECONOMY_CODES",
    "WORLD_BANK_INCOME_FISCAL_YEAR",
    "REQUIRED_FILES_CONFIG_KEYS",
    "REQUIRED_FILE_ENTRY_KEYS",
    "KTP_ECONOMIES_COL",
    "KTP_ECONOMIES_ISO_COL",
    "KTP_ECONOMIES_INCOME_GROUP_COL",
    "KTP_ECONOMY_MATCH_COL",
    "KTP_FILENAME_COL",
    "KTP_FRAGMENT_TYPE_COL",
    "KTP_FIRST_NAME_COL",
    "KTP_FRAGMENT_COL",
    "KTP_LAST_NAME_COL",
    "KTP_HCR_PRIMARY_AFFILIATIONS_COL",
    "KTP_HCR_SECONDARY_AFFILIATIONS_COL",
    "KTP_POPULATION_INDEX_COL",
    "KTP_PRIORITY_COL",
    "KTP_PRIORITY_GROUP_COL",
    "KTP_SOURCE_KEY_COL",
    "SSNAD_FILENAME_COL",
    "SSNAU_FILENAME_COL",
    "SSNAP_FILENAME_COL",
    "SSNHPL0_FILENAME_COL",
    "SSNHPL1_FILENAME_COL",
    "SSNF_FILENAME_COL",
    "KTP_SSN_SUM_HIT_1PCT_COL",
    "SSN_PAPERIDS_LEVEL0_COL",
    "SSN_PAPERIDS_LEVEL1_COL",
    "SSN_FIELD_IDS_LIST_COL",
    "KTP_SSN_TOP_PAPERS_HIT_1PCT_COL",
    "KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL",
    "KTP_SSN_TOP_INSTITUTIONS_COL",
    "SSNPAA_FILENAME_COL",
    "SSNAF_FILENAME_COL",
    "SSNPAA_INSTITUTION_ID_COL",
    "SSNAF_DISPLAY_NAME_COL",
    "KTP_SSN_COUNT_PAPERID_COL",
    "TOP_K_WORKS",
    "TOP_K_INSTITUTIONS",
    "STEP_MATCH_PARQUET_LOG_TAG_LEGEND",
    "STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET",
    "STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT",
    "STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF",
    "STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER",
    "STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT",
    "STEP_MATCH_PARQUET_LOG_TAG_OUTERDICT",
    "STEP_MATCH_PARQUET_LOG_LEGEND_LINES",
    "PILOT_NAME_CATEGORY_TRIPLES",
    "RIGHT_NAME_COL",
    "COUNTRY_PREFIX",
    "ENGLISH_HICS",
    "EU_COUNTRIES",
    "GREATER_CHINA",
    "HIGH_INCOME_COUNTRIES_FY2025",
    "KTP_FIRST_NAME_ORIG_COLNAME_COL",
    "KTP_LAST_NAME_ORIG_COLNAME_COL",
    "KTP_DOCX_FOOTNOTES_COL",
    "KTP_DOCX_COMMENTS_COL",
    "KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS",
    "KTP_PRIORITY_GROUP_LABELS",
]
