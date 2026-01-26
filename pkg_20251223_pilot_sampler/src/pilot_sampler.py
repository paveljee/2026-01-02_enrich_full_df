#### INTRO ####
# For piloting, 10 researchers were selected from the 2024 sample data (i.e., from `collated_sample_data.csv` from spreadsheet.zip, sha256:2965ec37e000bcebd4a374f1f34721997eb03b7f605863e10145ce675fc301ef, available from: <https://github.com/paveljee/research-integrity-ktp/releases/tag/v0.1.0-pilot.1751566592>) by randomly AI generated numbers; the first-last name pairs were reported in interim pilot results from 2025-07-24.
#
# This script is solely for cleanly producing a 2025-08-19_sampler-produced random samples-compatible table for pilot data from the original `2024_HCR.xlsx` Highly Cited Researchers spreadsheet.

### Helper: produces verifiable World Bank country lists ###

import pandas as pd
from typing import Literal

def extract_country_history(excel_path: str, income_group: Literal['L','LM','UM','H'] = 'H') -> list:
    """
    Reads the 'Country Analytical History' sheet from the given Excel file,
    and returns a list of values from column B for rows where column AM contains 'H'.
    """
    # Read the specific sheet
    df = pd.read_excel(excel_path, sheet_name="Country Analytical History", engine="openpyxl")

    # Filter rows where column AM contains 'H' (column AM is the 39th, zero-based index 38)
    filtered = df[df.iloc[:, 38] == 'H']  # column AM is 39th (index 38)

    # Extract values from column B (2nd column, index 1)
    values = filtered.iloc[:, 1].tolist()
    return values

HIGH_INCOME_COUNTRIES_FY2025 = extract_country_history('/path/to/OGHIST_2025_07_01.xlsx', income_group='H')
print(f'# Count: {len(HIGH_INCOME_COUNTRIES_FY2025)}',
      f'HIGH_INCOME_COUNTRIES_FY2025 = {HIGH_INCOME_COUNTRIES_FY2025}',
      sep='\n')

### Main sampler code ###

import os
import pandas as pd
import numpy as np
import warnings

HCR_LIST_LABEL = 'hcr.filename'
DRAW_LABEL = 'ktp.draw_number'
HCR_ROW_LABEL = 'hcr.row_number'
PRIORITY_LABEL = 'ktp.priority'
MATCHING_COLS = ["hcr.first_name", "hcr.last_name", "hcr.category"]

COUNTRY_PREFIX = ', '
ENGLISH_HICS = ['United States','USA','U.S.A.','US','U.S.','United Kingdom','UK','U.K.','Australia','Canada','New Zealand']
GREATER_CHINA = ['China','Hong Kong','Macau','Taiwan']
EU_COUNTRIES = [  # copied and pasted from <https://european-union.europa.eu/principles-countries-history/eu-countries_en?page=1#header_countries_list> on 2025-08-19 UTC-4 (27 countries)
    'Austria',
    'Belgium',
    'Bulgaria',
    'Croatia',
    'Cyprus',
    'Czechia',
    'Denmark',
    'Estonia',
    'Finland',
    'France',
    'Germany',
    'Greece',
    'Hungary',
    'Ireland',
    'Italy',
    'Latvia',
    'Lithuania',
    'Luxembourg',
    'Malta',
    'Netherlands',
    'Poland',
    'Portugal',
    'Romania',
    'Slovakia',
    'Slovenia',
    'Spain',
    'Sweden'
]
# High-income group for FY2025, extracted from World Bank Country and Lending Groups historical classification by income in XLSX format, filename 'OGHIST_2025_07_01.xlsx', downloaded from <https://datahelpdesk.worldbank.org/knowledgebase/articles/906519-world-bank-country-and-lending-groups> on 2025-08-19 UTC-4 (86 countries)
HIGH_INCOME_COUNTRIES_FY2025 = ['American Samoa', 'Andorra', 'Antigua and Barbuda', 'Aruba', 'Australia', 'Austria', 'Bahamas, The', 'Bahrain', 'Barbados', 'Belgium', 'Bermuda', 'British Virgin Islands', 'Brunei Darussalam', 'Bulgaria', 'Canada', 'Cayman Islands', 'Channel Islands', 'Chile', 'Croatia', 'Curaçao', 'Cyprus', 'Czechia', 'Denmark', 'Estonia', 'Faeroe Islands', 'Finland', 'France', 'French Polynesia', 'Germany', 'Gibraltar', 'Greece', 'Greenland', 'Guam', 'Guyana', 'Hong Kong SAR, China', 'Hungary', 'Iceland', 'Ireland', 'Isle of Man', 'Israel', 'Italy', 'Japan', 'Korea, Rep.', 'Kuwait', 'Latvia', 'Liechtenstein', 'Lithuania', 'Luxembourg', 'Macao SAR, China', 'Malta', 'Monaco', 'Nauru', 'Netherlands', 'New Caledonia', 'New Zealand', 'Northern Mariana Islands', 'Norway', 'Oman', 'Palau', 'Panama', 'Poland', 'Portugal', 'Puerto Rico (U.S.)', 'Qatar', 'Romania', 'Russian Federation', 'San Marino', 'Saudi Arabia', 'Seychelles', 'Singapore', 'Sint Maarten (Dutch part)', 'Slovak Republic', 'Slovenia', 'Spain', 'St. Kitts and Nevis', 'St. Martin (French part)', 'Sweden', 'Switzerland', 'Taiwan, China', 'Trinidad and Tobago', 'Turks and Caicos Islands', 'United Arab Emirates', 'United Kingdom', 'United States', 'Uruguay', 'Virgin Islands (U.S.)']
NON_ENGLISH_NON_EU_HICS_NO_CHINA = [  # may include overseas territories and such
    hic for hic in HIGH_INCOME_COUNTRIES_FY2025
    if not any(c in hic for c in ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA)
]  # 50 countries: ['American Samoa', 'Andorra', 'Antigua and Barbuda', 'Aruba', 'Bahamas, The', 'Bahrain', 'Barbados', 'Bermuda', 'British Virgin Islands', 'Brunei Darussalam', 'Cayman Islands', 'Channel Islands', 'Chile', 'Curaçao', 'Faeroe Islands', 'French Polynesia', 'Gibraltar', 'Greenland', 'Guam', 'Guyana', 'Iceland', 'Isle of Man', 'Israel', 'Japan', 'Korea, Rep.', 'Kuwait', 'Liechtenstein', 'Monaco', 'Nauru', 'New Caledonia', 'Northern Mariana Islands', 'Norway', 'Oman', 'Palau', 'Panama', 'Qatar', 'Russian Federation', 'San Marino', 'Saudi Arabia', 'Seychelles', 'Singapore', 'Sint Maarten (Dutch part)', 'Slovak Republic', 'St. Kitts and Nevis', 'St. Martin (French part)', 'Switzerland', 'Trinidad and Tobago', 'Turks and Caicos Islands', 'United Arab Emirates', 'Uruguay']

