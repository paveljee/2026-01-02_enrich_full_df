from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src import _vars
from src._vars import (
    DRAW_LABEL,
    HCR_FILENAME_COL,
    HCR_ROW_COL,
    KTP_ECONOMIES_COL,
    KTP_FILENAME_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
)
from src.data_models import FragmentType, NameKey, OuterDict, ResourceGroup
from src.hcr_xlsx.indexer import index_samples
from src.hcr_xlsx.loader import build_population_table
from src.hcr_xlsx.matcher import match_population
from src.hcr_xlsx.preprocessor import load_high_income_economies, preprocess_samples
from src.hcr_xlsx.sampler import sample_pilot, sample_population
from src.utils.name_keys import NAME_KEY_COL
from src.utils.resources import register_resource


def _write_xlsx(path: Path, df: pd.DataFrame) -> None:
    df.to_excel(path, index=False, engine="openpyxl")


def test_build_population_table_normalizes_headers_and_indices(tmp_path: Path) -> None:
    df1 = pd.DataFrame({"First Name": ["Ada"], "Last Name": ["Lovelace"]})
    df2 = pd.DataFrame({"First Name": ["Grace"], "Last Name": ["Hopper"]})
    path1 = tmp_path / "2019_HCR.xlsx"
    path2 = tmp_path / "2020_HCR.xlsx"
    temp_lock = tmp_path / "~$2019_HCR.xlsx"
    _write_xlsx(path1, df1)
    _write_xlsx(path2, df2)
    temp_lock.write_text("skip", encoding="utf-8")

    resources = {
        path1.name: register_resource(
            path1,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        ),
        path2.name: register_resource(
            path2,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        ),
        temp_lock.name: register_resource(
            temp_lock,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        ),
    }

    conn = duckdb.connect()
    try:
        build_population_table(conn, resources, table_name="population")
        population = conn.execute("SELECT * FROM population").df()
    finally:
        conn.close()

    assert len(population) == 2
    assert "hcr.first_name" in population.columns
    assert "hcr.last_name" in population.columns
    assert population[HCR_ROW_COL].tolist() == [2, 2]
    assert population[HCR_FILENAME_COL].tolist() == [path1.name, path2.name]
    assert population[KTP_POPULATION_INDEX_COL].tolist() == [0, 1]


def test_load_high_income_economies(tmp_path: Path) -> None:
    columns = [f"col{i}" for i in range(39)]
    df = pd.DataFrame([["x"] * 39, ["y"] * 39], columns=columns)
    df.iloc[0, 1] = "Economy A"
    df.iloc[1, 1] = "Economy B"
    df.iloc[0, 38] = "H"
    df.iloc[1, 38] = "L"

    path = tmp_path / "economies.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Country Analytical History", index=False)

    resource = register_resource(
        path,
        group=ResourceGroup.REGISTERED_SAMPLES,
        fragment_type=FragmentType.EXCEL_ROW,
    )
    economies = load_high_income_economies(resource)
    assert economies == ["Economy A"]


def test_preprocess_samples_priority_and_economies() -> None:
    df = pd.DataFrame(
        {
            "affiliation": [
                "No country",
                ", China",
                ", Mexico",
                ", France",
                ", United States",
            ],
            KTP_FILENAME_COL: ["file.xlsx"] * 5,
        }
    )

    economies = ["United States", "China", "France", "Mexico"]
    processed = preprocess_samples(df, economies=economies)

    assert processed[KTP_ECONOMIES_COL].tolist() == [
        "No country",
        "China",
        "Mexico",
        "France",
        "United States",
    ]
    assert processed[KTP_PRIORITY_COL].tolist() == [1, 2, 3, 4, 5]
    assert processed[KTP_PRIORITY_GROUP_COL].tolist() == [
        "non_target",
        "greater_china",
        "non_english_non_eu_hic",
        "eu",
        "other",
    ]


def test_sample_population_deterministic_draws() -> None:
    population = pd.DataFrame(
        {
            KTP_POPULATION_INDEX_COL: list(range(10)),
            HCR_FILENAME_COL: ["2019_HCR.xlsx"] * 10,
        }
    )
    conn = duckdb.connect()
    try:
        conn.register("population", population)
        conn.execute("CREATE OR REPLACE TABLE population AS SELECT * FROM population")
        sample_population(
            conn,
            population_table="population",
            samples_table="samples",
            draw_sizes=[3, 2],
            seed=123,
            economies=[],
        )
        samples = conn.execute("SELECT * FROM samples").df()
    finally:
        conn.close()

    assert len(samples) == 5
    assert samples[DRAW_LABEL].tolist() == ["1", "2", "3", "4", "5"]
    assert samples[KTP_FILENAME_COL].unique().tolist() == ["2019_HCR.xlsx"]


