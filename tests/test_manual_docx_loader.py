from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from zipfile import ZipFile

import pandas as pd
import pytest

from src.helpers.data_models import FragmentType, ResourceGroup
from src.helpers.docx_parse import parse_docx_tables_and_notes
from src.helpers.resources import register_resource
from src.helpers.vars import (
    DOCX_FRAGMENT_COL,
    DOCX_ROW_INDEX_COL,
    DOCX_TABLE_INDEX_COL,
    KTP_DOCX_COMMENTS_COL,
    KTP_DOCX_FOOTNOTES_COL,
    KTP_FILENAME_COL,
)
from src.steps.step_08_match_docx import load_docx_tables, normalize_docx_column_name


def test_normalize_docx_column_name_rules() -> None:
    assert normalize_docx_column_name("hcr.name") == "hcr.name"
    assert normalize_docx_column_name("Name (full)") == "ktp.table_1_name_full_"
    assert normalize_docx_column_name("  Mixed  Case ") == "ktp.table_1_mixed_case_"


def test_load_docx_tables_adds_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    docx_path = tmp_path / "sample.docx"
    docx_path.write_text("stub", encoding="utf-8")

    table = pd.DataFrame({"Researcher/author": ["Ada", "Grace"], "Notes": ["A", "B"]})

    def fake_parse_docx_tables_and_notes(
        _: Path,
    ) -> tuple[list[pd.DataFrame], str, list[list[str]]]:
        return [table], "outside note", [["comment row 1", "comment row 2"]]

    monkeypatch.setattr(
        "src.steps.step_08_match_docx.parse_docx_tables_and_notes",
        fake_parse_docx_tables_and_notes,
    )

    resources = {
        docx_path.name: register_resource(
            docx_path,
            group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.DOCX_ROW,
        )
    }

    df = load_docx_tables(resources)

    assert len(df) == 2
    assert df[KTP_FILENAME_COL].unique().tolist() == [docx_path.name]
    assert df[DOCX_TABLE_INDEX_COL].tolist() == [0, 0]
    assert df[DOCX_ROW_INDEX_COL].tolist() == [0, 1]
    assert df[DOCX_FRAGMENT_COL].tolist() == ["table0_row0", "table0_row1"]
    assert df[KTP_DOCX_FOOTNOTES_COL].tolist() == ["outside note", "outside note"]
    assert df[KTP_DOCX_COMMENTS_COL].tolist() == ["comment row 1", "comment row 2"]


