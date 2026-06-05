from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import duckdb
import pytest
from pydantic import ValidationError

from src.helpers.config import PipelineConfig
from src.helpers.data_models import (
    FragmentType,
    ResourceGroup,
    append_http_request_log_record,
    http_request_log_record,
)
from src.helpers.duckdb_extensions import load_duckdb_extension_from_config_path
from src.helpers.openalex import (
    openalex_work_titles_batch_query,
    write_openalex_paper_title_read_model,
)
from src.helpers.resources import register_pipeline_resources
from src.helpers.vars import (
    AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY,
    HCR_XLSX_KEY_PREFIX,
    KTP_ALT_NAME_COL,
    KTP_AUTHOR_DETAILS_UNNEST_KEY,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
    KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL,
    OPENALEX_AUTHOR_SEARCH_LOG_KEY,
    OPENALEX_PAPER_TITLE_LOG_KEY,
    OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY,
    OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION,
    OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION_METADATA_KEY,
    OPENALEX_TITLE_COL,
    REQUIRED_FILES_CONFIG_KEYS,
    SSNAD_AUTHORID_COL,
    SSNP_PAPERID_COL,
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
    load_duckdb_extension_from_config_path(conn, "splink_udfs")
    return conn


def _config_dict(tmp_path: Path, *, ssn_name_rule_version: int = 2) -> dict[str, object]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    author_details_path = data_dir / "author_details.parquet"
    _write_author_details(author_details_path)

    files_config: dict[str, dict[str, str]] = {}
    for key in sorted(REQUIRED_FILES_CONFIG_KEYS):
        if key == "author_details":
            path = author_details_path
        elif key in {OPENALEX_AUTHOR_SEARCH_LOG_KEY, OPENALEX_PAPER_TITLE_LOG_KEY}:
            path = data_dir / f"{key}.jsonl"
            path.write_text("", encoding="utf-8")
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
        "match_rule_version": {
            "xlsx_name": 1,
            "docx_name": 1,
            "ssn_name": ssn_name_rule_version,
            "ssn_hit": 1,
        },
    }


def test_register_pipeline_resources_creates_and_reuses_author_details_unnest(
    tmp_path: Path,
) -> None:
    config = PipelineConfig.model_validate(_config_dict(tmp_path, ssn_name_rule_version=2))
    conn = _connect_with_unaccent()
    messages: list[str] = []
    try:
        resources = register_pipeline_resources(
            config,
            conn=conn,
            log=messages.append,
        )
    finally:
        conn.close()

    assert any("HEAVY step ahead" in message for message in messages)
    assert any(KTP_AUTHOR_DETAILS_UNNEST_KEY in message for message in messages)
    assert any("SSN name rule version: v2" in message for message in messages)
    assert any(OPENALEX_AUTHOR_SEARCH_LOG_KEY in message for message in resources.messages)
    assert any(OPENALEX_PAPER_TITLE_LOG_KEY in message for message in resources.messages)

    resource = resources.author_details_unnest_resource
    assert resource is not None
    assert resource.name in resources.parquet_resources
    path = Path(resource.__fspath__())
    title_parquet_resource = resources.openalex_paper_title_parquet_resource
    assert title_parquet_resource is not None
    assert title_parquet_resource.name in resources.parquet_resources
    title_parquet_path = Path(title_parquet_resource.__fspath__())
    title_log_path = Path(resources.openalex_paper_title_log_resource.__fspath__())
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
        title_columns = [
            row[0]
            for row in conn.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{title_parquet_path}')"
            ).fetchall()
        ]
        title_metadata_rows = conn.execute(
            f"""
            SELECT decode(key), decode(value)
            FROM parquet_kv_metadata('{title_parquet_path}')
            ORDER BY 1
            """
        ).fetchall()
    finally:
        conn.close()

    assert columns == [SSNAD_AUTHORID_COL, KTP_ALT_NAME_COL]
    assert (AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY, "2") in metadata_rows
    assert ("A5058677050", "claire m fraser") in rows
    assert ("A5058677050", "claire m. fraser") in rows
    openalex_resource = resources.openalex_author_search_log_resource
    assert openalex_resource.group == ResourceGroup.KTP_PIPELINE_ARTIFACT
    assert openalex_resource.fragment_type == FragmentType.CSV_ROW
    title_log_resource = resources.openalex_paper_title_log_resource
    assert title_log_resource.group == ResourceGroup.KTP_PIPELINE_ARTIFACT
    assert title_log_resource.fragment_type == FragmentType.CSV_ROW
    assert title_parquet_resource.group == ResourceGroup.KTP_PIPELINE_ARTIFACT
    assert title_parquet_resource.fragment_type == FragmentType.PAPER_ID
    assert title_columns == [
        SSNP_PAPERID_COL,
        OPENALEX_TITLE_COL,
        KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL,
    ]
    assert (
        OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY,
        _sha256(title_log_path),
    ) in title_metadata_rows
    assert (
        OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION_METADATA_KEY,
        str(OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION),
    ) in title_metadata_rows
    papers_resource = resources.parquet_resources["papers.dat"]
    assert papers_resource.group == ResourceGroup.SCISCINET_HF
    assert papers_resource.fragment_type == FragmentType.PAPER_ID

    reused = register_pipeline_resources(config, conn=None)
    assert reused.author_details_unnest_resource is not None
    assert reused.author_details_unnest_resource.hash == resource.hash
    assert reused.openalex_paper_title_parquet_resource is not None
    assert reused.openalex_paper_title_parquet_resource.hash == title_parquet_resource.hash


