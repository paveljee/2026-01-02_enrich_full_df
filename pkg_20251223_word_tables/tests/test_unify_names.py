import pandas as pd
import pytest

from .. import (
    unify_first_last,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
)

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