def test_parse_docx_tables_and_notes_extracts_lists_and_notes(tmp_path: Path) -> None:
    docx_path = tmp_path / "lists_notes.docx"
    document_xml = dedent(
        """\
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Outside paragraph note</w:t></w:r></w:p>
            <w:tbl>
              <w:tr>
                <w:tc>
                  <w:p>
                    <w:commentRangeStart w:id="0"/>
                    <w:r><w:t>Researcher/author</w:t></w:r>
                    <w:commentRangeEnd w:id="0"/>
                    <w:r><w:commentReference w:id="0"/></w:r>
                  </w:p>
                </w:tc>
                <w:tc><w:p><w:r><w:t>Notes</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Jane Doe</w:t></w:r></w:p></w:tc>
                <w:tc>
                  <w:p>
                    <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
                    <w:r><w:t>First numbered item</w:t></w:r>
                  </w:p>
                  <w:p>
                    <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>
                    <w:r><w:t>Second numbered item</w:t></w:r>
                  </w:p>
                  <w:p>
                    <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>
                    <w:commentRangeStart w:id="1"/>
                    <w:r><w:t>Bullet item</w:t></w:r>
                    <w:commentRangeEnd w:id="1"/>
                    <w:r><w:commentReference w:id="1"/></w:r>
                  </w:p>
                </w:tc>
              </w:tr>
            </w:tbl>
            <w:p><w:r><w:t>Footnote-like text below table</w:t></w:r></w:p>
            <w:sectPr/>
          </w:body>
        </w:document>
        """
    )
    numbering_xml = dedent(
        """\
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="0">
            <w:lvl w:ilvl="0">
              <w:start w:val="1"/>
              <w:numFmt w:val="decimal"/>
              <w:lvlText w:val="%1."/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
          <w:abstractNum w:abstractNumId="1">
            <w:lvl w:ilvl="0">
              <w:start w:val="1"/>
              <w:numFmt w:val="bullet"/>
              <w:lvlText w:val="•"/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
        </w:numbering>
        """
    )
    comments_xml = dedent(
        """\
        <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                    xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml">
          <w:comment w:id="1" w:author="Second Reviewer" w:initials="SR"
                     w:date="2024-01-03T03:04:05Z">
            <w:p><w:r><w:t>Second root comment</w:t></w:r></w:p>
          </w:comment>
          <w:comment w:id="0" w:author="First Last" w:initials="FL"
                     w:date="2024-01-02T03:04:05Z">
            <w:p><w:r><w:t>Reviewer comment text</w:t></w:r></w:p>
          </w:comment>
          <w:comment w:id="2" w:author="Reply Author" w:initials="RA"
                     w:date="2024-01-02T04:04:05Z" w15:parentId="0">
            <w:p><w:r><w:t>Reply text</w:t></w:r></w:p>
          </w:comment>
        </w:comments>
        """
    )
    with ZipFile(docx_path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/numbering.xml", numbering_xml)
        zf.writestr("word/comments.xml", comments_xml)

    tables, footnotes, comments_by_row = parse_docx_tables_and_notes(docx_path)
    assert len(tables) == 1
    assert len(tables[0]) == 1
    notes_val = tables[0].iloc[0, 1]
    assert "1. First numbered item" in notes_val
    assert "2. Second numbered item" in notes_val
    assert "• Bullet item" in notes_val
    assert "Outside paragraph note" not in footnotes
    assert "Footnote-like text below table" in footnotes
    row_comments = comments_by_row[0][0]
    lines = row_comments.splitlines()
    assert lines[0].startswith('- **First Last** commented on "Researcher/author":')
    assert "(2024-01-02T03:04:05Z)" in lines[0]
    assert lines[1].startswith('  - **Reply Author** commented on "anchor unavailable": Reply text')
    assert lines[2].startswith('- **Second Reviewer** commented on "Bullet item":')

    review_dir = Path("data/test_data/parse_docx")
    review_dir.mkdir(parents=True, exist_ok=True)
    review_input = review_dir / "input.docx"
    review_input.write_bytes(docx_path.read_bytes())

    notes_val_md = str(notes_val).replace("\n", "\n\n")
    footnotes_md = footnotes.replace("\n", "\n\n") if footnotes else ""
    comments_md = row_comments.replace("\n", "\n\n") if row_comments else ""
    output_md = "\n\n".join(
        [
            "# parse_docx test output",
            "## Table Cell (Notes)",
            notes_val_md,
            "## Footnotes",
            footnotes_md,
            "## Comments",
            comments_md,
        ]
    )
    (review_dir / "output.md").write_text(output_md, encoding="utf-8")


def test_parse_docx_tables_and_notes_real_mock_fixture_for_review() -> None:
    mock_docx = Path("resources/mock_RI_test.docx")
    if not mock_docx.exists():
        pytest.skip("resources/mock_RI_test.docx not available.")

    tables, footnotes, comments_by_row = parse_docx_tables_and_notes(mock_docx)
    assert len(tables) >= 1
    assert len(tables[0]) >= 1
    comments = "\n".join(comments_by_row[0]) if comments_by_row and comments_by_row[0] else ""
    assert "Some comment" in comments

    review_dir = Path("data/test_data/parse_docx")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "input.docx").write_bytes(mock_docx.read_bytes())

    notes_val = tables[0].iloc[0, 0]
    notes_val_md = str(notes_val).replace("\n", "\n\n")
    footnotes_md = footnotes.replace("\n", "\n\n") if footnotes else ""
    comments_md = comments.replace("\n", "\n\n") if comments else ""
    output_md = "\n\n".join(
        [
            "# parse_docx mock fixture output",
            "## First Cell",
            notes_val_md,
            "## Footnotes",
            footnotes_md,
            "## Comments",
            comments_md,
        ]
    )
    (review_dir / "output.md").write_text(output_md, encoding="utf-8")