def concat_dfs_from_file_list(excel_file_paths: list[str]) -> pd.DataFrame:
    def hcr_header_unify(cat: str) -> str:
        return 'hcr.' + cat.replace(' ','_').replace(':','')
    # Load all excel files
    dfs = {}
    for file in excel_file_paths:
        if file.endswith(".xlsx") and not file.startswith("~$"):
            path = file
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    df = pd.read_excel(path)
                    df.columns = [hcr_header_unify(str(col).lower()) for col in df.columns]
                dfs[path] = df
            except Exception as e:
                print(f"Error reading {file}: {e}")

    if not dfs:
        raise FileNotFoundError("No Excel files found.")

    full_df = pd.concat(
        [df.assign(**{HCR_LIST_LABEL: os.path.basename(path)}) for path, df in dfs.items()],
        ignore_index=False
    )
    print(f"Total rows across {len(full_df[HCR_LIST_LABEL].unique())} Excel files: {len(full_df)}")
    # Reset index to make it a column while keeping original index
    full_df = full_df.reset_index().rename(columns={"index": HCR_ROW_LABEL})
    # Have it match Excel row numbering (+ header, + start from)
    full_df[HCR_ROW_LABEL] = full_df[HCR_ROW_LABEL] + 2

    return full_df

def concat_and_select_fixed_names_from_2024(excel_file_path, folder_path, output_csv_path, name_category_triples: list[tuple[str, str, str]], affiliation_sort: bool | None=None):
    if not (str(excel_file_path).endswith('.xlsx') and '2024' in str(excel_file_path)):
        raise RuntimeError("Only 2024 xlsx is supported")
    print('HCR list sampling\n-----------------')
    try:
        folder_file_paths = [
            os.path.join(folder_path, f)
            for f in sorted(os.listdir(folder_path))
            if f.endswith(".xlsx") and not f.startswith("~$")
        ]
        folder_full_df = concat_dfs_from_file_list(folder_file_paths)
        # Keep only column names, drop all rows
        folder_full_df = folder_full_df.iloc[0:0]
        print(f"Read col names from {folder_path!r}:\n{folder_full_df.columns}")
    except Exception as e:
        print(e)
    try:
        full_df = concat_dfs_from_file_list([excel_file_path])
        # Ensure full_df has all columns from folder_full_df
        full_df = full_df.reindex(columns=folder_full_df.columns)
        print(f"Read df from {excel_file_path!r}\n"
              "Reindexed to match col names schema above")
    except Exception as e:
        print(e)

    if os.path.exists(output_csv_path):
        try:
            overwrite = True if input("Previous CSV found. Overwrite? y/N").lower() == "y" else False
            if not overwrite:
                raise RuntimeError("Overwrite prompt not accepted")
        except Exception as e:
            print(f"Failed to handle previous CSV: {e}")
            raise

    print(f"Selecting matching name-category triples:\n{"\n".join([str(t) for t in name_category_triples])}")
    sampled_df = (
        full_df[
            full_df[MATCHING_COLS]
            .apply(tuple, axis=1)
            .isin(name_category_triples)
        ]
        .assign(
            __order=lambda x: x[MATCHING_COLS]
            .apply(tuple, axis=1)
            .map({pair: i for i, pair in enumerate(name_category_triples)})
        )
        .sort_values("__order")
        .drop(columns="__order")
        .copy()
    )

    # Assign draw numbers for logging (respecting order from interim pilot results from 2025-07-24 docx)
    sampled_df[DRAW_LABEL] = "pilot." + (sampled_df.reset_index(drop=True).index + 1).astype(str)


    # Apply any per-row logic (like printing)
    sampled_df.apply(
        lambda r: print(f"\nDraw #{r[DRAW_LABEL]}, First Name {r["hcr.first_name"]!r}, Last Name {r["hcr.last_name"]!r}: File '{r[HCR_LIST_LABEL]}', Row {r[HCR_ROW_LABEL]}:\n{r}"),
        axis=1
    )

    if affiliation_sort is not None:
        # Find all columns containing 'affiliation' (case-insensitive)
        aff_cols = [c for c in sampled_df.columns if 'affiliation' in c.lower()]
        def affiliation_priority(row):
            values = ' '.join(str(row[c]) for c in aff_cols if pd.notna(row[c]))
            # Priority 1: none of the target countries
            if not any(COUNTRY_PREFIX + country in values for country in ENGLISH_HICS + EU_COUNTRIES + GREATER_CHINA + NON_ENGLISH_NON_EU_HICS_NO_CHINA):
                return 1
            # Priority 2: Greater China
            elif any(COUNTRY_PREFIX + country in values for country in GREATER_CHINA):
                return 2
            # Priority 3: non-EU, non-English speaking HICs
            elif any(COUNTRY_PREFIX + country in values for country in NON_ENGLISH_NON_EU_HICS_NO_CHINA):
                return 3
            # Priority 4: EU
            elif any(COUNTRY_PREFIX + country in values for country in EU_COUNTRIES):
                return 4
            # Priority 5: everything else
            else:
                return 5
        sampled_df[PRIORITY_LABEL] = sampled_df.apply(affiliation_priority, axis=1)
        if affiliation_sort:
            sampled_df = sampled_df.sort_values([PRIORITY_LABEL, DRAW_LABEL])

    # Reorder columns: metadata first
    first_cols = [DRAW_LABEL, HCR_LIST_LABEL, HCR_ROW_LABEL, PRIORITY_LABEL]
    cols = first_cols + [c for c in sampled_df.columns if c not in first_cols]
    sampled_df = sampled_df[cols]

    # Save to CSV
    sampled_df.to_csv(output_csv_path, index=False, header=True)

    print(f"Matching rows saved to {output_csv_path}")

