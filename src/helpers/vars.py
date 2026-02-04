from __future__ import annotations

from typing import Final

KTP_FIRST_NAME_COL: Final = "ktp.first_name"
KTP_LAST_NAME_COL: Final = "ktp.last_name"
KTP_FIRST_NAME_ORIG_COLNAME_COL: Final = "ktp.first_name_original_column_name"
KTP_LAST_NAME_ORIG_COLNAME_COL: Final = "ktp.last_name_original_column_name"
KTP_FILENAME_COL: Final = "ktp.filename"
KTP_SOURCE_KEY_COL: Final = "ktp.source_key"
KTP_ECONOMIES_COL: Final = "ktp.world_bank_economies"
KTP_ECONOMIES_INCOME_GROUP_COL: Final = "ktp.world_bank_economies_income_group"
KTP_ECONOMY_MATCH_COL: Final = "ktp.world_bank_economies_match"
KTP_PRIORITY_COL: Final = "ktp.priority"
KTP_PRIORITY_GROUP_COL: Final = "ktp.priority_label"
KTP_HCR_PRIMARY_AFFILIATIONS_COL: Final = "ktp.hcr_primary_affiliations"
KTP_HCR_SECONDARY_AFFILIATIONS_COL: Final = "ktp.hcr_secondary_affiliations"
DRAW_LABEL: Final = "ktp.draw_number"
RIGHT_NAME_COL: Final = "Researcher/author"
KTP_FRAGMENT_COL: Final = "ktp.fragment"

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
KTP_DOCX_ROW_NUMBER_COL: Final = "ktp.table_1_row_number"
KTP_DOCX_TABLE_1_PREFIX: Final = "ktp.table_1_"

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
    "KTP_ECONOMIES_COL",
    "KTP_ECONOMIES_INCOME_GROUP_COL",
    "KTP_ECONOMY_MATCH_COL",
    "KTP_FILENAME_COL",
    "KTP_FIRST_NAME_COL",
    "KTP_FRAGMENT_COL",
    "KTP_LAST_NAME_COL",
    "KTP_HCR_PRIMARY_AFFILIATIONS_COL",
    "KTP_HCR_SECONDARY_AFFILIATIONS_COL",
    "KTP_POPULATION_INDEX_COL",
    "KTP_PRIORITY_COL",
    "KTP_PRIORITY_GROUP_COL",
    "KTP_SOURCE_KEY_COL",
    "PILOT_NAME_CATEGORY_TRIPLES",
    "RIGHT_NAME_COL",
    "COUNTRY_PREFIX",
    "ENGLISH_HICS",
    "EU_COUNTRIES",
    "GREATER_CHINA",
    "HIGH_INCOME_COUNTRIES_FY2025",
    "KTP_FIRST_NAME_ORIG_COLNAME_COL",
    "KTP_LAST_NAME_ORIG_COLNAME_COL",
    "KTP_PRIORITY_GROUP_LABELS",
]
