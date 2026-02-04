from typing import Final

KTP_FIRST_NAME_COL: Final = "ktp.first_name"
KTP_LAST_NAME_COL: Final = "ktp.last_name"
KTP_FIRST_NAME_ORIG_COLNAME_COL: Final = "ktp.first_name_original_column_name"
KTP_LAST_NAME_ORIG_COLNAME_COL: Final = "ktp.last_name_original_column_name"
KTP_FILENAME_COL: Final = "ktp.filename"
KTP_SOURCE_KEY_COL: Final = "ktp.source_key"
KTP_ECONOMIES_COL: Final = "ktp.economies"
KTP_PRIORITY_COL: Final = "ktp.priority"
KTP_PRIORITY_GROUP_COL: Final = "ktp.priority_group"
DRAW_LABEL: Final = "ktp.draw_number"
RIGHT_NAME_COL: Final = "Researcher/author"
KTP_FRAGMENT_COL: Final = "ktp.fragment"

HCR_FILENAME_COL: Final = "hcr.filename"
HCR_ROW_COL: Final = "hcr.row_number"
KTP_POPULATION_INDEX_COL: Final = "ktp.population_index"
DOCX_TABLE_INDEX_COL: Final = "ktp.docx_table_index"
DOCX_ROW_INDEX_COL: Final = "ktp.docx_row_index"
DOCX_FRAGMENT_COL: Final = "ktp.docx_fragment"
CSV_ROW_INDEX_COL: Final = "ktp.csv_row_index"

KTP_PRIORITY_GROUP_LABELS: Final[dict[int, str]] = {
    1: "non_target",
    2: "greater_china",
    3: "non_english_non_eu_hic",
    4: "eu",
    5: "other",
}

# Filled later by user: mapping of XLSX filename -> (first_name_col, last_name_col)
HCR_XLSX_NAME_COLS: Final[dict[str, tuple[str, str]]] = {}

COUNTRY_PREFIX: Final = ", "
ENGLISH_HICS: Final[list[str]] = [
    "United States",
    "USA",
    "U.S.A.",
    "US",
    "U.S.",
    "United Kingdom",
    "UK",
    "U.K.",
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
