from pathlib import Path

import pandas as pd
import pytest

from src._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from src.name_utils import unify_first_last
from src.utils.files import find_files_by_extension
from tests.real_data_utils import SAMPLES_DIR, list_sample_csv_files

TEST_CSV_DIR = Path("data/samples")

@pytest.fixture
def hcr_row():
    return pd.Series({
        "hcr.row_number": 2476,
        "hcr.firstname_middlename": None,
        "hcr.lastname": None,
        "hcr.category": "Cross-Field",
        "hcr.full_primary_affiliation": None,
        "hcr.full_secondary_affiliation": None,
        "hcr.researcher_id": None,
        "hcr.unnamed_6": None,
        "hcr.unnamed_7": None,
        "hcr.unnamed_8": None,
        "hcr.unnamed_9": None,
        "hcr.filename": "2019_HCR.xlsx",
        "hcr.familyname": None,
        "hcr.orcid": None,
        "hcr.institutional_profile": None,
        "hcr.twitter": None,
        "hcr.linkedin": None,
        "hcr.first_name": "Lane W.",
        "hcr.last_name": "Martin",
        "hcr.primary_affiliation": "University of California Berkeley, United States",
        "hcr.secondary_affiliation": None,
        "hcr.secondary_affiliations": "Lawrence Berkeley National Laboratory, United States",
        "hcr.firstname": None,
        "hcr.primaryaffiliation": None,
        "hcr.secondaryaffiliation": None,
        "ktp.draw_number": None,
    })

def test_unify_first_last_with_hcr_fixture(hcr_row):
    first, last = unify_first_last(hcr_row)
    assert "Lane" in first[KTP_FIRST_NAME_COL]
    assert last[KTP_LAST_NAME_COL] == "Martin"

def test_unify_first_last_on_full_dataset(tmp_path, csv_dir=TEST_CSV_DIR):
    """Test that unify_first_last runs without exceptions on a full dataset.
    
    This test doesn't validate correctness but ensures the function handles
    all real-world data without crashing.
    """
    
    # This test assumes you have actual CSV files in your test fixtures
    # Adjust the path to wherever your test data lives
    
    if SAMPLES_DIR.exists():
        csv_files = list_sample_csv_files()
    else:
        if not csv_dir.exists():
            pytest.skip(f"Test data directory not found: {csv_dir}")
        csv_files = find_files_by_extension(csv_dir, "csv", recursive=False)
    
    if not csv_files:
        pytest.skip("No CSV files found in test directory")
    
    # Load and combine CSV files (mimicking CLI logic)
    csv_df = pd.concat([pd.read_csv(csv_path) for csv_path in csv_files], ignore_index=True)
    
    # Track any failures
    failures = []
    
    # Run unify_first_last on each row
    for idx, row in csv_df.iterrows():
        try:
            first, last = unify_first_last(row)
            # Basic sanity checks
            assert KTP_FIRST_NAME_COL in first
            assert KTP_LAST_NAME_COL in last
        except Exception as e:
            failures.append((idx, row.get("hcr.first_name"), row.get("hcr.last_name"), str(e)))
    
    # If there were failures, report them
    if failures:
        failure_msg = "\n".join([
            f"Row {idx}: {first_name} {last_name} - {error}"
            for idx, first_name, last_name, error in failures[:10]  # Show first 10
        ])
        pytest.fail(f"unify_first_last failed on {len(failures)} rows.\n"
                    f"Showing first 10 for example:\n{failure_msg}")
