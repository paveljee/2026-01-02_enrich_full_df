from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import duckdb

from ..helpers.context import (
    PipelineContext,
    PipelineResources,
    StepResult,
)
from ..helpers.duckdb_utils import (
    append_innerdicts_from_rows_table,
    duckdb_quote_identifier,
    duckdb_string_literal,
)
from ..helpers.files import file_sha256
from ..helpers.name_matching import (
    sciscinet_ktp_name_norm_sql,
)
from ..helpers.openalex import (
    check_openalex_author,
    chunk_openalex_work_title_paperids,
    fetch_openalex_work_titles_batch,
    openalex_paper_title_read_model_log_sha256,
    write_openalex_paper_title_read_model,
)
from ..helpers.parquet_utils import normalize_parquet_column_name, parquet_columns, parquet_filename
from ..helpers.procedures import ParquetMatchProcedure
from ..helpers.schema import (
    OUTERDICT_NAME_VIEW,
    PARQUET_ALL_HITS_TABLE,
    PARQUET_AUTHOR_AGG_TABLE,
    PARQUET_AUTHOR_HIT_AGG_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_PRE_OPENALEX_TABLE,
    PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
    PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW,
    PARQUET_AUTHOR_MATCH_OPENALEX_CHECK_TABLE,
    PARQUET_AUTHOR_MATCH_TABLE,
    PARQUET_AUTHOR_OUTPUT_TABLE,
    PARQUET_AUTHOR_PAPERS_TABLE,
    PARQUET_INNERDICT_TABLE,
    PARQUET_OUTPUT_VIEW,
    SAMPLES_WITH_NAMES_VIEW,
    safe_identifier,
)
from ..helpers.ssn_hit_selection import (
    ssn_hit_metadata_select_sql,
    ssn_hit_openalex_check_candidates_sql,
    ssn_hit_openalex_check_insert_sql,
    ssn_hit_openalex_check_table_sql,
    ssn_hit_openalex_selected_view_sql,
    ssn_hit_selected_author_ids_view_sql,
    ssn_hit_selected_view_sql,
    ssn_hit_v2_bounds_summary_sql,
    ssn_hit_v2_candidate_metrics_table_sql,
    ssn_hit_v2_selection_breakdown_sql,
    ssn_nonzero_hit_view_sql,
    ssn_removed_zero_hit_count_sql,
)
from ..helpers.vars import (
    DRAW_LABEL,
    KTP_ALT_NAME_COL,
    KTP_AUTHOR_DETAILS_UNNEST_KEY,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_LAST_NAME_COL,
    KTP_OPENALEX_MATCH_COL,
    KTP_OPENALEX_REUSED_COL,
    KTP_SOURCE_KEY_COL,
    KTP_SSN_COUNT_PAPERID_COL,
    KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
    KTP_SSN_MATCH_RULE_KEY,
    KTP_SSN_MATCH_RULE_V1,
    KTP_SSN_MATCH_RULE_V2,
    KTP_SSN_SUM_HIT_1PCT_COL,
    KTP_SSN_TOP_INSTITUTIONS_COL,
    KTP_SSN_TOP_OLDEST_PAPERS_COL,
    KTP_SSN_TOP_PAPERS_HIT_1PCT_COL,
    KTP_SSNAD_FILENAME_COL,
    KTP_SSNAD_MATCH_COL,
    KTP_SSNAD_MATCH_KTP_NAME_NORM_KEY,
    KTP_SSNAD_MATCH_SSNAD_NAME_NORM_KEY,
    KTP_SSNAF_FILENAME_COL,
    KTP_SSNAP_FILENAME_COL,
    KTP_SSNAU_FILENAME_COL,
    KTP_SSNF_FILENAME_COL,
    KTP_SSNHPL0_FILENAME_COL,
    KTP_SSNHPL1_FILENAME_COL,
    KTP_SSNP_FILENAME_COL,
    KTP_SSNP_PAPERID_URL_COL,
    KTP_SSNPAA_FILENAME_COL,
    OPENALEX_TITLE_COL,
    SSN_FIELD_IDS_LIST_COL,
    SSN_PAPERIDS_LEVEL0_COL,
    SSN_PAPERIDS_LEVEL1_COL,
    SSNAD_AUTHORID_COL,
    SSNAD_RAW_AUTHORID_COL,
    SSNAF_DISPLAY_NAME_COL,
    SSNP_DATE_COL,
    SSNP_PAPERID_COL,
    SSNPAA_INSTITUTION_ID_COL,
    STEP_MATCH_PARQUET,
    STEP_MATCH_PARQUET_LOG_LEGEND_LINES,
    STEP_MATCH_PARQUET_LOG_TAG_LEGEND,
    STEP_MATCH_PARQUET_LOG_TAG_OUTERDICT,
    STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
    STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
    STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
    STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
    STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT,
    TOP_K_INSTITUTIONS,
    TOP_K_WORKS,
)
from .shared import draw_sort_ctes_sql, draw_sort_order_by_sql