def test_openalex_paper_title_parquet_rebuilds_strict_batch_log(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "openalex_paper_title_log.jsonl"
    output_path = tmp_path / "openalex_paper_titles.parquet"
    first_query = openalex_work_titles_batch_query(
        paperids=["W123", "W999"],
        api_key="REDACTED",
    )
    second_query = openalex_work_titles_batch_query(
        paperids=["W123"],
        api_key="REDACTED",
    )
    append_http_request_log_record(
        log_path=log_path,
        record=http_request_log_record(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
            method="GET",
            scheme="https",
            host="api.openalex.org",
            path="/works",
            redacted_query=first_query,
            response_code=200,
            response_body=(
                '{"results":['
                '{"id":"https://openalex.org/W123","title":"First Title"}'
                "]}"
            ),
            received_at_unix_usec=100,
            duration_usec=10,
        ),
    )
    append_http_request_log_record(
        log_path=log_path,
        record=http_request_log_record(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
            method="GET",
            scheme="https",
            host="api.openalex.org",
            path="/works",
            redacted_query=second_query,
            response_code=200,
            response_body=(
                '{"results":['
                '{"id":"https://openalex.org/W123","title":"Updated Title"}'
                "]}"
            ),
            received_at_unix_usec=200,
            duration_usec=10,
        ),
    )

    conn = duckdb.connect()
    try:
        log_hash = write_openalex_paper_title_read_model(
            conn,
            log_path=log_path,
            output_path=output_path,
        )
        rows = conn.execute(
            f"""
            SELECT
                "{SSNP_PAPERID_COL}",
                "{OPENALEX_TITLE_COL}",
                "{KTP_OPENALEX_RECEIVED_AT_UNIX_USEC_COL}"
            FROM read_parquet('{output_path}')
            ORDER BY "{SSNP_PAPERID_COL}"
            """
        ).fetchall()
        metadata_rows = conn.execute(
            f"""
            SELECT decode(key), decode(value)
            FROM parquet_kv_metadata('{output_path}')
            ORDER BY 1
            """
        ).fetchall()
    finally:
        conn.close()

    assert log_hash == _sha256(log_path)
    assert rows == [("W123", "Updated Title", 200), ("W999", None, 100)]
    assert (OPENALEX_PAPER_TITLE_LOG_SHA256_METADATA_KEY, log_hash) in metadata_rows
    assert (
        OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION_METADATA_KEY,
        str(OPENALEX_PAPER_TITLE_PARQUET_SCHEMA_VERSION),
    ) in metadata_rows


def test_openalex_paper_title_parquet_rejects_stale_log_hash(
    tmp_path: Path,
) -> None:
    config_data = _config_dict(tmp_path, ssn_name_rule_version=2)
    config = PipelineConfig.model_validate(config_data)
    conn = _connect_with_unaccent()
    try:
        register_pipeline_resources(config, conn=conn)
    finally:
        conn.close()

    files_config = cast(dict[str, dict[str, str]], config_data["files_config"])
    title_log_path = Path(files_config[OPENALEX_PAPER_TITLE_LOG_KEY]["path"])
    append_http_request_log_record(
        log_path=title_log_path,
        record=http_request_log_record(
            schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION,
            method="GET",
            scheme="https",
            host="api.openalex.org",
            path="/works",
            redacted_query=openalex_work_titles_batch_query(
                paperids=["W123"],
                api_key="REDACTED",
            ),
            response_code=200,
            response_body=(
                '{"results":['
                '{"id":"https://openalex.org/W123","title":"Fresh Title"}'
                "]}"
            ),
            received_at_unix_usec=300,
            duration_usec=10,
        ),
    )
    files_config[OPENALEX_PAPER_TITLE_LOG_KEY]["sha256"] = _sha256(title_log_path)
    stale_config = PipelineConfig.model_validate(config_data)

    with pytest.raises(ValueError, match="was built from OpenAlex title log hash"):
        register_pipeline_resources(stale_config, conn=None)


def test_configured_author_details_unnest_checks_parquet_metadata_rule_version(
    tmp_path: Path,
) -> None:
    config_data = _config_dict(tmp_path, ssn_name_rule_version=2)
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
    rule_config = cast(dict[str, object], config_data["match_rule_version"])
    rule_config["ssn_name"] = 1
    mismatched_config = PipelineConfig.model_validate(config_data)

    with pytest.raises(ValueError, match="was built with SSN name rule"):
        register_pipeline_resources(mismatched_config, conn=None)


def test_config_rejects_old_name_matching_rule_version_shape(tmp_path: Path) -> None:
    config_data = _config_dict(tmp_path, ssn_name_rule_version=1)
    config_data.pop("match_rule_version")
    config_data["name_matching_rule_version"] = {
        "xlsx": 1,
        "docx": 1,
        "sciscinet": 1,
    }

    with pytest.raises(ValidationError, match="name_matching_rule_version"):
        PipelineConfig.model_validate(config_data)


def test_config_requires_openalex_author_search_log_resource(tmp_path: Path) -> None:
    config_data = _config_dict(tmp_path, ssn_name_rule_version=1)
    files_config = cast(dict[str, dict[str, str]], config_data["files_config"])
    files_config.pop(OPENALEX_AUTHOR_SEARCH_LOG_KEY)

    with pytest.raises(ValidationError, match=OPENALEX_AUTHOR_SEARCH_LOG_KEY):
        PipelineConfig.model_validate(config_data)


def test_config_requires_openalex_paper_title_log_resource(tmp_path: Path) -> None:
    config_data = _config_dict(tmp_path, ssn_name_rule_version=1)
    files_config = cast(dict[str, dict[str, str]], config_data["files_config"])
    files_config.pop(OPENALEX_PAPER_TITLE_LOG_KEY)

    with pytest.raises(ValidationError, match=OPENALEX_PAPER_TITLE_LOG_KEY):
        PipelineConfig.model_validate(config_data)


def test_config_requires_papers_resource(tmp_path: Path) -> None:
    config_data = _config_dict(tmp_path, ssn_name_rule_version=1)
    files_config = cast(dict[str, dict[str, str]], config_data["files_config"])
    files_config.pop("papers")

    with pytest.raises(ValidationError, match="papers"):
        PipelineConfig.model_validate(config_data)
