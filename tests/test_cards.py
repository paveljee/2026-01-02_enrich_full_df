from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.helpers.cards import build_cards, write_cards_zip
from src.helpers.data_models import InnerDict, NameKey, OuterDict
from src.helpers.vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_ORIG_COLNAME_COL,
    KTP_LAST_NAME_ORIG_COLNAME_COL,
)


class DummyProcedure:
    dataset_id_field = "ktp.source_key"


def test_build_cards_includes_intro_and_fun_fact() -> None:
    name_key = NameKey(first_name="Ada", last_name="Lovelace")
    outer = OuterDict.from_name_keys([name_key])

    data = {
        DRAW_LABEL: 1,
        KTP_FILENAME_COL: "2019_HCR.xlsx",
        KTP_FIRST_NAME_ORIG_COLNAME_COL: "First Name",
        KTP_LAST_NAME_ORIG_COLNAME_COL: "Last Name",
        "note": "hello",
        "excluded": "skip",
    }
    outer.add_inner(name_key, InnerDict.from_mapping(data, DummyProcedure()))

    cards = build_cards(
        outer,
        total_draws=10,
        intro_date="2026-02-02",
        excluded_cols={"excluded"},
    )

    assert "1_Ada_Lovelace" in cards
    card = cards["1_Ada_Lovelace"]
    assert "## Introduction" in card
    assert "Fun fact" in card
    assert "excluded" not in card
    assert "Draw #1 of 10" in card


def test_write_cards_zip_txt(tmp_path: Path) -> None:
    cards = {"Ada_Lovelace": "card content", "Grace_Hopper": "more"}
    zip_path = write_cards_zip(
        cards,
        tmp_path,
        "cards.zip",
        output_format="txt",
        reference_docx=tmp_path / "ref.docx",
    )

    assert zip_path.exists()
    with ZipFile(zip_path, "r") as zipf:
        assert sorted(zipf.namelist()) == ["Ada_Lovelace.txt", "Grace_Hopper.txt"]


def test_write_cards_zip_docx_skips_without_pandoc(tmp_path: Path) -> None:
    if shutil.which("pandoc") is None:
        pytest.skip("pandoc not available")

    cards = {"Ada_Lovelace": "card content"}
    ref_docx = Path("resources/pandoc-custom-reference.docx")
    if not ref_docx.exists():
        pytest.skip("reference docx not available")

    zip_path = write_cards_zip(
        cards,
        tmp_path,
        "cards_docx.zip",
        output_format="docx",
        reference_docx=ref_docx,
    )

    assert zip_path.exists()
    with ZipFile(zip_path, "r") as zipf:
        assert zipf.namelist() == ["Ada_Lovelace.docx"]