def _create_parquet_table(
    conn: duckdb.DuckDBPyConnection,
    *,
    table_name: str,
    path: str,
    prefix: str,
    filename_col: str,
    join_sql: str,
) -> dict[str, str]:
    columns = parquet_columns(conn, path)
    select_cols = ", ".join(
        [f'parq."{col}" AS "{normalize_parquet_column_name(col, prefix)}"' for col in columns]
    )
    filename = parquet_filename(path)
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT {select_cols},
               '{filename}' AS "{filename_col}"
        FROM read_parquet('{path}') parq
        {join_sql}
        """
    )
    return {col: normalize_parquet_column_name(col, prefix) for col in columns}


def _raw_column_for_normalized(
    columns: list[str],
    *,
    prefix: str,
    normalized_col: str,
) -> str:
    for col in columns:
        if normalize_parquet_column_name(col, prefix) == normalized_col:
            return col
    raise ValueError(f"Missing parquet column normalized as {normalized_col!r}.")


def _top_oldest_papers_ctes_sql(
    *,
    author_papers_table: str,
    selected_author_view: str,
    papers_table: str,
    title_table: str,
    author_id_col: str,
    paperid_col: str,
    date_col: str,
    top_k_works: int,
) -> str:
    return f"""
        oldest_paper_candidates AS (
            SELECT
                ap.name_key AS name_key,
                ap.authorid AS authorid,
                CAST(ap.paperid AS VARCHAR) AS paperid,
                TRY_CAST(p.{duckdb_quote_identifier(date_col)} AS DATE) AS date_value
            FROM {author_papers_table} ap
            JOIN {papers_table} p
              ON CAST(p.{duckdb_quote_identifier(paperid_col)} AS VARCHAR)
                = CAST(ap.paperid AS VARCHAR)
            WHERE ap.paperid IS NOT NULL
              AND TRY_CAST(p.{duckdb_quote_identifier(date_col)} AS DATE) IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM {selected_author_view} m
                  WHERE m.name_key = ap.name_key
                    AND CAST(m.{duckdb_quote_identifier(author_id_col)} AS VARCHAR)
                        = CAST(ap.authorid AS VARCHAR)
              )
        ),
        oldest_paper_ranked AS (
            SELECT
                opc.name_key AS name_key,
                opc.authorid AS authorid,
                opc.paperid AS paperid,
                opc.date_value AS date_value,
                ROW_NUMBER() OVER (
                    PARTITION BY opc.name_key, opc.authorid
                    ORDER BY opc.date_value ASC, opc.paperid ASC
                ) AS rn
            FROM oldest_paper_candidates opc
        ),
        top_oldest_papers AS (
            SELECT
                opr.name_key AS name_key,
                opr.authorid AS authorid,
                CAST(
                    LIST(
                        json_object(
                            '{SSNP_DATE_COL}', CAST(opr.date_value AS VARCHAR),
                            '{OPENALEX_TITLE_COL}', wt.title,
                            '{KTP_SSNP_PAPERID_URL_COL}',
                            'https://openalex.org/' || CAST(opr.paperid AS VARCHAR)
                        )
                        ORDER BY opr.date_value ASC, opr.paperid ASC
                    )
                        FILTER (WHERE opr.rn <= {top_k_works})
                    AS VARCHAR
                ) AS "{KTP_SSN_TOP_OLDEST_PAPERS_COL}"
            FROM oldest_paper_ranked opr
            LEFT JOIN {title_table} wt
              ON wt.paperid = opr.paperid
            GROUP BY opr.name_key, opr.authorid
        )
    """


def _top_papers_hit_ctes_sql(
    *,
    author_papers_table: str,
    all_hits_table: str,
    selected_author_view: str,
    title_table: str,
    author_id_col: str,
    top_k_works: int,
) -> str:
    return f"""
        paper_hits AS (
            SELECT
                ap.name_key AS name_key,
                ap.authorid AS authorid,
                ap.paperid AS paperid,
                COALESCE(MAX(h.hit_1pct), 0) AS hit_1pct
            FROM {author_papers_table} ap
            LEFT JOIN {all_hits_table} h
              ON ap.paperid = h.paperid
            WHERE EXISTS (
                SELECT 1
                FROM {selected_author_view} m
                WHERE m.name_key = ap.name_key
                  AND CAST(m.{duckdb_quote_identifier(author_id_col)} AS VARCHAR)
                    = CAST(ap.authorid AS VARCHAR)
            )
            GROUP BY ap.name_key, ap.authorid, ap.paperid
        ),
        paper_ranked AS (
            SELECT
                ph.name_key AS name_key,
                ph.authorid AS authorid,
                ph.paperid AS paperid,
                ph.hit_1pct AS hit_1pct,
                ROW_NUMBER() OVER (
                    PARTITION BY ph.name_key, ph.authorid
                    ORDER BY ph.hit_1pct DESC, ph.paperid ASC
                ) AS rn
            FROM paper_hits ph
        ),
        top_papers AS (
            SELECT
                pr.name_key AS name_key,
                pr.authorid AS authorid,
                CAST(
                    LIST(
                        json_object(
                            '{OPENALEX_TITLE_COL}', wt.title,
                            '{KTP_SSNP_PAPERID_URL_COL}',
                            'https://openalex.org/' || CAST(pr.paperid AS VARCHAR)
                        )
                        ORDER BY pr.hit_1pct DESC, pr.paperid ASC
                    )
                        FILTER (WHERE pr.rn <= {top_k_works})
                    AS VARCHAR
                ) AS "{KTP_SSN_TOP_PAPERS_HIT_1PCT_COL}"
            FROM paper_ranked pr
            LEFT JOIN {title_table} wt
              ON wt.paperid = CAST(pr.paperid AS VARCHAR)
            GROUP BY pr.name_key, pr.authorid
        )
    """


def _openalex_work_title_needed_paperids_sql(
    *,
    author_papers_table: str,
    all_hits_table: str,
    selected_author_view: str,
    papers_table: str,
    author_id_col: str,
    paperid_col: str,
    date_col: str,
    top_k_works: int,
) -> str:
    return f"""
        WITH paper_hits AS (
            SELECT
                ap.name_key AS name_key,
                ap.authorid AS authorid,
                CAST(ap.paperid AS VARCHAR) AS paperid,
                COALESCE(MAX(h.hit_1pct), 0) AS hit_1pct
            FROM {author_papers_table} ap
            LEFT JOIN {all_hits_table} h
              ON ap.paperid = h.paperid
            WHERE ap.paperid IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM {selected_author_view} m
                  WHERE m.name_key = ap.name_key
                    AND CAST(m.{duckdb_quote_identifier(author_id_col)} AS VARCHAR)
                        = CAST(ap.authorid AS VARCHAR)
              )
            GROUP BY ap.name_key, ap.authorid, CAST(ap.paperid AS VARCHAR)
        ),
        top_work_ranked AS (
            SELECT
                ph.paperid AS paperid,
                ROW_NUMBER() OVER (
                    PARTITION BY ph.name_key, ph.authorid
                    ORDER BY ph.hit_1pct DESC, ph.paperid ASC
                ) AS rn
            FROM paper_hits ph
        ),
        oldest_paper_candidates AS (
            SELECT
                ap.name_key AS name_key,
                ap.authorid AS authorid,
                CAST(ap.paperid AS VARCHAR) AS paperid,
                TRY_CAST(p.{duckdb_quote_identifier(date_col)} AS DATE) AS date_value
            FROM {author_papers_table} ap
            JOIN {papers_table} p
              ON CAST(p.{duckdb_quote_identifier(paperid_col)} AS VARCHAR)
                = CAST(ap.paperid AS VARCHAR)
            WHERE ap.paperid IS NOT NULL
              AND TRY_CAST(p.{duckdb_quote_identifier(date_col)} AS DATE) IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM {selected_author_view} m
                  WHERE m.name_key = ap.name_key
                    AND CAST(m.{duckdb_quote_identifier(author_id_col)} AS VARCHAR)
                        = CAST(ap.authorid AS VARCHAR)
              )
        ),
        top_oldest_ranked AS (
            SELECT
                opc.paperid AS paperid,
                ROW_NUMBER() OVER (
                    PARTITION BY opc.name_key, opc.authorid
                    ORDER BY opc.date_value ASC, opc.paperid ASC
                ) AS rn
            FROM oldest_paper_candidates opc
        )
        SELECT DISTINCT paperid
        FROM (
            SELECT paperid FROM top_work_ranked WHERE rn <= {top_k_works}
            UNION ALL
            SELECT paperid FROM top_oldest_ranked WHERE rn <= {top_k_works}
        ) selected_papers
        ORDER BY paperid
    """


def run(context: PipelineContext) -> StepResult:
    if context.outer_dict is None:
        raise ValueError("OuterDict not initialized. Run build_outerdict first.")
    if context.resources is None:
        raise ValueError("Resources not initialized. Run register_resources first.")

    def log(msg: str) -> None:
        if context.log:
            context.log(msg, "cyan")

    def log_tag(tag: str, msg: str) -> None:
        log(f"[{tag}] {msg}")

    conn: duckdb.DuckDBPyConnection = context.conn
    files = context.config.files_config
    author_details_path = files["author_details"]["path"]
    authors_path = files["authors"]["path"]
    authors_paper_path = files["authors_paper"]["path"]
    paper_author_affiliation_path = files["paper_author_affiliation"]["path"]
    affiliations_path = files["affiliations"]["path"]
    hit_papers0_path = files["hit_papers_0"]["path"]
    hit_papers1_path = files["hit_papers_1"]["path"]
    fields_path = files["fields"]["path"]
    papers_path = files["papers"]["path"]

    if context.resources.author_details_unnest_resource is None:
        raise ValueError(
            f"Missing {KTP_AUTHOR_DETAILS_UNNEST_KEY} resource. Run register_resources first."
        )

    author_details_unnest_path = context.resources.author_details_unnest_resource.__fspath__()
    openalex_log_path = Path(context.resources.openalex_author_search_log_resource.__fspath__())
    openalex_paper_title_log_path = Path(
        context.resources.openalex_paper_title_log_resource.__fspath__()
    )
    openalex_paper_title_parquet_path = Path(
        context.resources.openalex_paper_title_parquet_resource.__fspath__()
    )
    openalex_paper_title_log_hash = file_sha256(openalex_paper_title_log_path)
    author_id_col = SSNAD_AUTHORID_COL
    authors_author_id_col = normalize_parquet_column_name(SSNAD_RAW_AUTHORID_COL, "ssnau")
    author_id_raw = SSNAD_RAW_AUTHORID_COL
    ssn_rule_version = context.config.match_rule_version.ssn_name
    ssn_hit_rule_version = context.config.match_rule_version.ssn_hit
    ssn_match_rule = KTP_SSN_MATCH_RULE_V2 if ssn_rule_version == 2 else KTP_SSN_MATCH_RULE_V1
    ktp_match_key_expr = sciscinet_ktp_name_norm_sql(
        f'"{KTP_FIRST_NAME_COL}"',
        f'"{KTP_LAST_NAME_COL}"',
        rule_version=ssn_rule_version,
    )

    def scalar_int(sql: str) -> int:
        row = conn.execute(sql).fetchone()
        if row is None or row[0] is None:
            return 0
        return int(row[0])

    def materialize_openalex_work_titles(
            title_table: str,
            resources: PipelineResources
        ) -> None:
        needed_table = "openalex_work_title_needed_paperids"
        title_parquet_sql = duckdb_string_literal(str(openalex_paper_title_parquet_path))
        parquet_log_hash = openalex_paper_title_read_model_log_sha256(
            conn,
            openalex_paper_title_parquet_path,
        )
        hash_matches = parquet_log_hash == openalex_paper_title_log_hash
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
            "OpenAlex work-title query side: "
            f"parquet={openalex_paper_title_parquet_path}; "
            f"parquet title-log sha256={parquet_log_hash or '<missing>'}; "
            f"current JSONL sha256={openalex_paper_title_log_hash}; "
            f"hash match={'yes' if hash_matches else 'no'}.",
        )
        if not hash_matches:
            raise ValueError(
                "OpenAlex paper-title parquet read model is out of sync with the "
                "registered JSONL command log. Re-run resource registration."
            )
        conn.execute(
            f"""
            CREATE OR REPLACE TEMP TABLE {needed_table} AS
            {_openalex_work_title_needed_paperids_sql(
                author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
                all_hits_table=PARQUET_ALL_HITS_TABLE,
                selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
                papers_table=papers_table,
                author_id_col=author_id_col,
                paperid_col=SSNP_PAPERID_COL,
                date_col=SSNP_DATE_COL,
                top_k_works=TOP_K_WORKS,
            )}
            """
        )
        needed_count = scalar_int(f"SELECT COUNT(*) FROM {needed_table}")
        missing_rows = conn.execute(
            f"""
            SELECT n.paperid
            FROM {needed_table} n
            LEFT JOIN read_parquet({title_parquet_sql}) t
              ON CAST(t."{SSNP_PAPERID_COL}" AS VARCHAR) = n.paperid
            WHERE t."{SSNP_PAPERID_COL}" IS NULL
            ORDER BY n.paperid
            """
        ).fetchall()
        missing_paperids = [str(row[0]) for row in missing_rows]
        present_paperid_count = needed_count - len(missing_paperids)
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
            "OpenAlex work-title query side coverage: "
            f"needed paper IDs={needed_count:,}, "
            f"present in read model={present_paperid_count:,}, "
            f"missing from read model={len(missing_paperids):,}.",
        )
        appended_log_record_count = 0
        fetched_titled_count = 0
        response_status_counts: dict[str, int] = {}
        if missing_paperids:
            for batch in chunk_openalex_work_title_paperids(missing_paperids):
                result = fetch_openalex_work_titles_batch(
                    paperids=batch,
                    log_path=openalex_paper_title_log_path,
                )
                appended_log_record_count += 1
                status_key = (
                    str(result.response_code) if result.response_code is not None else "null"
                )
                response_status_counts[status_key] = response_status_counts.get(status_key, 0) + 1
                fetched_titled_count += sum(
                    1 for title in result.titles_by_paperid.values() if title is not None
                )
            status_summary = ", ".join(
                f"{status}={count:,}" for status, count in sorted(response_status_counts.items())
            )
            log_tag(
                STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
                "OpenAlex work-title command side: "
                f"fetched de novo={len(missing_paperids):,} paper IDs, "
                f"JSONL batch records appended={appended_log_record_count:,}, "
                f"batch HTTP statuses={status_summary or 'none'}, "
                f"new titles returned={fetched_titled_count:,}, "
                f"missing/null titles returned={len(missing_paperids) - fetched_titled_count:,}.",
            )
            new_log_resource = deepcopy(resources.openalex_paper_title_log_resource)
            updated_log_hash = write_openalex_paper_title_read_model(
                conn,
                openalex_paper_title_log_resource=new_log_resource,
                output_path=openalex_paper_title_parquet_path,
            )
            parquet_log_hash = openalex_paper_title_read_model_log_sha256(
                conn,
                openalex_paper_title_parquet_path,
            )
            log_tag(
                STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
                "OpenAlex work-title query side rebuilt after command append: "
                f"parquet={openalex_paper_title_parquet_path}; "
                f"parquet title-log sha256={parquet_log_hash or '<missing>'}; "
                f"current JSONL sha256={updated_log_hash}; "
                f"hash match={'yes' if parquet_log_hash == updated_log_hash else 'no'}.",
            )
        else:
            log_tag(
                STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
                "OpenAlex work-title command side: "
                "fetched de novo=0 paper IDs, JSONL batch records appended=0.",
            )

        conn.execute(
            f"""
            CREATE OR REPLACE TABLE {title_table} AS
            SELECT
                n.paperid AS paperid,
                t."{OPENALEX_TITLE_COL}" AS title
            FROM {needed_table} n
            LEFT JOIN read_parquet({title_parquet_sql}) t
              ON CAST(t."{SSNP_PAPERID_COL}" AS VARCHAR) = n.paperid
            """
        )
        title_counts = conn.execute(
            f"""
            SELECT
                COUNT(*) AS row_count,
                COUNT(*) FILTER (WHERE title IS NOT NULL) AS titled_count
            FROM {title_table}
            """
        ).fetchone()
        row_count = int(title_counts[0]) if title_counts else 0
        titled_count = int(title_counts[1]) if title_counts else 0
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
            "OpenAlex work-title table materialized from parquet: "
            f"{row_count:,} rows, {titled_count:,} with titles, "
            f"{row_count - titled_count:,} missing/null titles.",
        )

    def apply_openalex_confidence_gate() -> None:
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE {PARQUET_AUTHOR_MATCH_HIT_SELECTED_PRE_OPENALEX_TABLE} AS
            SELECT *
            FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}
            """
        )
        conn.execute(ssn_hit_openalex_check_table_sql(author_id_col=author_id_col))
        check_candidates = conn.execute(
            ssn_hit_openalex_check_candidates_sql(author_id_col=author_id_col)
        ).fetchall()
        if not check_candidates:
            log_tag(
                STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
                "SSN hit v2 OpenAlex confidence gate: no unique max-work "
                "multi-candidate selections to check.",
            )
            conn.execute(ssn_hit_openalex_selected_view_sql(author_id_col=author_id_col))
            return

        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
            "SSN hit v2 OpenAlex confidence gate: checking "
            f"{len(check_candidates):,} unique max-work selections against current OpenAlex.",
        )
        check_rows: list[tuple[str, str, str | None, bool, bool, int | None, int | None]] = []
        for name_key, first_name, last_name, selected_author_id in check_candidates:
            selected_author_id_str = str(selected_author_id)
            result = check_openalex_author(
                source_key=str(name_key),
                first_name=str(first_name or ""),
                last_name=str(last_name or ""),
                selected_author_id=selected_author_id_str,
                log_path=openalex_log_path,
            )
            check_rows.append(
                (
                    result.source_key,
                    selected_author_id_str,
                    result.top_author_id,
                    result.matched,
                    result.reused,
                    result.response_code,
                    result.received_at_unix_usec,
                )
            )
            source = "reused" if result.reused else "fetched"
            verdict = "match" if result.matched else "mismatch"
            status = result.response_code if result.response_code is not None else "null"
            top_author_id = result.top_author_id or "<none>"
            received_at = (
                result.received_at_unix_usec
                if result.received_at_unix_usec is not None
                else "null"
            )
            log_tag(
                STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
                "OpenAlex author check "
                f"{source}: name_key={name_key}, selected={selected_author_id_str}, "
                f"top={top_author_id}, status={status}, verdict={verdict}, "
                f"received_at_unix_usec={received_at}.",
            )
        conn.executemany(ssn_hit_openalex_check_insert_sql(author_id_col=author_id_col), check_rows)
        conn.execute(ssn_hit_openalex_selected_view_sql(author_id_col=author_id_col))
        openalex_counts = conn.execute(
            f"""
            SELECT
                COUNT(*) AS checked,
                COUNT(*) FILTER (WHERE "{KTP_OPENALEX_REUSED_COL}") AS reused,
                COUNT(*) FILTER (WHERE NOT "{KTP_OPENALEX_REUSED_COL}") AS fetched,
                COUNT(*) FILTER (WHERE "{KTP_OPENALEX_MATCH_COL}") AS matched,
                COUNT(*) FILTER (WHERE NOT "{KTP_OPENALEX_MATCH_COL}") AS failed
            FROM {PARQUET_AUTHOR_MATCH_OPENALEX_CHECK_TABLE}
            """
        ).fetchone()
        if openalex_counts is not None:
            log_tag(
                STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
                "SSN hit v2 OpenAlex confidence gate summary: "
                f"checked={int(openalex_counts[0] or 0):,}, "
                f"reused={int(openalex_counts[1] or 0):,}, "
                f"fetched={int(openalex_counts[2] or 0):,}, "
                f"matched={int(openalex_counts[3] or 0):,}, "
                f"failed={int(openalex_counts[4] or 0):,}.",
            )

    for legend_line in STEP_MATCH_PARQUET_LOG_LEGEND_LINES:
        log_tag(STEP_MATCH_PARQUET_LOG_TAG_LEGEND, legend_line)

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        f"Match author details to name keys ({KTP_AUTHOR_DETAILS_UNNEST_KEY} scan)",
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: author_details exact-name matching scans precomputed "
        "author-name keys and joins against all outerdict name keys. Display payloads "
        "are deferred until after nonzero-hit pruning.",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_MATCH_TABLE} AS
        WITH names AS (
            SELECT
                "{KTP_SOURCE_KEY_COL}" AS name_key,
                "{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                "{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
                {ktp_match_key_expr} AS match_key_norm
            FROM {OUTERDICT_NAME_VIEW}
        )
        SELECT DISTINCT
            n.name_key AS name_key,
            n."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
            n."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
            u."{SSNAD_AUTHORID_COL}" AS "{author_id_col}",
            json_object(
                '{KTP_SSN_MATCH_RULE_KEY}', '{ssn_match_rule}',
                '{KTP_SSNAD_MATCH_KTP_NAME_NORM_KEY}', n.match_key_norm,
                '{KTP_SSNAD_MATCH_SSNAD_NAME_NORM_KEY}', u."{KTP_ALT_NAME_COL}"
            ) AS "{KTP_SSNAD_MATCH_COL}"
        FROM names n
        JOIN read_parquet('{author_details_unnest_path}') u
          ON u."{KTP_ALT_NAME_COL}" = n.match_key_norm
        """
    )
    match_stats_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT name_key) AS name_key_count,
            COUNT(DISTINCT "{author_id_col}") AS author_count
        FROM {PARQUET_AUTHOR_MATCH_TABLE}
        """
    ).fetchone()
    parquet_author_match_rows = int(match_stats_row[0]) if match_stats_row else 0
    parquet_author_match_name_keys = int(match_stats_row[1]) if match_stats_row else 0
    parquet_author_match_authors = int(match_stats_row[2]) if match_stats_row else 0
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Matched author-details candidates: "
        f"{parquet_author_match_rows:,} rows, "
        f"{parquet_author_match_name_keys:,} name keys, "
        f"{parquet_author_match_authors:,} author IDs.",
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET, "Create author->paper table")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: author->paper expansion joins matched author rows to "
        "authors_paper parquet and can grow substantially.",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_PAPERS_TABLE} AS
        SELECT
            m.name_key AS name_key,
            m."{author_id_col}" AS authorid,
            pap.paperid AS paperid
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        JOIN read_parquet('{authors_paper_path}') pap
          ON pap.authorid = m."{author_id_col}"
        """
    )
    author_papers_stats_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT name_key || '|' || CAST(authorid AS VARCHAR)) AS pair_count,
            COUNT(DISTINCT paperid) AS paper_count
        FROM {PARQUET_AUTHOR_PAPERS_TABLE}
        """
    ).fetchone()
    author_papers_rows = int(author_papers_stats_row[0]) if author_papers_stats_row else 0
    author_papers_pair_count = int(author_papers_stats_row[1]) if author_papers_stats_row else 0
    author_papers_distinct_papers = (
        int(author_papers_stats_row[2]) if author_papers_stats_row else 0
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Author->paper rows: "
        f"{author_papers_rows:,} rows, "
        f"{author_papers_pair_count:,} name/author pairs, "
        f"{author_papers_distinct_papers:,} distinct papers.",
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF, "Create hits union table")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY step ahead: materializing hit tables union from 2 parquet files "
        f"filtered to author->paper distinct papers ({author_papers_distinct_papers:,}) "
        "for reuse in multiple downstream queries.",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_ALL_HITS_TABLE} AS
        WITH needed_papers AS (
            SELECT DISTINCT paperid
            FROM {PARQUET_AUTHOR_PAPERS_TABLE}
        )
        SELECT h.paperid, h.fieldid, h."Hit_1pct" AS hit_1pct, 'level0' AS level
        FROM read_parquet('{hit_papers0_path}') h
        JOIN needed_papers p
          ON p.paperid = h.paperid
        UNION ALL
        SELECT h.paperid, h.fieldid, h."Hit_1pct" AS hit_1pct, 'level1' AS level
        FROM read_parquet('{hit_papers1_path}') h
        JOIN needed_papers p
          ON p.paperid = h.paperid
        """
    )
    all_hits_stats_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT paperid) AS paper_count,
            COUNT(DISTINCT fieldid) AS field_count
        FROM {PARQUET_ALL_HITS_TABLE}
        """
    ).fetchone()
    all_hits_rows = int(all_hits_stats_row[0]) if all_hits_stats_row else 0
    all_hits_distinct_papers = int(all_hits_stats_row[1]) if all_hits_stats_row else 0
    all_hits_distinct_fields = int(all_hits_stats_row[2]) if all_hits_stats_row else 0
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "Hits union materialized: "
        f"{all_hits_rows:,} rows, "
        f"{all_hits_distinct_papers:,} papers, "
        f"{all_hits_distinct_fields:,} fields.",
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF, "Aggregate author-level hit stats")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY step ahead: aggregating hit stats over author->paper rows "
        f"({author_papers_rows:,}) joined to hits union rows ({all_hits_rows:,}).",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_HIT_AGG_TABLE} AS
        SELECT
            ap.name_key AS name_key,
            ap.authorid AS authorid,
            SUM(COALESCE(h.hit_1pct, 0)) AS "{KTP_SSN_SUM_HIT_1PCT_COL}"
        FROM {PARQUET_AUTHOR_PAPERS_TABLE} ap
        LEFT JOIN {PARQUET_ALL_HITS_TABLE} h
          ON ap.paperid = h.paperid
        GROUP BY ap.name_key, ap.authorid
        """
    )
    author_agg_stats_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(*) FILTER (WHERE "{KTP_SSN_SUM_HIT_1PCT_COL}" = 0) AS zero_hit_rows,
            COUNT(*) FILTER (WHERE "{KTP_SSN_SUM_HIT_1PCT_COL}" <> 0) AS nonzero_hit_rows,
            COUNT(*) FILTER (WHERE "{KTP_SSN_SUM_HIT_1PCT_COL}" IS NULL) AS null_hit_rows
        FROM {PARQUET_AUTHOR_HIT_AGG_TABLE}
        """
    ).fetchone()
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "Author hit aggregates: "
        f"{int(author_agg_stats_row[0]) if author_agg_stats_row else 0:,} rows "
        f"(zero={int(author_agg_stats_row[1]) if author_agg_stats_row else 0:,}, "
        f"nonzero={int(author_agg_stats_row[2]) if author_agg_stats_row else 0:,}, "
        f"null={int(author_agg_stats_row[3]) if author_agg_stats_row else 0:,}).",
    )

    removed_zero_hit_count_row = conn.execute(
        ssn_removed_zero_hit_count_sql(author_id_col=author_id_col)
    ).fetchone()
    removed_zero_hit_count = int(removed_zero_hit_count_row[0]) if removed_zero_hit_count_row else 0

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        "Create filtered parquet author-match view before downstream enrichment",
    )
    conn.execute(ssn_nonzero_hit_view_sql(author_id_col=author_id_col))
    nonzero_hit_stats_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT name_key) AS name_key_count,
            COUNT(DISTINCT "{author_id_col}") AS author_count
        FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW}
        """
    ).fetchone()
    nonzero_hit_rows = int(nonzero_hit_stats_row[0]) if nonzero_hit_stats_row else 0
    nonzero_hit_name_keys = int(nonzero_hit_stats_row[1]) if nonzero_hit_stats_row else 0
    nonzero_hit_authors = int(nonzero_hit_stats_row[2]) if nonzero_hit_stats_row else 0
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        "Nonzero-hit author-match filter: "
        f"kept {nonzero_hit_rows:,}/{parquet_author_match_rows:,} rows, "
        f"{nonzero_hit_name_keys:,} name keys, "
        f"{nonzero_hit_authors:,} author IDs; "
        f"removed zero-hit rows={removed_zero_hit_count:,}.",
    )

    if ssn_hit_rule_version == 2:
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
            "Create SSN hit v2 candidate metric table",
        )
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
            "HEAVY step ahead: joining nonzero-hit candidates to the narrow "
            "author_details metrics needed for Tukey hit selection.",
        )
        conn.execute(
            ssn_hit_v2_candidate_metrics_table_sql(
                author_details_path=author_details_path,
                author_id_col=author_id_col,
            )
        )
        bounds_row = conn.execute(ssn_hit_v2_bounds_summary_sql()).fetchone()
        if bounds_row is None:
            bounds_values = [0] * 5
        else:
            bounds_values = [int(value or 0) for value in bounds_row]
        (
            candidate_metric_rows,
            candidate_metric_name_keys,
            singleton_nonzero_metric_name_keys,
            missing_works_count_metric_rows,
            multi_missing_works_count_metric_name_keys,
        ) = bounds_values
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
            "SSN hit v2 per-name-key Tukey metrics: "
            f"candidate rows={candidate_metric_rows:,}, "
            f"name keys={candidate_metric_name_keys:,}, "
            f"singleton nonzero name keys={singleton_nonzero_metric_name_keys:,}, "
            f"missing works-count rows={missing_works_count_metric_rows:,}, "
            "multi-candidate missing works-count name keys="
            f"{multi_missing_works_count_metric_name_keys:,}.",
        )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        f"Create hit-selected author-match view (SSN hit rule v{ssn_hit_rule_version})",
    )
    conn.execute(
        ssn_hit_selected_view_sql(
            author_id_col=author_id_col,
            hit_rule_version=ssn_hit_rule_version,
        )
    )
    if ssn_hit_rule_version == 2:
        apply_openalex_confidence_gate()
    hit_selected_stats_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT name_key) AS name_key_count,
            COUNT(DISTINCT "{author_id_col}") AS author_count
        FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW}
        """
    ).fetchone()
    hit_selected_rows = int(hit_selected_stats_row[0]) if hit_selected_stats_row else 0
    hit_selected_name_keys = int(hit_selected_stats_row[1]) if hit_selected_stats_row else 0
    hit_selected_authors = int(hit_selected_stats_row[2]) if hit_selected_stats_row else 0
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        "Hit-selected author-match view: "
        f"kept {hit_selected_rows:,}/{nonzero_hit_rows:,} nonzero-hit rows, "
        f"{hit_selected_name_keys:,} name keys, "
        f"{hit_selected_authors:,} author IDs.",
    )

    if ssn_hit_rule_version == 2:
        breakdown_row = conn.execute(
            ssn_hit_v2_selection_breakdown_sql(author_id_col=author_id_col)
        ).fetchone()
        if breakdown_row is None:
            breakdown_values = [0] * 28
        else:
            breakdown_values = [int(value or 0) for value in breakdown_row]
        (
            candidate_rows,
            candidate_name_keys,
            candidate_authors,
            sum_hit_outlier_rows,
            works_count_outlier_rows,
            cited_by_count_outlier_rows,
            any_tukey_outlier_rows,
            name_keys_with_tukey_outlier,
            outlier_decision_pool_name_keys,
            full_nonzero_no_outlier_decision_pool_name_keys,
            singleton_nonzero_name_keys,
            missing_works_count_rows,
            multi_missing_works_count_name_keys,
            decision_pool_rows,
            decision_pool_name_keys,
            unique_max_work_winner_name_keys,
            max_work_tie_name_keys,
            selected_rows,
            selected_name_keys,
            selected_authors,
            selected_singleton_rows,
            selected_unique_max_work_rows,
            selected_multi_missing_works_count_rows,
            selected_max_work_tie_rows,
            pruned_unique_max_work_rows,
            one_selected_row_name_keys,
            multi_selected_row_name_keys,
            max_selected_rows_per_name_key,
        ) = breakdown_values
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
            "SSN hit v2 candidate flags: "
            f"candidate rows={candidate_rows:,}, "
            f"name keys={candidate_name_keys:,}, "
            f"author IDs={candidate_authors:,}; "
            f"any Tukey outlier rows={any_tukey_outlier_rows:,}, "
            f"sum-hit outlier rows={sum_hit_outlier_rows:,}, "
            f"works-count outlier rows={works_count_outlier_rows:,}, "
            f"cited-by-count outlier rows={cited_by_count_outlier_rows:,}.",
        )
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
            "SSN hit v2 name-key selection: "
            f"name keys with Tukey outliers={name_keys_with_tukey_outlier:,}, "
            f"outlier decision-pool name keys={outlier_decision_pool_name_keys:,}, "
            "full-nonzero/no-outlier decision-pool name keys="
            f"{full_nonzero_no_outlier_decision_pool_name_keys:,}, "
            f"singleton nonzero name keys={singleton_nonzero_name_keys:,}, "
            "multi-candidate missing works-count name keys="
            f"{multi_missing_works_count_name_keys:,}, "
            f"max-work tie name keys={max_work_tie_name_keys:,}; "
            f"selected rows={selected_rows:,}, "
            f"selected name keys={selected_name_keys:,}, "
            f"selected author IDs={selected_authors:,}.",
        )
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
            "SSN hit v2 row disposition: "
            f"decision-pool rows={decision_pool_rows:,}, "
            f"decision-pool name keys={decision_pool_name_keys:,}, "
            f"unique max-work winner name keys={unique_max_work_winner_name_keys:,}, "
            f"missing works-count rows={missing_works_count_rows:,}; "
            f"selected singleton rows={selected_singleton_rows:,}, "
            f"selected unique max-work rows={selected_unique_max_work_rows:,}, "
            "selected multi-candidate missing works-count rows="
            f"{selected_multi_missing_works_count_rows:,}, "
            f"selected max-work tie rows={selected_max_work_tie_rows:,}, "
            f"pruned by unique max-work={pruned_unique_max_work_rows:,}.",
        )
        log_tag(
            STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
            "SSN hit v2 selected-row multiplicity: "
            f"one-row name keys={one_selected_row_name_keys:,}, "
            f"multi-row/tied name keys={multi_selected_row_name_keys:,}, "
            f"max selected rows for one name key={max_selected_rows_per_name_key:,}.",
        )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        "Create distinct hit-selected author-id filter view",
    )
    conn.execute(ssn_hit_selected_author_ids_view_sql(author_id_col=author_id_col))
    nonzero_hit_author_ids_count = scalar_int(
        f'SELECT COUNT(*) FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW}'
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        f"Distinct hit-selected author IDs: {nonzero_hit_author_ids_count:,}.",
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "Create full author aggregate payload table (nonzero-hit subset only)",
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY step ahead: list-heavy author aggregation (paper lists + field IDs) "
        "restricted to hit-selected author matches after pruning.",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_AGG_TABLE} AS
        SELECT
            ap.name_key AS name_key,
            ap.authorid AS authorid,
            SUM(COALESCE(h.hit_1pct, 0)) AS "{KTP_SSN_SUM_HIT_1PCT_COL}",
            LIST(ap.paperid) FILTER (WHERE h.level = 'level0') AS "{SSN_PAPERIDS_LEVEL0_COL}",
            LIST(ap.paperid) FILTER (WHERE h.level = 'level1') AS "{SSN_PAPERIDS_LEVEL1_COL}",
            LIST(DISTINCT h.fieldid) AS "{SSN_FIELD_IDS_LIST_COL}"
        FROM {PARQUET_AUTHOR_PAPERS_TABLE} ap
        LEFT JOIN {PARQUET_ALL_HITS_TABLE} h
          ON ap.paperid = h.paperid
        WHERE EXISTS (
            SELECT 1
            FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
            WHERE m.name_key = ap.name_key
              AND CAST(m."{author_id_col}" AS VARCHAR) = CAST(ap.authorid AS VARCHAR)
        )
        GROUP BY ap.name_key, ap.authorid
        """
    )
    parquet_author_agg_payload_rows = scalar_int(f"SELECT COUNT(*) FROM {PARQUET_AUTHOR_AGG_TABLE}")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "Author aggregate payload rows (hit-selected subset): "
        f"{parquet_author_agg_payload_rows:,}.",
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET, "Create matched author_details table")
    author_table = f"ssn_{safe_identifier(Path(author_details_path).stem)}"
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: filtering author_details parquet by distinct hit-selected "
        f"author IDs ({nonzero_hit_author_ids_count:,}).",
    )
    _create_parquet_table(
        conn,
        table_name=author_table,
        path=author_details_path,
        prefix="ssnad",
        filename_col=KTP_SSNAD_FILENAME_COL,
        join_sql=(
            "JOIN "
            f"{PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW} ids "
            f"ON parq.{author_id_raw} = ids.\"{author_id_col}\""
        ),
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Matched author_details rows: "
        f"{scalar_int(f'SELECT COUNT(*) FROM {author_table}'):,}."
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET, "Create matched authors table")
    authors_table = f"ssn_{safe_identifier(Path(authors_path).stem)}"
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: filtering authors parquet by distinct hit-selected "
        f"author IDs ({nonzero_hit_author_ids_count:,}).",
    )
    _create_parquet_table(
        conn,
        table_name=authors_table,
        path=authors_path,
        prefix="ssnau",
        filename_col=KTP_SSNAU_FILENAME_COL,
        join_sql=(
            "JOIN "
            f"{PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW} ids "
            f"ON parq.{author_id_raw} = ids.\"{author_id_col}\""
        ),
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Matched authors rows: "
        f"{scalar_int(f'SELECT COUNT(*) FROM {authors_table}'):,}."
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Create matched paper-author-affiliation table",
    )
    paper_author_affiliation_table = (
        f"ssn_{safe_identifier(Path(paper_author_affiliation_path).stem)}"
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: filtering paper_author_affiliation parquet by distinct "
        f"hit-selected author IDs ({nonzero_hit_author_ids_count:,}); "
        "this can still be very large.",
    )
    _create_parquet_table(
        conn,
        table_name=paper_author_affiliation_table,
        path=paper_author_affiliation_path,
        prefix="ssnpaa",
        filename_col=KTP_SSNPAA_FILENAME_COL,
        join_sql=(
            "JOIN "
            f"{PARQUET_AUTHOR_MATCH_HIT_SELECTED_AUTHOR_IDS_VIEW} ids "
            f"ON parq.{SSNAD_RAW_AUTHORID_COL} = ids.\"{author_id_col}\""
        ),
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Matched paper-author-affiliation rows: "
        f"{scalar_int(f'SELECT COUNT(*) FROM {paper_author_affiliation_table}'):,}."
    )

    ssnpaa_institution_id_col = normalize_parquet_column_name("institutionid", "ssnpaa")
    ssnpaa_paper_id_col = normalize_parquet_column_name("paperid", "ssnpaa")
    ssnpaa_author_id_col = normalize_parquet_column_name(SSNAD_RAW_AUTHORID_COL, "ssnpaa")

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET, "Create matched affiliations table")
    affiliations_table = f"ssn_{safe_identifier(Path(affiliations_path).stem)}"
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: filtering affiliations parquet to institutions "
        "referenced by matched paper-author-affiliation rows.",
    )
    _create_parquet_table(
        conn,
        table_name=affiliations_table,
        path=affiliations_path,
        prefix="ssnaf",
        filename_col=KTP_SSNAF_FILENAME_COL,
        join_sql=(
            "JOIN ("
            f"SELECT DISTINCT CAST(\"{ssnpaa_institution_id_col}\" AS VARCHAR) AS institution_id "
            f"FROM {paper_author_affiliation_table} "
            f"WHERE \"{ssnpaa_institution_id_col}\" IS NOT NULL "
            f"AND trim(CAST(\"{ssnpaa_institution_id_col}\" AS VARCHAR)) <> ''"
            ") ids ON CAST(parq.institution_id AS VARCHAR) = ids.institution_id"
        ),
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Matched affiliations rows: "
        f"{scalar_int(f'SELECT COUNT(*) FROM {affiliations_table}'):,}."
    )

    ssnaf_institution_id_col = normalize_parquet_column_name("institution_id", "ssnaf")
    ssnaf_display_name_col = SSNAF_DISPLAY_NAME_COL

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET, "Create matched papers table")
    papers_columns = parquet_columns(conn, papers_path)
    papers_raw_paperid_col = _raw_column_for_normalized(
        papers_columns,
        prefix="ssnp",
        normalized_col=SSNP_PAPERID_COL,
    )
    _raw_column_for_normalized(
        papers_columns,
        prefix="ssnp",
        normalized_col=SSNP_DATE_COL,
    )
    papers_table = f"ssn_{safe_identifier(Path(papers_path).stem)}"
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: filtering papers parquet to papers referenced by "
        "hit-selected author rows.",
    )
    _create_parquet_table(
        conn,
        table_name=papers_table,
        path=papers_path,
        prefix="ssnp",
        filename_col=KTP_SSNP_FILENAME_COL,
        join_sql=(
            "JOIN ("
            "SELECT DISTINCT CAST(ap.paperid AS VARCHAR) AS paperid "
            f"FROM {PARQUET_AUTHOR_PAPERS_TABLE} ap "
            "WHERE ap.paperid IS NOT NULL "
            "AND EXISTS ("
            "SELECT 1 "
            f"FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m "
            "WHERE m.name_key = ap.name_key "
            f"AND CAST(m.\"{author_id_col}\" AS VARCHAR) = CAST(ap.authorid AS VARCHAR)"
            ")"
            f") ids ON CAST(parq.{duckdb_quote_identifier(papers_raw_paperid_col)} AS VARCHAR) "
            "= ids.paperid"
        ),
    )
    papers_stats_row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT "{SSNP_PAPERID_COL}") AS paper_count,
            COUNT(*) FILTER (
                WHERE TRY_CAST("{SSNP_DATE_COL}" AS DATE) IS NOT NULL
            ) AS dated_rows
        FROM {papers_table}
        """
    ).fetchone()
    papers_rows = int(papers_stats_row[0]) if papers_stats_row else 0
    papers_distinct = int(papers_stats_row[1]) if papers_stats_row else 0
    papers_dated_rows = int(papers_stats_row[2]) if papers_stats_row else 0
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Matched papers rows: "
        f"{papers_rows:,} rows, {papers_distinct:,} distinct papers, "
        f"{papers_dated_rows:,} dated rows.",
    )

    parquet_filenames = [
        parquet_filename(author_details_path),
        parquet_filename(authors_path),
        parquet_filename(authors_paper_path),
        parquet_filename(paper_author_affiliation_path),
        parquet_filename(affiliations_path),
        parquet_filename(hit_papers0_path),
        parquet_filename(hit_papers1_path),
        parquet_filename(fields_path),
        parquet_filename(papers_path),
    ]
    parquet_filename_payload = json.dumps(parquet_filenames)
    authors_paper_filename = parquet_filename(authors_paper_path)
    hit_papers0_filename = parquet_filename(hit_papers0_path)
    hit_papers1_filename = parquet_filename(hit_papers1_path)
    fields_filename = parquet_filename(fields_path)
    papers_filename = parquet_filename(papers_path)
    paper_author_affiliation_filename = parquet_filename(paper_author_affiliation_path)
    affiliations_filename = parquet_filename(affiliations_path)
    ssn_hit_metadata_select = ssn_hit_metadata_select_sql(
        hit_rule_version=ssn_hit_rule_version,
        table_alias="m",
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT, "Create author-level output table")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        "HEAVY step ahead: joining hit-selected author matches with matched author_details, "
        "matched authors, and author hit aggregates.",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_AUTHOR_OUTPUT_TABLE} AS
        SELECT
            m.name_key AS "{KTP_SOURCE_KEY_COL}",
            m."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
            m."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
            a."{author_id_col}" AS "{KTP_FRAGMENT_COL}",
            'author_id' AS "{KTP_FRAGMENT_TYPE_COL}",
            '{parquet_filename_payload}' AS "{KTP_FILENAME_COL}",
            m."{KTP_SSNAD_MATCH_COL}" AS "{KTP_SSNAD_MATCH_COL}"{ssn_hit_metadata_select},
            '{authors_paper_filename}' AS "{KTP_SSNAP_FILENAME_COL}",
            '{hit_papers0_filename}' AS "{KTP_SSNHPL0_FILENAME_COL}",
            '{hit_papers1_filename}' AS "{KTP_SSNHPL1_FILENAME_COL}",
            '{fields_filename}' AS "{KTP_SSNF_FILENAME_COL}",
            '{papers_filename}' AS "{KTP_SSNP_FILENAME_COL}",
            '{paper_author_affiliation_filename}' AS "{KTP_SSNPAA_FILENAME_COL}",
            '{affiliations_filename}' AS "{KTP_SSNAF_FILENAME_COL}",
            a.*,
            au.*,
            CAST(agg."{SSN_PAPERIDS_LEVEL0_COL}" AS VARCHAR) AS "{SSN_PAPERIDS_LEVEL0_COL}",
            CAST(agg."{SSN_PAPERIDS_LEVEL1_COL}" AS VARCHAR) AS "{SSN_PAPERIDS_LEVEL1_COL}",
            CAST(agg."{SSN_FIELD_IDS_LIST_COL}" AS VARCHAR) AS "{SSN_FIELD_IDS_LIST_COL}",
            agg."{KTP_SSN_SUM_HIT_1PCT_COL}"
        FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
        JOIN {author_table} a
          ON a."{author_id_col}" = m."{author_id_col}"
        JOIN {authors_table} au
          ON au."{authors_author_id_col}" = m."{author_id_col}"
        LEFT JOIN {PARQUET_AUTHOR_AGG_TABLE} agg
          ON agg.authorid = m."{author_id_col}"
         AND agg.name_key = m.name_key
        """
    )
    parquet_author_output_rows = scalar_int(f"SELECT COUNT(*) FROM {PARQUET_AUTHOR_OUTPUT_TABLE}")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        f"Author-level output rows: {parquet_author_output_rows:,}.",
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY diagnostic ahead: estimate top-paper reduction by scanning author->paper "
        "rows filtered to hit-selected matches.",
    )
    paper_reduction_row = conn.execute(
        f"""
        WITH paper_counts AS (
            SELECT
                name_key,
                authorid,
                COUNT(*) AS paper_count
            FROM {PARQUET_AUTHOR_PAPERS_TABLE} ap
            WHERE EXISTS (
                SELECT 1
                FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
                WHERE m.name_key = ap.name_key
                  AND CAST(m."{author_id_col}" AS VARCHAR) = CAST(ap.authorid AS VARCHAR)
            )
            GROUP BY name_key, authorid
        )
        SELECT
            COALESCE(SUM(paper_count), 0) AS total_papers,
            COALESCE(SUM(LEAST(paper_count, {TOP_K_WORKS})), 0) AS kept_papers
        FROM paper_counts
        """
    ).fetchone()
    total_papers = int(paper_reduction_row[0]) if paper_reduction_row else 0
    kept_papers = int(paper_reduction_row[1]) if paper_reduction_row else 0
    removed_papers = max(total_papers - kept_papers, 0)
    log(
        f"Top-{TOP_K_WORKS} paper reduction: kept {kept_papers} of {total_papers}, "
        f"removed {removed_papers}."
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY diagnostic ahead: estimate oldest-paper reduction by joining "
        "hit-selected author->paper rows to dated papers metadata.",
    )
    oldest_paper_reduction_row = conn.execute(
        f"""
        WITH dated_paper_counts AS (
            SELECT
                ap.name_key AS name_key,
                ap.authorid AS authorid,
                COUNT(DISTINCT CAST(ap.paperid AS VARCHAR)) AS paper_count
            FROM {PARQUET_AUTHOR_PAPERS_TABLE} ap
            JOIN {papers_table} p
              ON CAST(p."{SSNP_PAPERID_COL}" AS VARCHAR) = CAST(ap.paperid AS VARCHAR)
            WHERE ap.paperid IS NOT NULL
              AND TRY_CAST(p."{SSNP_DATE_COL}" AS DATE) IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
                  WHERE m.name_key = ap.name_key
                    AND CAST(m."{author_id_col}" AS VARCHAR) = CAST(ap.authorid AS VARCHAR)
              )
            GROUP BY ap.name_key, ap.authorid
        )
        SELECT
            COALESCE(SUM(paper_count), 0) AS dated_papers,
            COALESCE(SUM(LEAST(paper_count, {TOP_K_WORKS})), 0) AS kept_papers
        FROM dated_paper_counts
        """
    ).fetchone()
    oldest_total_papers = (
        int(oldest_paper_reduction_row[0]) if oldest_paper_reduction_row else 0
    )
    oldest_kept_papers = (
        int(oldest_paper_reduction_row[1]) if oldest_paper_reduction_row else 0
    )
    oldest_removed_papers = max(oldest_total_papers - oldest_kept_papers, 0)
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        f"Top-{TOP_K_WORKS} oldest-paper reduction: "
        f"kept {oldest_kept_papers} of {oldest_total_papers} dated papers, "
        f"removed {oldest_removed_papers}.",
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY diagnostic ahead: estimate top-institution reduction from matched "
        "paper-author-affiliation rows.",
    )
    institution_reduction_row = conn.execute(
        f"""
        WITH institution_counts AS (
            SELECT
                m.name_key AS name_key,
                m."{author_id_col}" AS authorid,
                CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR) AS institution_id,
                COUNT(DISTINCT paa."{ssnpaa_paper_id_col}") AS paper_count
            FROM {paper_author_affiliation_table} paa
            JOIN {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
              ON CAST(paa."{ssnpaa_author_id_col}" AS VARCHAR)
                = CAST(m."{author_id_col}" AS VARCHAR)
            WHERE paa."{ssnpaa_institution_id_col}" IS NOT NULL
              AND trim(CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR)) <> ''
            GROUP BY
                m.name_key,
                m."{author_id_col}",
                CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR)
        ),
        grouped AS (
            SELECT
                name_key,
                authorid,
                COUNT(*) AS institution_count
            FROM institution_counts
            GROUP BY name_key, authorid
        )
        SELECT
            COALESCE(SUM(institution_count), 0) AS total_institutions,
            COALESCE(SUM(LEAST(institution_count, {TOP_K_INSTITUTIONS})), 0)
                AS kept_institutions
        FROM grouped
        """
    ).fetchone()
    total_institutions = int(institution_reduction_row[0]) if institution_reduction_row else 0
    kept_institutions = int(institution_reduction_row[1]) if institution_reduction_row else 0
    removed_institutions = max(total_institutions - kept_institutions, 0)
    log(
        f"Top-{TOP_K_INSTITUTIONS} institution reduction: "
        f"kept {kept_institutions} of {total_institutions}, "
        f"removed {removed_institutions}."
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY diagnostic ahead: expand field-id lists and join fields parquet to "
        "measure display-name coverage.",
    )
    fields_match_row = conn.execute(
        f"""
        WITH field_lookup AS (
            SELECT
                CAST(fieldid AS VARCHAR) AS field_id,
                CAST(display_name AS VARCHAR) AS field_display_name
            FROM read_parquet('{fields_path}')
        ),
        expanded_ids AS (
            SELECT CAST(fid.field_id AS VARCHAR) AS field_id
            FROM {PARQUET_AUTHOR_AGG_TABLE} a
            JOIN {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
              ON a.name_key = m.name_key
             AND CAST(a.authorid AS VARCHAR) = CAST(m."{author_id_col}" AS VARCHAR)
            LEFT JOIN LATERAL UNNEST(a."{SSN_FIELD_IDS_LIST_COL}") AS fid(field_id) ON TRUE
        )
        SELECT
            COUNT(*) FILTER (WHERE e.field_id IS NOT NULL) AS total_field_ids,
            COUNT(*) FILTER (
                WHERE e.field_id IS NOT NULL
                  AND fl.field_display_name IS NOT NULL
            ) AS matched_field_ids
        FROM expanded_ids e
        LEFT JOIN field_lookup fl
          ON e.field_id = fl.field_id
        """
    ).fetchone()
    total_field_ids = int(fields_match_row[0]) if fields_match_row else 0
    matched_field_ids = int(fields_match_row[1]) if fields_match_row else 0
    unmatched_field_ids = max(total_field_ids - matched_field_ids, 0)
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "Fields display-name mapping: "
        f"matched {matched_field_ids}/{total_field_ids} IDs "
        f"(unmatched: {unmatched_field_ids}).",
    )

    openalex_work_title_table = "openalex_work_titles"
    materialize_openalex_work_titles(
        openalex_work_title_table,
        context.resources,
    )

    top_oldest_papers_ctes = _top_oldest_papers_ctes_sql(
        author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
        selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
        papers_table=papers_table,
        title_table=openalex_work_title_table,
        author_id_col=author_id_col,
        paperid_col=SSNP_PAPERID_COL,
        date_col=SSNP_DATE_COL,
        top_k_works=TOP_K_WORKS,
    )
    top_papers_hit_ctes = _top_papers_hit_ctes_sql(
        author_papers_table=PARQUET_AUTHOR_PAPERS_TABLE,
        all_hits_table=PARQUET_ALL_HITS_TABLE,
        selected_author_view=PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW,
        title_table=openalex_work_title_table,
        author_id_col=author_id_col,
        top_k_works=TOP_K_WORKS,
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        f"Create parquet enriched table (top-{TOP_K_WORKS} hit papers, "
        f"top-{TOP_K_WORKS} oldest papers, "
        f"top-{TOP_K_INSTITUTIONS} institutions, concept display names, selected hits)"
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        "HEAVY step ahead: builds final parquet innerdict rows with paper ranking, "
        "institution ranking, concept display mapping, and draw ordering.",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_INNERDICT_TABLE} AS
        WITH {top_papers_hit_ctes},
        {top_oldest_papers_ctes},
        affiliation_counts AS (
            SELECT
                m.name_key AS name_key,
                m."{author_id_col}" AS authorid,
                CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR) AS institution_id,
                COUNT(DISTINCT paa."{ssnpaa_paper_id_col}") AS paper_count,
                MAX(af."{ssnaf_display_name_col}") AS institution_display_name
            FROM {paper_author_affiliation_table} paa
            JOIN {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
              ON CAST(paa."{ssnpaa_author_id_col}" AS VARCHAR)
                = CAST(m."{author_id_col}" AS VARCHAR)
            LEFT JOIN {affiliations_table} af
              ON CAST(af."{ssnaf_institution_id_col}" AS VARCHAR)
                = CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR)
            WHERE paa."{ssnpaa_institution_id_col}" IS NOT NULL
              AND trim(CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR)) <> ''
            GROUP BY
                m.name_key,
                m."{author_id_col}",
                CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR)
        ),
        affiliation_ranked AS (
            SELECT
                ac.name_key AS name_key,
                ac.authorid AS authorid,
                ac.institution_id AS institution_id,
                ac.paper_count AS paper_count,
                ac.institution_display_name AS institution_display_name,
                ROW_NUMBER() OVER (
                    PARTITION BY ac.name_key, ac.authorid
                    ORDER BY ac.paper_count DESC, ac.institution_id
                ) AS rn
            FROM affiliation_counts ac
        ),
        top_institutions AS (
            SELECT
                ar.name_key AS name_key,
                ar.authorid AS authorid,
                CAST(
                    LIST(
                        json_object(
                            '{SSNPAA_INSTITUTION_ID_COL}',
                            'https://openalex.org/' || CAST(ar.institution_id AS VARCHAR),
                            '{SSNAF_DISPLAY_NAME_COL}',
                            COALESCE(
                                ar.institution_display_name,
                                CAST(ar.institution_id AS VARCHAR)
                            ),
                            '{KTP_SSN_COUNT_PAPERID_COL}',
                            ar.paper_count
                        )
                        ORDER BY ar.paper_count DESC, ar.institution_id
                    )
                        FILTER (WHERE ar.rn <= {TOP_K_INSTITUTIONS})
                    AS VARCHAR
                ) AS "{KTP_SSN_TOP_INSTITUTIONS_COL}"
            FROM affiliation_ranked ar
            GROUP BY ar.name_key, ar.authorid
        ),
        field_lookup AS (
            SELECT
                CAST(f.fieldid AS VARCHAR) AS field_id,
                CAST(f.display_name AS VARCHAR) AS field_display_name
            FROM read_parquet('{fields_path}') f
        ),
        concept_display AS (
            SELECT
                a.name_key AS name_key,
                a.authorid AS authorid,
                CAST(
                    LIST(
                        DISTINCT COALESCE(
                            fl.field_display_name,
                            CAST(fid.field_id AS VARCHAR)
                        )
                        ORDER BY COALESCE(
                            fl.field_display_name,
                            CAST(fid.field_id AS VARCHAR)
                        )
                    )
                    AS VARCHAR
                ) AS "{KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL}"
            FROM {PARQUET_AUTHOR_AGG_TABLE} a
            JOIN {PARQUET_AUTHOR_MATCH_HIT_SELECTED_VIEW} m
              ON a.name_key = m.name_key
             AND CAST(a.authorid AS VARCHAR) = CAST(m."{author_id_col}" AS VARCHAR)
            LEFT JOIN LATERAL UNNEST(a."{SSN_FIELD_IDS_LIST_COL}") AS fid(field_id) ON TRUE
            LEFT JOIN field_lookup fl
              ON CAST(fid.field_id AS VARCHAR) = fl.field_id
            GROUP BY a.name_key, a.authorid
        ),
        enriched AS (
            SELECT
                v."{KTP_SOURCE_KEY_COL}",
                v."{KTP_FILENAME_COL}",
                v."{KTP_FRAGMENT_COL}",
                v."{KTP_FRAGMENT_TYPE_COL}",
                v."{KTP_FIRST_NAME_COL}",
                v."{KTP_LAST_NAME_COL}",
                v."{KTP_SSNAD_MATCH_COL}",
                v.* EXCLUDE (
                    "{KTP_SOURCE_KEY_COL}",
                    "{KTP_FILENAME_COL}",
                    "{KTP_FRAGMENT_COL}",
                    "{KTP_FRAGMENT_TYPE_COL}",
                    "{KTP_FIRST_NAME_COL}",
                    "{KTP_LAST_NAME_COL}",
                    "{KTP_SSNAD_MATCH_COL}",
                    "{author_id_col}",
                    "{authors_author_id_col}",
                    "{SSN_FIELD_IDS_LIST_COL}",
                    "{SSN_PAPERIDS_LEVEL0_COL}",
                    "{SSN_PAPERIDS_LEVEL1_COL}"
                ),
                tp."{KTP_SSN_TOP_PAPERS_HIT_1PCT_COL}",
                top_old."{KTP_SSN_TOP_OLDEST_PAPERS_COL}",
                ti."{KTP_SSN_TOP_INSTITUTIONS_COL}",
                cd."{KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL}"
            FROM {PARQUET_AUTHOR_OUTPUT_TABLE} v
            LEFT JOIN top_papers tp
              ON tp.name_key = v."{KTP_SOURCE_KEY_COL}"
             AND CAST(tp.authorid AS VARCHAR) = CAST(v."{author_id_col}" AS VARCHAR)
            LEFT JOIN top_oldest_papers top_old
              ON top_old.name_key = v."{KTP_SOURCE_KEY_COL}"
             AND CAST(top_old.authorid AS VARCHAR) = CAST(v."{author_id_col}" AS VARCHAR)
            LEFT JOIN top_institutions ti
              ON ti.name_key = v."{KTP_SOURCE_KEY_COL}"
             AND CAST(ti.authorid AS VARCHAR) = CAST(v."{author_id_col}" AS VARCHAR)
            LEFT JOIN concept_display cd
              ON cd.name_key = v."{KTP_SOURCE_KEY_COL}"
             AND CAST(cd.authorid AS VARCHAR) = CAST(v."{author_id_col}" AS VARCHAR)
            WHERE v."{KTP_SSN_SUM_HIT_1PCT_COL}" IS NULL OR v."{KTP_SSN_SUM_HIT_1PCT_COL}" <> 0
        ),
        source_draw AS (
            SELECT
                x."{KTP_SOURCE_KEY_COL}" AS "{KTP_SOURCE_KEY_COL}",
                x."{DRAW_LABEL}" AS "{DRAW_LABEL}"
            FROM (
                SELECT
                    nk."{KTP_SOURCE_KEY_COL}" AS "{KTP_SOURCE_KEY_COL}",
                    s."{DRAW_LABEL}" AS "{DRAW_LABEL}",
                    ROW_NUMBER() OVER (
                        PARTITION BY nk."{KTP_SOURCE_KEY_COL}"
                        ORDER BY
                            CASE
                                WHEN starts_with(CAST(s."{DRAW_LABEL}" AS VARCHAR), 'pilot.') THEN 0
                                WHEN TRY_CAST(s."{DRAW_LABEL}" AS BIGINT) IS NOT NULL THEN 1
                                WHEN s."{DRAW_LABEL}" IS NULL
                                  OR trim(CAST(s."{DRAW_LABEL}" AS VARCHAR)) = '' THEN 3
                                ELSE 2
                            END,
                            COALESCE(
                                CASE
                                    WHEN starts_with(CAST(s."{DRAW_LABEL}" AS VARCHAR), 'pilot.')
                                        THEN TRY_CAST(
                                            split_part(CAST(s."{DRAW_LABEL}" AS VARCHAR), '.', 2)
                                            AS BIGINT
                                        )
                                    WHEN TRY_CAST(s."{DRAW_LABEL}" AS BIGINT) IS NOT NULL
                                        THEN CAST(s."{DRAW_LABEL}" AS BIGINT)
                                    ELSE NULL
                                END,
                                999999999
                            )
                    ) AS draw_rank
                FROM {OUTERDICT_NAME_VIEW} nk
                LEFT JOIN {SAMPLES_WITH_NAMES_VIEW} s
                  ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
                 AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
            ) x
            WHERE x.draw_rank = 1
        ),
        base AS (
            SELECT
                e.*,
                sd."{DRAW_LABEL}" AS "{DRAW_LABEL}"
            FROM enriched e
            LEFT JOIN source_draw sd
              ON sd."{KTP_SOURCE_KEY_COL}" = e."{KTP_SOURCE_KEY_COL}"
        ),
        {draw_sort_ctes_sql(draw_col=DRAW_LABEL, source_key_col=KTP_SOURCE_KEY_COL)}
        SELECT * EXCLUDE (
            row_draw_group, row_draw_num, source_draw_group, source_draw_num, "{DRAW_LABEL}"
        )
        FROM ranked
        ORDER BY
            {draw_sort_order_by_sql(
                source_key_col=KTP_SOURCE_KEY_COL,
                filename_col=KTP_FILENAME_COL,
                fragment_col=KTP_FRAGMENT_COL,
            )}
        """
    )
    parquet_innerdict_rows = scalar_int(f"SELECT COUNT(*) FROM {PARQUET_INNERDICT_TABLE}")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        f"Parquet enriched rows: {parquet_innerdict_rows:,}.",
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_OUTERDICT,
        f"Append parquet matches into OuterDict ({parquet_innerdict_rows:,} rows)",
    )
    append_innerdicts_from_rows_table(
        conn,
        table_name=PARQUET_INNERDICT_TABLE,
        outer_dict=context.outer_dict,
        procedure=ParquetMatchProcedure(),
        key_column=KTP_SOURCE_KEY_COL,
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT, "Create parquet output view")
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {PARQUET_OUTPUT_VIEW} AS
        WITH source_draw AS (
            SELECT
                x."{KTP_SOURCE_KEY_COL}" AS "{KTP_SOURCE_KEY_COL}",
                x."{DRAW_LABEL}" AS "{DRAW_LABEL}"
            FROM (
                SELECT
                    nk."{KTP_SOURCE_KEY_COL}" AS "{KTP_SOURCE_KEY_COL}",
                    s."{DRAW_LABEL}" AS "{DRAW_LABEL}",
                    ROW_NUMBER() OVER (
                        PARTITION BY nk."{KTP_SOURCE_KEY_COL}"
                        ORDER BY
                            CASE
                                WHEN starts_with(CAST(s."{DRAW_LABEL}" AS VARCHAR), 'pilot.') THEN 0
                                WHEN TRY_CAST(s."{DRAW_LABEL}" AS BIGINT) IS NOT NULL THEN 1
                                WHEN s."{DRAW_LABEL}" IS NULL
                                  OR trim(CAST(s."{DRAW_LABEL}" AS VARCHAR)) = '' THEN 3
                                ELSE 2
                            END,
                            COALESCE(
                                CASE
                                    WHEN starts_with(CAST(s."{DRAW_LABEL}" AS VARCHAR), 'pilot.')
                                        THEN TRY_CAST(
                                            split_part(CAST(s."{DRAW_LABEL}" AS VARCHAR), '.', 2)
                                            AS BIGINT
                                        )
                                    WHEN TRY_CAST(s."{DRAW_LABEL}" AS BIGINT) IS NOT NULL
                                        THEN CAST(s."{DRAW_LABEL}" AS BIGINT)
                                    ELSE NULL
                                END,
                                999999999
                            )
                    ) AS draw_rank
                FROM {OUTERDICT_NAME_VIEW} nk
                LEFT JOIN {SAMPLES_WITH_NAMES_VIEW} s
                  ON lower(nk."{KTP_FIRST_NAME_COL}") = lower(s."{KTP_FIRST_NAME_COL}")
                 AND lower(nk."{KTP_LAST_NAME_COL}") = lower(s."{KTP_LAST_NAME_COL}")
            ) x
            WHERE x.draw_rank = 1
        ),
        base AS (
            SELECT
                v.*,
                sd."{DRAW_LABEL}" AS "{DRAW_LABEL}"
            FROM {PARQUET_INNERDICT_TABLE} v
            LEFT JOIN source_draw sd
              ON sd."{KTP_SOURCE_KEY_COL}" = v."{KTP_SOURCE_KEY_COL}"
        ),
        {draw_sort_ctes_sql(draw_col=DRAW_LABEL, source_key_col=KTP_SOURCE_KEY_COL)}
        SELECT * EXCLUDE (
            row_draw_group, row_draw_num, source_draw_group, source_draw_num, "{DRAW_LABEL}"
        )
        FROM ranked
        ORDER BY
            {draw_sort_order_by_sql(
                source_key_col=KTP_SOURCE_KEY_COL,
                filename_col=KTP_FILENAME_COL,
                fragment_col=KTP_FRAGMENT_COL,
            )}
        """
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        "Filtered out parquet author-match rows before downstream enrichment with "
        f"{KTP_SSN_SUM_HIT_1PCT_COL} == 0: {removed_zero_hit_count:,}"
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT, "Load parquet output dataframe")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT,
        "HEAVY step ahead: executes output view and converts result to pandas dataframe.",
    )
    output_views = [PARQUET_OUTPUT_VIEW]
    output_dfs = [conn.execute(f"SELECT * FROM {view}").df() for view in output_views]
    matched_rows = sum(len(df) for df in output_dfs)
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_OUTPUT,
        f"Loaded parquet output dataframe rows: {matched_rows:,} "
        f"across {len(output_views)} view(s)."
    )

    return StepResult(
        step_id=STEP_MATCH_PARQUET,
        artifacts={"parquet_match_dfs": output_dfs, "parquet_view_names": output_views},
        messages=[
            f"Parquet views created: {len(output_dfs)}",
            f"Matched parquet rows: {matched_rows}",
        ],
        diagnostics=[
            f"Parquet match views: {len(output_dfs)}",
            f"Matched parquet rows: {matched_rows}",
        ],
    )
