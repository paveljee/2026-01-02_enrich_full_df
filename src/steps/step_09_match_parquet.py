from __future__ import annotations

import json
from pathlib import Path

import duckdb

from ..helpers.context import PipelineContext, StepResult
from ..helpers.duckdb_utils import append_innerdicts_from_rows_table
from ..helpers.name_matching import (
    sciscinet_author_name_norm_sql,
    sciscinet_ktp_name_norm_sql,
)
from ..helpers.parquet_utils import normalize_parquet_column_name, parquet_columns, parquet_filename
from ..helpers.procedures import ParquetMatchProcedure
from ..helpers.schema import (
    OUTERDICT_NAME_VIEW,
    PARQUET_ALL_HITS_TABLE,
    PARQUET_AUTHOR_AGG_TABLE,
    PARQUET_AUTHOR_HIT_AGG_TABLE,
    PARQUET_AUTHOR_MATCH_NONZERO_HIT_AUTHOR_IDS_VIEW,
    PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW,
    PARQUET_AUTHOR_MATCH_TABLE,
    PARQUET_AUTHOR_OUTPUT_TABLE,
    PARQUET_AUTHOR_PAPERS_TABLE,
    PARQUET_INNERDICT_TABLE,
    PARQUET_OUTPUT_VIEW,
    SAMPLES_WITH_NAMES_VIEW,
    safe_identifier,
)
from ..helpers.vars import (
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_LAST_NAME_COL,
    KTP_SOURCE_KEY_COL,
    KTP_SSN_COUNT_PAPERID_COL,
    KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
    KTP_SSN_SUM_HIT_1PCT_COL,
    KTP_SSN_TOP_INSTITUTIONS_COL,
    KTP_SSN_TOP_PAPERS_HIT_1PCT_COL,
    KTP_SSNAD_MATCH_COL,
    KTP_SSNAD_MATCH_KTP_NAME_NORM_KEY,
    KTP_SSNAD_MATCH_SSNAD_NAME_NORM_KEY,
    SSN_FIELD_IDS_LIST_COL,
    SSN_PAPERIDS_LEVEL0_COL,
    SSN_PAPERIDS_LEVEL1_COL,
    SSNAD_FILENAME_COL,
    SSNAF_DISPLAY_NAME_COL,
    SSNAF_FILENAME_COL,
    SSNAP_FILENAME_COL,
    SSNAU_FILENAME_COL,
    SSNF_FILENAME_COL,
    SSNHPL0_FILENAME_COL,
    SSNHPL1_FILENAME_COL,
    SSNPAA_FILENAME_COL,
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

    author_id_col = normalize_parquet_column_name("authorid", "ssnad")
    authors_author_id_col = normalize_parquet_column_name("authorid", "ssnau")
    author_id_raw = "authorid"
    strip_sciscinet_tokens = context.config.sciscinet_match_strip_tokens
    ktp_match_key_expr = sciscinet_ktp_name_norm_sql(
        f'"{KTP_FIRST_NAME_COL}"',
        f'"{KTP_LAST_NAME_COL}"',
        strip_tokens=strip_sciscinet_tokens,
    )
    ssnad_alt_name_expr = sciscinet_author_name_norm_sql(
        "p.alt_name",
        strip_tokens=strip_sciscinet_tokens,
    )

    def scalar_int(sql: str) -> int:
        row = conn.execute(sql).fetchone()
        if row is None or row[0] is None:
            return 0
        return int(row[0])

    for legend_line in STEP_MATCH_PARQUET_LOG_LEGEND_LINES:
        log_tag(STEP_MATCH_PARQUET_LOG_TAG_LEGEND, legend_line)

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Match author details to name keys (author_details scan)",
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: author_details exact-name matching scans author_details "
        "(display_name + alternatives) and joins against all outerdict name keys.",
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
        ),
        parq AS (
            SELECT
                authorid,
                display_name,
                display_name_alternatives,
                unnest(CAST(json(display_name_alternatives) AS VARCHAR[])) AS alt_name
            FROM read_parquet('{author_details_path}')
            UNION ALL
            SELECT
                authorid,
                display_name,
                display_name_alternatives,
                display_name AS alt_name
            FROM read_parquet('{author_details_path}')
        )
        SELECT DISTINCT
            n.name_key AS name_key,
            n."{KTP_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
            n."{KTP_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}",
            p.authorid AS "{author_id_col}",
            p.display_name AS "ssnad.display_name",
            p.display_name_alternatives AS "ssnad.display_name_alternatives",
            json_object(
                '{KTP_SSNAD_MATCH_KTP_NAME_NORM_KEY}', n.match_key_norm,
                '{KTP_SSNAD_MATCH_SSNAD_NAME_NORM_KEY}', {ssnad_alt_name_expr}
            ) AS "{KTP_SSNAD_MATCH_COL}"
        FROM names n
        JOIN parq p
          ON {ssnad_alt_name_expr} = n.match_key_norm
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
        f"""
        SELECT COUNT(*)
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        LEFT JOIN {PARQUET_AUTHOR_HIT_AGG_TABLE} agg
          ON agg.authorid = m."{author_id_col}"
         AND agg.name_key = m.name_key
        WHERE agg."{KTP_SSN_SUM_HIT_1PCT_COL}" = 0
        """
    ).fetchone()
    removed_zero_hit_count = int(removed_zero_hit_count_row[0]) if removed_zero_hit_count_row else 0

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        "Create filtered parquet author-match view before downstream enrichment",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} AS
        SELECT m.*
        FROM {PARQUET_AUTHOR_MATCH_TABLE} m
        LEFT JOIN {PARQUET_AUTHOR_HIT_AGG_TABLE} agg
          ON agg.authorid = m."{author_id_col}"
         AND agg.name_key = m.name_key
        WHERE agg."{KTP_SSN_SUM_HIT_1PCT_COL}" IS NULL
           OR agg."{KTP_SSN_SUM_HIT_1PCT_COL}" <> 0
        """
    )
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

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        "Create distinct nonzero-hit author-id filter view",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {PARQUET_AUTHOR_MATCH_NONZERO_HIT_AUTHOR_IDS_VIEW} AS
        SELECT DISTINCT
            m."{author_id_col}" AS "{author_id_col}"
        FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
        """
    )
    nonzero_hit_author_ids_count = scalar_int(
        f'SELECT COUNT(*) FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_AUTHOR_IDS_VIEW}'
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_VIEW_FILTER,
        f"Distinct nonzero-hit author IDs: {nonzero_hit_author_ids_count:,}.",
    )

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "Create full author aggregate payload table (nonzero-hit subset only)",
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "HEAVY step ahead: list-heavy author aggregation (paper lists + field IDs) "
        "restricted to nonzero-hit author matches after pruning.",
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
            FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
            WHERE m.name_key = ap.name_key
              AND CAST(m."{author_id_col}" AS VARCHAR) = CAST(ap.authorid AS VARCHAR)
        )
        GROUP BY ap.name_key, ap.authorid
        """
    )
    parquet_author_agg_payload_rows = scalar_int(f"SELECT COUNT(*) FROM {PARQUET_AUTHOR_AGG_TABLE}")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_EFF,
        "Author aggregate payload rows (nonzero-hit subset): "
        f"{parquet_author_agg_payload_rows:,}.",
    )

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET, "Create matched author_details table")
    author_table = f"ssn_{safe_identifier(Path(author_details_path).stem)}"
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "HEAVY step ahead: filtering author_details parquet by distinct nonzero-hit "
        f"author IDs ({nonzero_hit_author_ids_count:,}).",
    )
    _create_parquet_table(
        conn,
        table_name=author_table,
        path=author_details_path,
        prefix="ssnad",
        filename_col=SSNAD_FILENAME_COL,
        join_sql=(
            "JOIN "
            f"{PARQUET_AUTHOR_MATCH_NONZERO_HIT_AUTHOR_IDS_VIEW} ids "
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
        "HEAVY step ahead: filtering authors parquet by distinct nonzero-hit "
        f"author IDs ({nonzero_hit_author_ids_count:,}).",
    )
    _create_parquet_table(
        conn,
        table_name=authors_table,
        path=authors_path,
        prefix="ssnau",
        filename_col=SSNAU_FILENAME_COL,
        join_sql=(
            "JOIN "
            f"{PARQUET_AUTHOR_MATCH_NONZERO_HIT_AUTHOR_IDS_VIEW} ids "
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
        f"nonzero-hit author IDs ({nonzero_hit_author_ids_count:,}); this can still be very large.",
    )
    _create_parquet_table(
        conn,
        table_name=paper_author_affiliation_table,
        path=paper_author_affiliation_path,
        prefix="ssnpaa",
        filename_col=SSNPAA_FILENAME_COL,
        join_sql=(
            "JOIN "
            f"{PARQUET_AUTHOR_MATCH_NONZERO_HIT_AUTHOR_IDS_VIEW} ids "
            f"ON parq.authorid = ids.\"{author_id_col}\""
        ),
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_PARQUET,
        "Matched paper-author-affiliation rows: "
        f"{scalar_int(f'SELECT COUNT(*) FROM {paper_author_affiliation_table}'):,}."
    )

    ssnpaa_institution_id_col = normalize_parquet_column_name("institutionid", "ssnpaa")
    ssnpaa_paper_id_col = normalize_parquet_column_name("paperid", "ssnpaa")
    ssnpaa_author_id_col = normalize_parquet_column_name("authorid", "ssnpaa")

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
        filename_col=SSNAF_FILENAME_COL,
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

    parquet_filenames = [
        parquet_filename(author_details_path),
        parquet_filename(authors_path),
        parquet_filename(authors_paper_path),
        parquet_filename(paper_author_affiliation_path),
        parquet_filename(affiliations_path),
        parquet_filename(hit_papers0_path),
        parquet_filename(hit_papers1_path),
        parquet_filename(fields_path),
    ]
    parquet_filename_payload = json.dumps(parquet_filenames)
    authors_paper_filename = parquet_filename(authors_paper_path)
    hit_papers0_filename = parquet_filename(hit_papers0_path)
    hit_papers1_filename = parquet_filename(hit_papers1_path)
    fields_filename = parquet_filename(fields_path)
    paper_author_affiliation_filename = parquet_filename(paper_author_affiliation_path)
    affiliations_filename = parquet_filename(affiliations_path)

    log_tag(STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT, "Create author-level output table")
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        "HEAVY step ahead: joining nonzero-hit author matches with matched author_details, "
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
            m."{KTP_SSNAD_MATCH_COL}" AS "{KTP_SSNAD_MATCH_COL}",
            '{authors_paper_filename}' AS "{SSNAP_FILENAME_COL}",
            '{hit_papers0_filename}' AS "{SSNHPL0_FILENAME_COL}",
            '{hit_papers1_filename}' AS "{SSNHPL1_FILENAME_COL}",
            '{fields_filename}' AS "{SSNF_FILENAME_COL}",
            '{paper_author_affiliation_filename}' AS "{SSNPAA_FILENAME_COL}",
            '{affiliations_filename}' AS "{SSNAF_FILENAME_COL}",
            a.*,
            au.*,
            CAST(agg."{SSN_PAPERIDS_LEVEL0_COL}" AS VARCHAR) AS "{SSN_PAPERIDS_LEVEL0_COL}",
            CAST(agg."{SSN_PAPERIDS_LEVEL1_COL}" AS VARCHAR) AS "{SSN_PAPERIDS_LEVEL1_COL}",
            CAST(agg."{SSN_FIELD_IDS_LIST_COL}" AS VARCHAR) AS "{SSN_FIELD_IDS_LIST_COL}",
            agg."{KTP_SSN_SUM_HIT_1PCT_COL}"
        FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
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
        "rows filtered to nonzero-hit matches.",
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
                FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
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
            JOIN {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
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
            JOIN {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
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

    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        f"Create parquet enriched table (top-{TOP_K_WORKS} papers, "
        f"top-{TOP_K_INSTITUTIONS} institutions, concept display names, nonzero hits)"
    )
    log_tag(
        STEP_MATCH_PARQUET_LOG_TAG_TABLE_INNERDICT,
        "HEAVY step ahead: builds final parquet innerdict rows with paper ranking, "
        "institution ranking, concept display mapping, and draw ordering.",
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {PARQUET_INNERDICT_TABLE} AS
        WITH paper_hits AS (
            SELECT
                ap.name_key AS name_key,
                ap.authorid AS authorid,
                ap.paperid AS paperid,
                COALESCE(MAX(h.hit_1pct), 0) AS hit_1pct
            FROM {PARQUET_AUTHOR_PAPERS_TABLE} ap
            LEFT JOIN {PARQUET_ALL_HITS_TABLE} h
              ON ap.paperid = h.paperid
            WHERE EXISTS (
                SELECT 1
                FROM {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
                WHERE m.name_key = ap.name_key
                  AND CAST(m."{author_id_col}" AS VARCHAR) = CAST(ap.authorid AS VARCHAR)
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
                    ORDER BY ph.hit_1pct DESC, ph.paperid
                ) AS rn
            FROM paper_hits ph
        ),
        top_papers AS (
            SELECT
                pr.name_key AS name_key,
                pr.authorid AS authorid,
                CAST(
                    LIST(
                        'https://openalex.org/' || CAST(pr.paperid AS VARCHAR)
                        ORDER BY pr.hit_1pct DESC, pr.paperid
                    )
                        FILTER (WHERE pr.rn <= {TOP_K_WORKS})
                    AS VARCHAR
                ) AS "{KTP_SSN_TOP_PAPERS_HIT_1PCT_COL}"
            FROM paper_ranked pr
            GROUP BY pr.name_key, pr.authorid
        ),
        affiliation_counts AS (
            SELECT
                m.name_key AS name_key,
                m."{author_id_col}" AS authorid,
                CAST(paa."{ssnpaa_institution_id_col}" AS VARCHAR) AS institution_id,
                COUNT(DISTINCT paa."{ssnpaa_paper_id_col}") AS paper_count,
                MAX(af."{ssnaf_display_name_col}") AS institution_display_name
            FROM {paper_author_affiliation_table} paa
            JOIN {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
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
            JOIN {PARQUET_AUTHOR_MATCH_NONZERO_HIT_VIEW} m
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
                ti."{KTP_SSN_TOP_INSTITUTIONS_COL}",
                cd."{KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL}"
            FROM {PARQUET_AUTHOR_OUTPUT_TABLE} v
            LEFT JOIN top_papers tp
              ON tp.name_key = v."{KTP_SOURCE_KEY_COL}"
             AND CAST(tp.authorid AS VARCHAR) = CAST(v."{author_id_col}" AS VARCHAR)
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