# manually copied and pasted on 2025-12-23 from interim pilot results from 2025-07-24 docx
name_category_triples = [
    ("Bin","Gao","Cross-Field"),                    # 1
    ("Beatriz Roldan","Cuenya","Chemistry"),        # 2
    ("Lizhi","Zhang","Chemistry"),                  # 3
    ("Rudolf A.","de Boer","Clinical Medicine"),    # 4
    ("Hidenori","Arai","Cross-Field"),              # 5
    ("Mark A.","Bradford","Cross-Field"),           # 6
    ("Salim","Yusuf","Clinical Medicine"),          # 7
    ("Nicholas C.","Turner","Clinical Medicine"),   # 8
    ("Osman M.","Bakr","Chemistry"),                # 9
    ("Rainer","Blatt","Physics"),                   # 10
]

concat_and_select_fixed_names_from_2024("/path/to/2024-Historical-Highly-Cited-Researchers-lists - final/2024_HCR.xlsx", f"pilot_sample_2025-07-24.csv", name_category_triples=name_category_triples, affiliation_sort=False)
# It is interesting that if we do not take category into filtering, the table contains two more rows, for a total of 12 (non-header) rows.
# The additional rows have been confirmed to be:
# 2024_HCR.xlsx,4713,Lizhi,Zhang,Environment and Ecology,"Central China Normal University, China Mainland",
# 2024_HCR.xlsx,5091,Osman M.,Bakr,Materials Science,"King Abdullah University of Science & Technology, Saudi Arabia",
# This is because these researchers were featured twice on the 2024 HCR list.
# These two additional rows were not used in the pilot.
# While these two rows highlight the nuance of deduplication in this dataset, to ensure full alignment with the pilot sample actually used and to be able to assign ktp draw numbers (with a special `pilot.` prefix) to ensure full shape equality, these two rows are not present in `pilot_sample_2025-07-24.csv`.
