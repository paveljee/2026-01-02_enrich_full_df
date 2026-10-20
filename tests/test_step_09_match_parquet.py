from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

import duckdb
import pytest
import requests

from src.helpers.config import PipelineConfig
from src.helpers.context import PipelineContext
from src.helpers.data_models import NameKey, OuterDict
from src.helpers.diagnostics import DiagnosticsReport
from src.helpers.duckdb_extensions import load_duckdb_extension_from_config_path
from src.helpers.duckdb_utils import duckdb_string_literal
from src.helpers.files import file_sha256
from src.helpers.openalex import (
    _OpenAlexNonOKResponse,
    openalex_paper_title_read_model_log_sha256,
    openalex_work_title_paperids_from_query,
)
from src.helpers.pipeline_manager import PipelineManager
from src.helpers.resources import register_pipeline_resources
from src.helpers.schema import (
    OUTERDICT_NAME_VIEW,
    PARQUET_ALL_HITS_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
    PARQUET_AUTHOR_PAPERS_TABLE,
)
from src.helpers.vars import (
    HCR_XLSX_KEY_PREFIX,
    KTP_FIRST_NAME_COL,
    KTP_LAST_NAME_COL,
    KTP_SOURCE_KEY_COL,
    KTP_SSN_TOP_OLDEST_PAPERS_COL,
    KTP_SSN_TOP_PAPERS_HIT_1PCT_COL,
    KTP_SSNP_PAPERID_URL_COL,
    OPENALEX_AUTHOR_SEARCH_LOG_KEY,
    OPENALEX_PAPER_TITLE_LOG_KEY,
    OPENALEX_TITLE_COL,
    REQUIRED_FILES_CONFIG_KEYS,
    SSNAD_AUTHORID_COL,
    SSNP_DATE_COL,
    SSNP_PAPERID_COL,
    TOP_K_WORKS,
    WORLD_BANK_XLSX_KEY,
)
from src.steps.step_09_match_parquet import (
    _openalex_work_title_needed_paperids_sql,
    _top_oldest_papers_ctes_sql,
    _top_papers_hit_ctes_sql,
    run,
)


def _write_step_09_fixture_parquet(
    conn: duckdb.DuckDBPyConnection,
    path: Path,
    columns: str,
    rows: list[tuple[object, ...]],
) -> None:
    conn.execute(f"CREATE OR REPLACE TEMP TABLE step_09_fixture ({columns})")
    if rows:
        placeholders = ", ".join("?" for _ in rows[0])
        conn.executemany(f"INSERT INTO step_09_fixture VALUES ({placeholders})", rows)
    conn.execute(
        f"COPY step_09_fixture TO {duckdb_string_literal(str(path))} (FORMAT PARQUET)"
    )