def test_sample_pilot_order_and_labels() -> None:
    population = pd.DataFrame(
        {
            "hcr.first_name": ["Ada", "Grace", "Alan"],
            "hcr.last_name": ["Lovelace", "Hopper", "Turing"],
            "hcr.category": ["Math", "CS", "CS"],
            HCR_FILENAME_COL: ["2019_HCR.xlsx"] * 3,
        }
    )
    original = dict(_vars.HCR_XLSX_NAME_COLS)
    _vars.HCR_XLSX_NAME_COLS.clear()
    _vars.HCR_XLSX_NAME_COLS.update({"2019_HCR.xlsx": ("hcr.first_name", "hcr.last_name")})

    conn = duckdb.connect()
    try:
        conn.register("population", population)
        conn.execute("CREATE OR REPLACE TABLE population AS SELECT * FROM population")
        sample_pilot(
            conn,
            population_table="population",
            samples_table="samples",
            pilot_filename="2019_HCR.xlsx",
            economies=[],
            name_category_triples=[
                ("Grace", "Hopper", "CS"),
                ("Ada", "Lovelace", "Math"),
            ],
        )
        samples = conn.execute("SELECT * FROM samples").df()
    finally:
        conn.close()
        _vars.HCR_XLSX_NAME_COLS.clear()
        _vars.HCR_XLSX_NAME_COLS.update(original)

    assert samples[DRAW_LABEL].tolist() == ["pilot.1", "pilot.2"]
    assert samples["hcr.first_name"].tolist() == ["Grace", "Ada"]


def test_index_samples_updates_table_and_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    sample_df = pd.DataFrame(
        {
            HCR_FILENAME_COL: ["2019_HCR.xlsx"],
            "first": ["Ada"],
            "last": ["Lovelace"],
        }
    )

    original = dict(_vars.HCR_XLSX_NAME_COLS)
    _vars.HCR_XLSX_NAME_COLS.clear()
    _vars.HCR_XLSX_NAME_COLS.update({"2019_HCR.xlsx": ("first", "last")})

    conn = duckdb.connect()
    try:
        conn.register("samples", sample_df)
        conn.execute("CREATE OR REPLACE TABLE samples AS SELECT * FROM samples")
        try:
            conn.unregister("samples")
        except Exception:
            pass
        outer = index_samples(conn, samples_table="samples")
        updated = conn.execute("SELECT * FROM samples").df()
    finally:
        conn.close()
        _vars.HCR_XLSX_NAME_COLS.clear()
        _vars.HCR_XLSX_NAME_COLS.update(original)

    assert updated["ktp.first_name"].tolist() == ["Ada"]
    assert updated["ktp.last_name"].tolist() == ["Lovelace"]
    assert updated[NAME_KEY_COL].tolist() == [
        NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    ]
    assert list(outer.data.keys()) == [
        NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    ]


def test_index_samples_missing_mapping_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    sample_df = pd.DataFrame(
        {
            HCR_FILENAME_COL: ["missing.xlsx"],
            "first": ["Ada"],
            "last": ["Lovelace"],
        }
    )

    original = dict(_vars.HCR_XLSX_NAME_COLS)
    _vars.HCR_XLSX_NAME_COLS.clear()

    conn = duckdb.connect()
    try:
        conn.register("samples", sample_df)
        conn.execute("CREATE OR REPLACE TABLE samples AS SELECT * FROM samples")
        try:
            conn.unregister("samples")
        except Exception:
            pass
        with pytest.raises(ValueError, match="Missing name column mapping"):
            index_samples(conn, samples_table="samples")
    finally:
        conn.close()
        _vars.HCR_XLSX_NAME_COLS.clear()
        _vars.HCR_XLSX_NAME_COLS.update(original)


def test_match_population_first_token_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    xlsx_name = "2019_HCR.xlsx"
    original = dict(_vars.HCR_XLSX_NAME_COLS)
    _vars.HCR_XLSX_NAME_COLS.clear()
    _vars.HCR_XLSX_NAME_COLS.update({xlsx_name: ("hcr.first_name", "hcr.last_name")})

    outer = OuterDict.from_name_keys([
        NameKey(first_name="Ada Marie", last_name="Lovelace"),
    ])

    population = pd.DataFrame(
        {
            "hcr.first_name": ["ADA"],
            "hcr.last_name": ["LOVELACE"],
            HCR_FILENAME_COL: [xlsx_name],
            HCR_ROW_COL: [5],
        }
    )
    xlsx_path = tmp_path / xlsx_name
    xlsx_path.write_text("stub", encoding="utf-8")
    resources = {
        xlsx_name: register_resource(
            xlsx_path,
            group=ResourceGroup.KTP_PILOT_SAMPLE,
            fragment_type=FragmentType.EXCEL_ROW,
        )
    }

    conn = duckdb.connect()
    try:
        conn.register("population", population)
        conn.execute("CREATE OR REPLACE TABLE population AS SELECT * FROM population")
        match_population(conn, outer, population_table="population", resources=resources)
    finally:
        conn.close()
        _vars.HCR_XLSX_NAME_COLS.clear()
        _vars.HCR_XLSX_NAME_COLS.update(original)

    key = NameKey(first_name="Ada Marie", last_name="Lovelace").to_json_key()
    assert len(outer.data[key]) == 1
    assert outer.data[key][0].data[HCR_ROW_COL] == 5
