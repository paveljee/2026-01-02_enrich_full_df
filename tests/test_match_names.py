from pathlib import Path

import pandas as pd
import pytest
from docx import Document

from src._vars import (
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    RIGHT_NAME_COL,
)
from src.io_utils import find_files_by_extension
from src.name_utils import match_csv_docx_names, unify_first_last
from src.parse_docx import parse_docx_table

TEST_CSV_DIR = Path("data/samples")
TEST_DOCX_DIR = Path("data/manual_extractions")


def create_test_docx_with_table(path: Path, names: list[str]):
    """Helper to create a DOCX file with a table matching the image structure."""
    doc = Document()

    # Add italic caption
    caption = doc.add_paragraph()
    caption_run = caption.add_run(
        "Table 1: PROGRESS-Plus factors for sample (n_52) of authors on "
        "Clarivate's Highly Cited Researchers List."
    )
    caption_run.italic = True

    # Create table: 9 columns matching the image
    table = doc.add_table(rows=1, cols=9)
    table.style = "Table Grid"

    # Header row - first column must be "Researcher/author"
    hdr = table.rows[0].cells
    hdr[0].text = "Researcher/author"
    hdr[1].text = "Place of\nresidence"
    hdr[2].text = "Gender"
    hdr[3].text = "Country of\nfirst degree"
    hdr[4].text = "Country of\nPhD"
    hdr[5].text = "Academic\nage"
    hdr[6].text = "Mentor"
    hdr[7].text = "Undergrad\ninstitution"
    hdr[8].text = "Undergrad\ninstitution\nCountry"

    for name in names:
        row_cells = table.add_row().cells
        row_cells[0].text = name
        row_cells[1].text = "Sample data"
        row_cells[2].text = "Sample data"
        row_cells[3].text = "Sample data"
        row_cells[4].text = "Sample data"
        row_cells[5].text = "Sample data"
        row_cells[6].text = "Sample data"
        row_cells[7].text = "Sample data"
        row_cells[8].text = "Sample data"

    doc.save(path)


def test_create_test_docx_with_table(tmp_path):
    names = ["John Doe", "Jane Smith"]
    docx_path = tmp_path / "test.docx"
    create_test_docx_with_table(docx_path, names)

    # Parse and verify
    dfs = parse_docx_table(docx_path)
    assert len(dfs) == 1
    df = dfs[0]
    assert RIGHT_NAME_COL in df.columns
    assert len(df) == 2


def test_match_csv_docx_names_with_synthetic_data():
    csv_df = pd.DataFrame({
        KTP_FIRST_NAME_COL: ["Ada", "Alan", "Jane"],
        KTP_LAST_NAME_COL: ["Lovelace", "Turing", "Doe"],
    })
    docx_series = pd.Series([
        "Dr. Ada Lovelace",
        "Prof. Alan M. Turing",
        "Jane Doe",
    ])

    matches = match_csv_docx_names(csv_df, docx_series)

    assert matches[0] == 0
    assert matches[1] == 1
    assert matches[2] == 2


def test_match_csv_docx_names_on_full_dataset():
    if not TEST_CSV_DIR.exists() or not TEST_DOCX_DIR.exists():
        pytest.skip("Test data directory not found")

    csv_files = find_files_by_extension(TEST_CSV_DIR, "csv", recursive=False)
    docx_files = find_files_by_extension(TEST_DOCX_DIR, "docx", recursive=False)

    if not csv_files or not docx_files:
        pytest.skip("No CSV or DOCX files found in test directories")

    csv_df = pd.concat([pd.read_csv(path) for path in csv_files], ignore_index=True)
    docx_df = pd.concat(
        [parse_docx_table(path)[0] for path in docx_files], ignore_index=True
    )

    unified_names = csv_df.apply(unify_first_last, axis=1, result_type="expand")
    csv_names = pd.DataFrame(
        {
            KTP_FIRST_NAME_COL: unified_names[0].apply(lambda x: x[KTP_FIRST_NAME_COL]),
            KTP_LAST_NAME_COL: unified_names[1].apply(lambda x: x[KTP_LAST_NAME_COL]),
        }
    )

    matches = match_csv_docx_names(csv_names, docx_df[RIGHT_NAME_COL])
    assert len(matches) == len(csv_names)