@pytest.mark.parametrize("fail_on_batch", [1, 2])
def test_step_09_non_ok_title_batch_preserves_successful_log_and_parquet(
    tmp_path: Path,
    fail_on_batch: int,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    conn = duckdb.connect(":memory:")
    try:
        load_duckdb_extension_from_config_path(conn, "splink_udfs")
        author_ids = [f"A{index:03d}" for index in range(21)]
        paperids = [f"W{index:03d}" for index in range(101)]
        parquet_data: dict[str, tuple[str, list[tuple[object, ...]]]] = {
            "author_details": (
                "authorid VARCHAR, display_name VARCHAR, display_name_alternatives VARCHAR",
                [(author_id, "Ada Lovelace", "[]") for author_id in author_ids],
            ),
            "authors": ("authorid VARCHAR", [(author_id,) for author_id in author_ids]),
            "authors_paper": (
                "authorid VARCHAR, paperid VARCHAR",
                [(author_ids[index // 5], paperid) for index, paperid in enumerate(paperids)],
            ),
            "paper_author_affiliation": (
                "authorid VARCHAR, paperid VARCHAR, institutionid VARCHAR",
                [],
            ),
            "affiliations": ("institution_id VARCHAR, display_name VARCHAR", []),
            "hit_papers_0": (
                'paperid VARCHAR, fieldid VARCHAR, "Hit_1pct" INTEGER',
                [(paperid, "F1", 1) for paperid in paperids],
            ),
            "hit_papers_1": (
                'paperid VARCHAR, fieldid VARCHAR, "Hit_1pct" INTEGER',
                [],
            ),
            "fields": ("fieldid VARCHAR, display_name VARCHAR", [("F1", "Field")]),
            "papers": (
                "paperid VARCHAR, date VARCHAR",
                [(paperid, "2020-01-01") for paperid in paperids],
            ),
        }
        paths: dict[str, Path] = {}
        for key, (columns, rows) in parquet_data.items():
            path = inputs / f"{key}.parquet"
            _write_step_09_fixture_parquet(conn, path, columns, rows)
            paths[key] = path
        for key in (OPENALEX_AUTHOR_SEARCH_LOG_KEY, OPENALEX_PAPER_TITLE_LOG_KEY):
            path = inputs / f"{key}.jsonl"
            path.write_text("", encoding="utf-8")
            paths[key] = path
        for key in (WORLD_BANK_XLSX_KEY, f"{HCR_XLSX_KEY_PREFIX}fixture"):
            path = inputs / f"{key}.xlsx"
            path.write_bytes(b"fixture")
            paths[key] = path
        assert REQUIRED_FILES_CONFIG_KEYS <= paths.keys()
        config = PipelineConfig.model_validate(
            {
                "files_config": {
                    key: {
                        "path": str(path),
                        "sha256": file_sha256(path),
                        "desc": f"fixture {key}",
                    }
                    for key, path in paths.items()
                },
                "db_file": tmp_path / "pipeline.duckdb",
                "state_file": tmp_path / "state.json",
                "output_dir": output_dir,
                "output_format": "txt",
                "pandoc_reference_docx": inputs / "reference.docx",
                "docx_dir": inputs,
                "timezone": "UTC",
                "sample_seed": 1,
                "sample_draw_sizes": [1],
                "pilot_xlsx_name": "fixture.xlsx",
                "total_draws": 1,
                "card_subset_mode": 0,
            }
        )
        resources = register_pipeline_resources(config, conn=conn)
        name_key = NameKey(first_name="Ada", last_name="Lovelace")
        conn.execute(
            f'CREATE TABLE {OUTERDICT_NAME_VIEW} ('
            f'"{KTP_SOURCE_KEY_COL}" VARCHAR, '
            f'"{KTP_FIRST_NAME_COL}" VARCHAR, '
            f'"{KTP_LAST_NAME_COL}" VARCHAR)'
        )
        conn.execute(
            f"INSERT INTO {OUTERDICT_NAME_VIEW} VALUES (?, ?, ?)",
            [name_key.to_json_key(), name_key.first_name, name_key.last_name],
        )
        context = PipelineContext(
            config=config,
            manager=PipelineManager(config.state_file, config.db_file),
            conn=conn,
            diagnostics=DiagnosticsReport(tmp_path / "diagnostics"),
            interactive=False,
            artifacts_dir=output_dir,
            resources=resources,
            outer_dict=OuterDict.from_name_keys([name_key]),
        )
        title_log = paths[OPENALEX_PAPER_TITLE_LOG_KEY]
        title_parquet = Path(resources.openalex_paper_title_parquet_resource)
        original_parquet_hash = file_sha256(title_parquet)
        ok_response = requests.Response()
        ok_response.status_code = HTTPStatus.OK
        ok_response._content = json.dumps(
            {"results": [{"id": "https://openalex.org/W000", "title": "First title"}]}
        ).encode("utf-8")
        non_ok_response = requests.Response()
        non_ok_response.status_code = HTTPStatus.TOO_MANY_REQUESTS
        responses = [non_ok_response] if fail_on_batch == 1 else [ok_response, non_ok_response]
        with patch.object(requests, "get", side_effect=responses) as request_get:
            with pytest.raises(_OpenAlexNonOKResponse) as raised:
                run(context)
        assert raised.value.record.response_code == HTTPStatus.TOO_MANY_REQUESTS
        assert request_get.call_count == fail_on_batch
        records = [json.loads(line) for line in title_log.read_text(encoding="utf-8").splitlines()]
        if fail_on_batch == 1:
            assert records == []
            assert file_sha256(title_parquet) == original_parquet_hash
        else:
            assert len(records) == 1
            assert records[0]["response_code"] == HTTPStatus.OK
            assert openalex_work_title_paperids_from_query(records[0]["query"]) == tuple(
                paperids[:100]
            )
            assert file_sha256(title_parquet) != original_parquet_hash
            assert openalex_paper_title_read_model_log_sha256(conn, title_parquet) == file_sha256(
                title_log
            )
            title_rows = conn.execute(
                f'SELECT "{SSNP_PAPERID_COL}", "{OPENALEX_TITLE_COL}" '
                f"FROM read_parquet({duckdb_string_literal(str(title_parquet))}) "
                f'ORDER BY "{SSNP_PAPERID_COL}"'
            ).fetchall()
            assert title_rows == [
                (paperid, "First title" if paperid == "W000" else None)
                for paperid in paperids[:100]
            ]
    finally:
        conn.close()


def test_openalex_work_title_needed_paperids_uses_only_reduced_top_sets() -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_PAPERS_TABLE} (
                name_key VARCHAR,
                authorid VARCHAR,
                paperid VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} (
                name_key VARCHAR,
                "{SSNAD_AUTHORID_COL}" VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_ALL_HITS_TABLE} (
                paperid VARCHAR,
                hit_1pct BIGINT
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE ssn_sciscinet_papers (
                "{SSNP_PAPERID_COL}" VARCHAR,
                "{SSNP_DATE_COL}" VARCHAR
            )
            """
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_PAPERS_TABLE} VALUES (?, ?, ?)",
            [
                ("ada", "A1", "W1"),
                ("ada", "A1", "W2"),
                ("ada", "A1", "W3"),
                ("ada", "A1", "W4"),
                ("ada", "A1", "W5"),
                ("ada", "A1", "W6"),
                ("ada", "A1", "W7"),
                ("ada", "A1", "W8"),
                ("ada", "A2", "W0"),
            ],
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} VALUES (?, ?)",
            [("ada", "A1")],
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_ALL_HITS_TABLE} VALUES (?, ?)",
            [
                ("W1", 9),
                ("W2", 8),
                ("W3", 7),
                ("W4", 6),
                ("W5", 5),
                ("W6", 4),
                ("W7", 0),
                ("W8", 1),
                ("W0", 99),
            ],
        )
        conn.executemany(
            "INSERT INTO ssn_sciscinet_papers VALUES (?, ?)",
            [
                ("W1", "1996-01-01"),
                ("W2", "1995-01-01"),
                ("W3", "1994-01-01"),
                ("W4", "1993-01-01"),
                ("W5", "1992-01-01"),
                ("W6", "1991-01-01"),
                ("W7", "1990-01-01"),
                ("W8", "2020-01-01"),
                ("W0", "1800-01-01"),
            ],
        )

        rows = conn.execute(
            _openalex_work_title_needed_paperids_sql(
                author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
                all_hits_table=PARQUET_ALL_HITS_TABLE,
                selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
                papers_table="ssn_sciscinet_papers",
                author_id_col=SSNAD_AUTHORID_COL,
                paperid_col=SSNP_PAPERID_COL,
                date_col=SSNP_DATE_COL,
                top_k_works=TOP_K_WORKS,
            )
        ).fetchall()
    finally:
        conn.close()

    assert [row[0] for row in rows] == ["W1", "W2", "W3", "W4", "W5", "W6", "W7"]


def test_top_oldest_papers_sql_orders_by_date_truncates_and_omits_null_date() -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_PAPERS_TABLE} (
                name_key VARCHAR,
                authorid VARCHAR,
                paperid VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} (
                name_key VARCHAR,
                "{SSNAD_AUTHORID_COL}" VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE ssn_sciscinet_papers (
                "{SSNP_PAPERID_COL}" VARCHAR,
                "{SSNP_DATE_COL}" VARCHAR
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE openalex_work_titles (
                paperid VARCHAR,
                title VARCHAR
            )
            """
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_PAPERS_TABLE} VALUES (?, ?, ?)",
            [
                ("ada", "A1", "W7"),
                ("ada", "A1", "W2"),
                ("ada", "A1", "W1"),
                ("ada", "A1", "W3"),
                ("ada", "A1", "W4"),
                ("ada", "A1", "W5"),
                ("ada", "A1", "W6"),
                ("ada", "A2", "W0"),
            ],
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} VALUES (?, ?)",
            [("ada", "A1")],
        )
        conn.executemany(
            "INSERT INTO ssn_sciscinet_papers VALUES (?, ?)",
            [
                ("W7", "2012-01-01"),
                ("W2", "1999-05-20"),
                ("W1", "1999-05-20"),
                ("W3", "1999-05-19"),
                ("W4", None),
                ("W5", "2010-01-01"),
                ("W6", "2011-01-01"),
                ("W0", "1800-01-01"),
            ],
        )
        conn.executemany(
            "INSERT INTO openalex_work_titles VALUES (?, ?)",
            [
                ("W1", "Old W1"),
                ("W2", "Old W2"),
                ("W3", "Old W3"),
                ("W5", "Old W5"),
                ("W6", "Old W6"),
                ("W7", "Old W7"),
            ],
        )

        ctes = _top_oldest_papers_ctes_sql(
            author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
            selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
            papers_table="ssn_sciscinet_papers",
            title_table="openalex_work_titles",
            author_id_col=SSNAD_AUTHORID_COL,
            paperid_col=SSNP_PAPERID_COL,
            date_col=SSNP_DATE_COL,
            top_k_works=TOP_K_WORKS,
        )
        row = conn.execute(
            f"""
            WITH {ctes}
            SELECT "{KTP_SSN_TOP_OLDEST_PAPERS_COL}"
            FROM top_oldest_papers
            WHERE name_key = 'ada' AND authorid = 'A1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    payload = json.loads(row[0])
    assert payload == [
        {
            SSNP_DATE_COL: "1999-05-19",
            OPENALEX_TITLE_COL: "Old W3",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W3",
        },
        {
            SSNP_DATE_COL: "1999-05-20",
            OPENALEX_TITLE_COL: "Old W1",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W1",
        },
        {
            SSNP_DATE_COL: "1999-05-20",
            OPENALEX_TITLE_COL: "Old W2",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W2",
        },
        {
            SSNP_DATE_COL: "2010-01-01",
            OPENALEX_TITLE_COL: "Old W5",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W5",
        },
        {
            SSNP_DATE_COL: "2011-01-01",
            OPENALEX_TITLE_COL: "Old W6",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W6",
        },
    ]


def test_top_hit_papers_sql_preserves_hit_order_and_includes_titles() -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_PAPERS_TABLE} (
                name_key VARCHAR,
                authorid VARCHAR,
                paperid VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} (
                name_key VARCHAR,
                "{SSNAD_AUTHORID_COL}" VARCHAR
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE {PARQUET_ALL_HITS_TABLE} (
                paperid VARCHAR,
                hit_1pct BIGINT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE openalex_work_titles (
                paperid VARCHAR,
                title VARCHAR
            )
            """
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_PAPERS_TABLE} VALUES (?, ?, ?)",
            [
                ("ada", "A1", "W7"),
                ("ada", "A1", "W2"),
                ("ada", "A1", "W1"),
                ("ada", "A1", "W3"),
                ("ada", "A1", "W5"),
                ("ada", "A1", "W6"),
                ("ada", "A2", "W0"),
            ],
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} VALUES (?, ?)",
            [("ada", "A1")],
        )
        conn.executemany(
            f"INSERT INTO {PARQUET_ALL_HITS_TABLE} VALUES (?, ?)",
            [
                ("W7", 1),
                ("W2", 5),
                ("W1", 5),
                ("W3", 3),
                ("W5", 2),
                ("W6", 1),
                ("W0", 99),
            ],
        )
        conn.executemany(
            "INSERT INTO openalex_work_titles VALUES (?, ?)",
            [
                ("W1", "Hit W1"),
                ("W2", "Hit W2"),
                ("W3", "Hit W3"),
                ("W5", "Hit W5"),
                ("W6", "Hit W6"),
                ("W7", "Hit W7"),
            ],
        )

        ctes = _top_papers_hit_ctes_sql(
            author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
            all_hits_table=PARQUET_ALL_HITS_TABLE,
            selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
            title_table="openalex_work_titles",
            author_id_col=SSNAD_AUTHORID_COL,
            top_k_works=TOP_K_WORKS,
        )
        row = conn.execute(
            f"""
            WITH {ctes}
            SELECT "{KTP_SSN_TOP_PAPERS_HIT_1PCT_COL}"
            FROM top_papers
            WHERE name_key = 'ada' AND authorid = 'A1'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    payload = json.loads(row[0])
    assert payload == [
        {
            OPENALEX_TITLE_COL: "Hit W1",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W1",
        },
        {
            OPENALEX_TITLE_COL: "Hit W2",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W2",
        },
        {
            OPENALEX_TITLE_COL: "Hit W3",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W3",
        },
        {
            OPENALEX_TITLE_COL: "Hit W5",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W5",
        },
        {
            OPENALEX_TITLE_COL: "Hit W6",
            KTP_SSNP_PAPERID_URL_COL: "https://openalex.org/W6",
        },
    ]
