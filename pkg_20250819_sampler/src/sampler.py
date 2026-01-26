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

def concat_and_sample_fixed_seed(folder_path, output_csv_path, seed=42, n=1, affiliation_sort=False):
    print('HCR list sampling\n-----------------')
    def hcr_header_unify(cat: str) -> str:
        return 'hcr.' + cat.replace(' ','_').replace(':','')
    # Load all excel files
    dfs = {}
    for file in sorted(os.listdir(folder_path)):
        if file.endswith(".xlsx") and not file.startswith("~$"):
            path = os.path.join(folder_path, file)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    df = pd.read_excel(path)
                    df.columns = [hcr_header_unify(str(col).lower()) for col in df.columns]
                dfs[path] = df
            except Exception as e:
                print(f"Error reading {file}: {e}")

    if not dfs:
        print("No Excel files found.")
        return

    full_df = pd.concat(
        [df.assign(**{HCR_LIST_LABEL: os.path.basename(path)}) for path, df in dfs.items()],
        ignore_index=False
    )
    print(f"Total rows across {len(full_df[HCR_LIST_LABEL].unique())} Excel files: {len(full_df)}")
    # Reset index to make it a column while keeping original index
    full_df = full_df.reset_index().rename(columns={"index": HCR_ROW_LABEL})
    # Have it match Excel row numbering (+ header, + start from)
    full_df[HCR_ROW_LABEL] = full_df[HCR_ROW_LABEL] + 2

    # Initialize generator with fixed seed
    rng = np.random.default_rng(seed)

    # Figure out how many draws have already been made
    last_draw = -1
    if os.path.exists(output_csv_path):
        try:
            prev = pd.read_csv(output_csv_path)
            if DRAW_LABEL in prev.columns and not prev.empty:
                # When reading previous CSV, decrement to match RNG state
                last_draw = prev[DRAW_LABEL].max() - 1
        except Exception as e:
            print(f"Could not read previous CSV: {e}")

    # Advance generator to correct state
    draw_number = last_draw + 1
    _ = rng.integers(0, len(full_df), size=draw_number)  # burn numbers

    # ===== Draw n rows at once =====
    print(f"Sampling {n} random row(s) (seed={seed})...")
    rand_idxs = rng.integers(0, len(full_df), size=n)
    sampled_df = full_df.iloc[rand_idxs].copy()

    # Assign draw numbers for logging (starting from last_draw + 2 so first draw logs as 1)
    sampled_df[DRAW_LABEL] = np.arange(draw_number + 1, draw_number + 1 + n)

    # Apply any per-row logic (like printing)
    sampled_df.apply(
        lambda r: print(f"\nDraw #{r[DRAW_LABEL]}: File '{r[HCR_LIST_LABEL]}', Row {r[HCR_ROW_LABEL]}:\n{r}"),
        axis=1
    )

    if affiliation_sort:
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
        sampled_df = sampled_df.sort_values([PRIORITY_LABEL, DRAW_LABEL])

    # Reorder columns: metadata first
    first_cols = [DRAW_LABEL, HCR_LIST_LABEL, HCR_ROW_LABEL, PRIORITY_LABEL]
    cols = first_cols + [c for c in sampled_df.columns if c not in first_cols]
    sampled_df = sampled_df[cols]

    # Save to CSV
    if os.path.exists(output_csv_path) and os.path.getsize(output_csv_path) > 0:
        sampled_df.to_csv(output_csv_path, mode="a", index=False, header=False)
    else:
        sampled_df.to_csv(output_csv_path, index=False, header=True)

    print(f"{n} samples saved to {output_csv_path}")

from datetime import datetime, timedelta, timezone
concat_and_sample_fixed_seed("/path/to/2024-Historical-Highly-Cited-Researchers-lists - final", f"random_samples_{datetime.now(timezone(timedelta(hours=-4))).strftime("%Y-%m-%d")}.csv", seed=42, n=40, affiliation_sort=True)
# NOTE: Manually replace the generated file with ALL the previous sample(s) to adjust the starting draw number, and then regenerate. Then remove the previous lines.
# TODO: Implement this fully in code.
