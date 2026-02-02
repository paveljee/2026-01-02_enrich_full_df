from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import pandas as pd

from src.data_models import FragmentType, ResourceGroup
from src.utils.duckdb import register_frame
from src.utils.files import find_files_by_extension
from src.utils.name_keys import build_name_key_frame
from src.utils.resources import register_resource, register_resources
from src.data_models import NameKey, OuterDict


def test_register_frame_replaces_schema() -> None:
    conn = duckdb.connect()
    try:
        df1 = pd.DataFrame({"a": [1, 2]})
        register_frame(conn, "demo", df1)
        df2 = pd.DataFrame({"b": ["x"]})
        register_frame(conn, "demo", df2)

        cols = conn.execute("PRAGMA table_info('demo')").fetchall()
        col_names = [row[1] for row in cols]
        assert col_names == ["b"]
        assert conn.execute("SELECT COUNT(*) FROM demo").fetchone()[0] == 1
    finally:
        conn.close()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_register_resource_expected_hash(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("content", encoding="utf-8")
    expected = _sha256(path)

    resource = register_resource(
        path,
        group=ResourceGroup.REGISTERED_SAMPLES,
        fragment_type=FragmentType.CSV_ROW,
        expected_hash=expected,
    )
    assert resource.hash == expected


def test_register_resources_expected_hashes(tmp_path: Path) -> None:
    path_a = tmp_path / "a.txt"
    path_b = tmp_path / "b.txt"
    path_a.write_text("alpha", encoding="utf-8")
    path_b.write_text("beta", encoding="utf-8")

    expected_a = _sha256(path_a)
    resources = register_resources(
        [path_a, path_b],
        group=ResourceGroup.REGISTERED_SAMPLES,
        fragment_type=FragmentType.CSV_ROW,
        expected_hashes={path_a.name: expected_a},
    )

    assert resources[path_a.name].hash == expected_a
    assert resources[path_b.name].hash == _sha256(path_b)


def test_find_files_by_extension_uppercase(tmp_path: Path) -> None:
    file_path = tmp_path / "REPORT.TXT"
    file_path.write_text("ok", encoding="utf-8")

    matches = find_files_by_extension(tmp_path, "TXT")
    assert matches == [file_path]


def test_build_name_key_frame_order() -> None:
    outer = OuterDict.from_name_keys(
        [
            NameKey(first_name="Ada", last_name="Lovelace"),
            NameKey(first_name="Grace", last_name="Hopper"),
        ]
    )
    df = build_name_key_frame(outer)
    assert df.iloc[0].tolist() == [
        NameKey(first_name="Ada", last_name="Lovelace").to_json_key(),
        "Ada",
        "Lovelace",
    ]
    assert df.iloc[1].tolist() == [
        NameKey(first_name="Grace", last_name="Hopper").to_json_key(),
        "Grace",
        "Hopper",
    ]
