from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import duckdb
import pytest

from src.helpers.config import PipelineConfig
from src.helpers.resources import register_pipeline_resources
from src.helpers.vars import (
    AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY,
    HCR_XLSX_KEY_PREFIX,
    KTP_ALT_NAME_COL,
    KTP_AUTHOR_DETAILS_UNNEST_KEY,
    REQUIRED_FILES_CONFIG_KEYS,
    SSNAD_AUTHORID_COL,
    WORLD_BANK_XLSX_KEY,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_author_details(path: Path) -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            f"""
            COPY (
                SELECT
                    'A5058677050' AS authorid,
                    'Claire M. Fraser' AS display_name,
                    '["C. Fraser", "Claire Fraser-Liggett"]' AS display_name_alternatives
            ) TO '{path}' (FORMAT PARQUET)
            """
        )
    finally:
        conn.close()


def _connect_with_unaccent() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
    return conn


def _config_dict(tmp_path: Path, *, sciscinet_rule_version: int = 2) -> dict[str, object]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    author_details_path = data_dir / "author_details.parquet"
    _write_author_details(author_details_path)

    files_config: dict[str, dict[str, str]] = {}
    for key in sorted(REQUIRED_FILES_CONFIG_KEYS):
        if key == "author_details":
            path = author_details_path
        elif key == WORLD_BANK_XLSX_KEY:
            path = data_dir / "world_bank.xlsx"
            path.write_text("world bank", encoding="utf-8")
        else:
            path = data_dir / f"{key}.dat"
            path.write_text(f"dummy-{key}", encoding="utf-8")
        files_config[key] = {
            "path": str(path),
            "sha256": _sha256(path),
            "desc": f"fixture {key}",
        }

    hcr_path = data_dir / "hcr.xlsx"
    hcr_path.write_text("hcr", encoding="utf-8")
    files_config[f"{HCR_XLSX_KEY_PREFIX}fixture"] = {
        "path": str(hcr_path),
        "sha256": _sha256(hcr_path),
        "desc": "fixture hcr",
    }

    docx_dir = data_dir / "docx"
    docx_dir.mkdir()
    reference_docx = data_dir / "reference.docx"
    reference_docx.write_text("reference", encoding="utf-8")

    return {
        "files_config": files_config,
        "db_file": str(tmp_path / "pipeline.duckdb"),
        "state_file": str(tmp_path / "pipeline.state.json"),
        "output_dir": str(tmp_path / "output"),
        "output_format": "txt",
        "pandoc_reference_docx": str(reference_docx),
        "docx_dir": str(docx_dir),
        "timezone": "UTC",
        "sample_seed": 1,
        "sample_draw_sizes": [1],
        "pilot_xlsx_name": "hcr.xlsx",
        "total_draws": 1,
        "card_subset_mode": 0,
        "name_matching_rule_version": {
            "xlsx": 1,
            "docx": 1,
            "sciscinet": sciscinet_rule_version,
        },
    }


def test_register_pipeline_resources_creates_and_reuses_author_details_unnest(
    tmp_path: Path,
) -> None:
    config = PipelineConfig.model_validate(_config_dict(tmp_path, sciscinet_rule_version=2))
    conn = _connect_with_unaccent()
    progress_messages: list[str] = []
    try:
        resources = register_pipeline_resources(
            config,
            conn=conn,
            progress_log=progress_messages.append,
        )
    finally:
        conn.close()

    assert any("HEAVY step ahead" in message for message in progress_messages)
    assert any(KTP_AUTHOR_DETAILS_UNNEST_KEY in message for message in progress_messages)
    assert any("sciscinet rule version: v2" in message for message in progress_messages)

    resource = resources.author_details_unnest_resource
    assert resource is not None
    assert resource.name in resources.parquet_resources
    path = Path(resource.__fspath__())
    metadata_path = path.with_suffix(path.suffix + ".metadata.json")
    assert not metadata_path.exists()

    conn = duckdb.connect()
    try:
        columns = [
            row[0]
            for row in conn.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()
        ]
        metadata_rows = conn.execute(
            f"""
            SELECT decode(key), decode(value)
            FROM parquet_kv_metadata('{path}')
            ORDER BY 1
            """
        ).fetchall()
        rows = conn.execute(
            f"""
            SELECT "{SSNAD_AUTHORID_COL}", "{KTP_ALT_NAME_COL}"
            FROM read_parquet('{path}')
            ORDER BY 1, 2
            """
        ).fetchall()
    finally:
        conn.close()

    assert columns == [SSNAD_AUTHORID_COL, KTP_ALT_NAME_COL]
    assert (AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY, "2") in metadata_rows
    assert ("A5058677050", "claire m fraser") in rows
    assert ("A5058677050", "claire m. fraser") in rows

    reused = register_pipeline_resources(config, conn=None)
    assert reused.author_details_unnest_resource is not None
    assert reused.author_details_unnest_resource.hash == resource.hash


def test_configured_author_details_unnest_checks_parquet_metadata_rule_version(
    tmp_path: Path,
) -> None:
    config_data = _config_dict(tmp_path, sciscinet_rule_version=2)
    config = PipelineConfig.model_validate(config_data)
    conn = _connect_with_unaccent()
    try:
        resources = register_pipeline_resources(config, conn=conn)
    finally:
        conn.close()

    resource = resources.author_details_unnest_resource
    assert resource is not None
    path = Path(resource.__fspath__())
    files_config = cast(dict[str, dict[str, str]], config_data["files_config"])
    files_config[KTP_AUTHOR_DETAILS_UNNEST_KEY] = {
        "path": str(path),
        "sha256": resource.hash,
        "desc": "configured derived resource",
    }
    rule_config = cast(dict[str, Any], config_data["name_matching_rule_version"])
    rule_config["sciscinet"] = 1
    mismatched_config = PipelineConfig.model_validate(config_data)

    with pytest.raises(ValueError, match="was built with sciscinet rule"):
        register_pipeline_resources(mismatched_config, conn=None)
