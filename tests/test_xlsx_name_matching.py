from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.helpers.config import MatchRuleVersion, PipelineConfig
from src.helpers.context import PipelineContext
from src.helpers.data_models import FragmentType, InnerDict, NameKey, OuterDict, ResourceGroup
from src.helpers.diagnostics import DiagnosticsReport
from src.helpers.duckdb_extensions import load_duckdb_extension_from_config_path
from src.helpers.name_matching import xlsx_match_sql
from src.helpers.pipeline_manager import PipelineManager
from src.helpers.procedures import ParquetMatchProcedure
from src.helpers.resources import PipelineResources, register_resource
from src.helpers.schema import (
    OUTERDICT_NAME_VIEW,
    POPULATION_ECON_TABLE,
    POPULATION_NAMES_TABLE,
    POPULATION_TABLE,
    REGISTERED_RESOURCES_TABLE,
    SAMPLES_TABLE,
    XLSX_MATCH_VIEW,
)
from src.helpers.vars import (
    DRAW_LABEL,
    HCR_FIRST_NAME_COL,
    HCR_LAST_NAME_COL,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_HCR_FILENAME_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_ROW_NUMBER_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_POPULATION_INDEX_COL,
    KTP_PRIORITY_COL,
    KTP_PRIORITY_GROUP_COL,
    KTP_SSNAD_FILENAME_COL,
    KTP_XLSX_MATCH_RULE_KEY,
    KTP_XLSX_MATCH_RULE_V1,
    KTP_XLSX_MATCH_RULE_V2,
    REQUIRED_FILES_CONFIG_KEYS,
)
from src.steps import step_07_match_xlsx, step_10_build_cards
from src.steps.step_02_load_xlsx import _build_population_table


def _connect() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    load_duckdb_extension_from_config_path(conn, "splink_udfs")
    return conn


def _matches(
    *,
    use_v2: bool,
    source_first: str,
    source_last: str,
    target_first: str,
    target_last: str,
) -> bool:
    conn = _connect()
    match_sql = xlsx_match_sql(
        use_v2=use_v2,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
    )
    row = conn.execute(
        f"""
        WITH source_input(first_name, last_name) AS (VALUES (?, ?)),
        target_input(first_name, last_name) AS (VALUES (?, ?)),
        name_draws AS (
            SELECT
                nk.first_name,
                nk.last_name,
                {match_sql.name_draws_fields}
            FROM source_input nk
        ),
        pop_names AS (
            SELECT
                n.first_name AS pop_first,
                n.last_name AS pop_last,
                {match_sql.pop_names_fields}
                1 AS sentinel
            FROM target_input n
        ){match_sql.extra_ctes}
        SELECT COALESCE(bool_or({match_sql.condition}), FALSE) AS matched
        FROM {match_sql.name_draws_relation} nd
        CROSS JOIN {match_sql.pop_names_relation} p
        """,
        [source_first, source_last, target_first, target_last],
    ).fetchone()
    assert row is not None
    return bool(row[0])


def _matched_rules(
    *,
    source_first: str,
    source_last: str,
    target_first: str,
    target_last: str,
) -> list[str]:
    conn = _connect()
    match_sql = xlsx_match_sql(
        use_v2=True,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
        rule_v1=KTP_XLSX_MATCH_RULE_V1,
    )
    return [
        str(row[0])
        for row in conn.execute(
            f"""
            WITH source_input(first_name, last_name) AS (VALUES (?, ?)),
            target_input(first_name, last_name) AS (VALUES (?, ?)),
            name_draws AS (
                SELECT
                    nk.first_name,
                    nk.last_name,
                    {match_sql.name_draws_fields}
                FROM source_input nk
            ),
            pop_names AS (
                SELECT
                    n.first_name AS pop_first,
                    n.last_name AS pop_last,
                    {match_sql.pop_names_fields}
                    1 AS sentinel
                FROM target_input n
            ){match_sql.extra_ctes}
            SELECT DISTINCT nd.nd_xlsx_match_rule
            FROM {match_sql.name_draws_relation} nd
            CROSS JOIN {match_sql.pop_names_relation} p
            WHERE {match_sql.condition}
            ORDER BY nd.nd_xlsx_match_rule
            """,
            [source_first, source_last, target_first, target_last],
        ).fetchall()
    ]


def _preferred_matched_rules(
    *,
    source_first: str,
    source_last: str,
    target_first: str,
    target_last: str,
) -> list[str]:
    conn = _connect()
    match_sql = xlsx_match_sql(
        use_v2=True,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
        rule_v1=KTP_XLSX_MATCH_RULE_V1,
    )
    return [
        str(row[0])
        for row in conn.execute(
            f"""
            WITH source_input(first_name, last_name) AS (VALUES (?, ?)),
            target_input(first_name, last_name) AS (VALUES (?, ?)),
            name_draws AS (
                SELECT
                    'source' AS "ktp.source_key",
                    nk.first_name,
                    nk.last_name,
                    {match_sql.name_draws_fields}
                FROM source_input nk
            ),
            pop_names AS (
                SELECT
                    'hcr.xlsx' AS "ktp.hcr_filename",
                    1 AS "ktp.hcr_row_number",
                    n.first_name AS pop_first,
                    n.last_name AS pop_last,
                    {match_sql.pop_names_fields}
                    1 AS sentinel
                FROM target_input n
            ){match_sql.extra_ctes}
            , base_candidates AS (
                SELECT DISTINCT
                    'source' AS "ktp.source_key",
                    'hcr.xlsx' AS "ktp.filename",
                    1 AS "ktp.fragment",
                    nd.nd_xlsx_match_rule,
                    {match_sql.match_path_priority_expr} AS xlsx_match_path_priority
                FROM {match_sql.name_draws_relation} nd
                CROSS JOIN {match_sql.pop_names_relation} p
                WHERE {match_sql.condition}
            ),
            base_min_priority AS (
                SELECT
                    "ktp.source_key",
                    "ktp.filename",
                    "ktp.fragment",
                    MIN(xlsx_match_path_priority) AS xlsx_match_path_priority
                FROM base_candidates
                GROUP BY "ktp.source_key", "ktp.filename", "ktp.fragment"
            )
            SELECT bc.nd_xlsx_match_rule
            FROM base_candidates bc
            JOIN base_min_priority bp
              ON bc."ktp.source_key" = bp."ktp.source_key"
             AND bc."ktp.filename" = bp."ktp.filename"
             AND bc."ktp.fragment" = bp."ktp.fragment"
             AND bc.xlsx_match_path_priority = bp.xlsx_match_path_priority
            ORDER BY bc.nd_xlsx_match_rule
            """,
            [source_first, source_last, target_first, target_last],
        ).fetchall()
    ]


def test_v2_join_condition_is_key_equality_not_pairwise_recursive_sql() -> None:
    match_sql = xlsx_match_sql(
        use_v2=True,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
    )

    assert match_sql.condition == (
        "nd.nd_xlsx_match_rule = p.pop_xlsx_match_rule "
        "AND nd.nd_first_match_key = p.pop_first_match_key "
        "AND nd.nd_last_match_key = p.pop_last_match_key"
    )
    assert match_sql.name_draws_relation == "name_draw_keys"
    assert match_sql.pop_names_relation == "pop_name_keys"
    assert match_sql.base_select_keyword == "SELECT DISTINCT"
    assert match_sql.match_path_priority_expr == "nd.nd_xlsx_match_priority"


def test_v1_payload_includes_rule_version() -> None:
    match_sql = xlsx_match_sql(
        use_v2=False,
        source_first_expr="nk.first_name",
        source_last_expr="nk.last_name",
        target_first_expr="n.first_name",
        target_last_expr="n.last_name",
        rule_key=KTP_XLSX_MATCH_RULE_KEY,
        rule_v2=KTP_XLSX_MATCH_RULE_V2,
        rule_v1=KTP_XLSX_MATCH_RULE_V1,
    )
    row = _connect().execute(
        f"""
        SELECT json_object(
            {match_sql.rule_payload_entry}
            'sentinel', 'ok'
        )
        """
    ).fetchone()
    assert row is not None
    payload = json.loads(row[0])

    assert payload[KTP_XLSX_MATCH_RULE_KEY] == KTP_XLSX_MATCH_RULE_V1


def test_v1_preserves_original_first_token_contains_and_unaccent_behavior() -> None:
    assert _matches(
        use_v2=False,
        source_first="John R",
        source_last="Smith",
        target_first="R John",
        target_last="Smith",
    )
    assert _matches(
        use_v2=False,
        source_first="Jose",
        source_last="Garcia",
        target_first="Jose Maria",
        target_last="Garcia",
    )
    assert _matches(
        use_v2=False,
        source_first="José",
        source_last="García",
        target_first="Jose",
        target_last="Garcia",
    )


def test_v1_does_not_get_v2_punctuation_or_last_token_matching() -> None:
    assert not _matches(
        use_v2=False,
        source_first="John-R",
        source_last="Smith Jones",
        target_first="John R",
        target_last="Smith-Jones",
    )


def test_v2_includes_original_v1_candidate_as_v1_rule() -> None:
    assert _matches(
        use_v2=True,
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano Nunes",
        target_last="Nunes-Nesi",
    )
    assert _matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano Nunes",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V1]
    assert _preferred_matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano Nunes",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V1]


def test_v2_preferred_when_candidate_also_matches_original_v1_rule() -> None:
    assert _matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V1, KTP_XLSX_MATCH_RULE_V2]
    assert _preferred_matched_rules(
        source_first="Adriano",
        source_last="Nunes-Nesi",
        target_first="Adriano",
        target_last="Nunes-Nesi",
    ) == [KTP_XLSX_MATCH_RULE_V2]


def test_v2_normalizes_punctuation_and_requires_sequence_order() -> None:
    assert KTP_XLSX_MATCH_RULE_V2 in _matched_rules(
        source_first="John-R",
        source_last="Smith Jones",
        target_first="John R",
        target_last="Smith-Jones",
    )
    assert _matched_rules(
        source_first="R John",
        source_last="Smith",
        target_first="John R",
        target_last="Smith",
    ) == [KTP_XLSX_MATCH_RULE_V1]


@pytest.mark.parametrize(
    ("source_first", "target_first", "expected"),
    [
        ("John RB", "John R B", True),
        ("John R B", "John RB", True),
        ("RB John", "John R B", False),
        ("John RB", "John R B James", False),
    ],
)
def test_v2_compact_initials_rule_for_first_names(
    source_first: str,
    target_first: str,
    expected: bool,
) -> None:
    rules = _matched_rules(
        source_first=source_first,
        source_last="Smith",
        target_first=target_first,
        target_last="Smith",
    )
    assert (KTP_XLSX_MATCH_RULE_V2 in rules) is expected


@pytest.mark.parametrize(
    ("source_first", "target_first", "expected"),
    [
        ("Abdul Latif M", "Abdul L M", True),
        ("L Abdul", "Abdul Latif", False),
        ("Abdul Latif Merem", "Abdul L", False),
    ],
)
def test_v2_initial_expansion_rule_for_first_names(
    source_first: str,
    target_first: str,
    expected: bool,
) -> None:
    rules = _matched_rules(
        source_first=source_first,
        source_last="Khan",
        target_first=target_first,
        target_last="Khan",
    )
    assert (KTP_XLSX_MATCH_RULE_V2 in rules) is expected


def test_v2_fallback_rules_apply_to_last_names() -> None:
    assert _matches(
        use_v2=True,
        source_first="John",
        source_last="Smith RB",
        target_first="John",
        target_last="Smith R B",
    )
    assert not _matches(
        use_v2=True,
        source_first="John",
        source_last="RB Smith",
        target_first="John",
        target_last="Smith R B",
    )


@pytest.mark.parametrize(
    ("first_names", "expected_match_count", "expected_filenames"),
    [
        (("A.B", "AB"), 4, {"7_8_AB_Lee_1", "7_8_AB_Lee_2"}),
        (("JinRong", "JinRong "), 4, {"7_8_JinRong_Lee_1", "7_8_JinRong_Lee_2"}),
        (("Anne-Marie", "AnneMarie"), 2, {"7_AnneMarie_Lee", "8_AnneMarie_Lee"}),
    ],
)
def test_xlsx_matches_keep_distinct_namekeys_when_filenames_collide(
    tmp_path: Path,
    first_names: tuple[str, str],
    expected_match_count: int,
    expected_filenames: set[str],
) -> None:
    xlsx_path = tmp_path / "names.xlsx"
    pd.DataFrame(
        {"First Name": list(first_names), "Last Name": ["Lee", "Lee"]}
    ).to_excel(xlsx_path, index=False)
    author_path = tmp_path / "author_details.parquet"
    author_path.write_bytes(b"synthetic author resource")
    xlsx_resource = register_resource(
        xlsx_path,
        group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
        fragment_type=FragmentType.EXCEL_ROW,
    )
    author_resource = register_resource(
        author_path,
        group=ResourceGroup.SCISCINET_HF,
        fragment_type=FragmentType.AUTHOR_ID,
    )
    config = PipelineConfig(
        files_config={
            **{
                key: {"path": str(xlsx_path), "sha256": "synthetic", "desc": "synthetic"}
                for key in REQUIRED_FILES_CONFIG_KEYS
            },
            "hcr_xlsx_names": {
                "path": str(xlsx_path),
                "sha256": "synthetic",
                "desc": "synthetic",
            },
        },
        db_file=tmp_path / "unused.duckdb",
        state_file=tmp_path / "state.json",
        output_dir=tmp_path,
        output_format="txt",
        pandoc_reference_docx=tmp_path / "unused.docx",
        timezone="UTC",
        sample_seed=1,
        sample_draw_sizes=[{"size": 2, "replace": False}],
        pilot_xlsx_name=xlsx_path.name,
        total_draws=8,
        card_subset_mode=3,
        match_rule_version=MatchRuleVersion(xlsx_name=2),
    )
    conn = _connect()
    conn.execute("SET threads=1")
    conn.execute("SET memory_limit='128MB'")
    names = [NameKey(first_name=first, last_name="Lee") for first in first_names]
    outer_dict = OuterDict.from_name_keys(names)
    log_lines: list[str] = []
    context = PipelineContext(
        config=config,
        manager=PipelineManager(config.state_file, config.db_file),
        conn=conn,
        diagnostics=DiagnosticsReport(tmp_path / "diagnostics"),
        interactive=False,
        artifacts_dir=tmp_path,
        resources=PipelineResources(
            parquet_resources={author_resource.name: author_resource},
            xlsx_resources={xlsx_resource.name: xlsx_resource},
            world_bank_resource=xlsx_resource,
            docx_resources={},
            openalex_author_search_log_resource=xlsx_resource,
            openalex_paper_title_log_resource=xlsx_resource,
            openalex_paper_title_parquet_resource=xlsx_resource,
        ),
        outer_dict=outer_dict,
        log=lambda message, _style: log_lines.append(message),
    )
    try:
        _build_population_table(
            conn, {xlsx_resource.name: xlsx_resource}, table_name=POPULATION_TABLE
        )
        conn.execute(
            f'''
            CREATE TABLE {POPULATION_NAMES_TABLE} AS
            SELECT "{KTP_POPULATION_INDEX_COL}",
                   "{HCR_FIRST_NAME_COL}" AS "{KTP_FIRST_NAME_COL}",
                   "{HCR_LAST_NAME_COL}" AS "{KTP_LAST_NAME_COL}"
            FROM {POPULATION_TABLE}
            '''
        )
        economy_columns = (
            KTP_ECONOMIES_COL,
            KTP_ECONOMIES_INCOME_GROUP_COL,
            KTP_ECONOMY_MATCH_COL,
            KTP_HCR_PRIMARY_AFFILIATIONS_COL,
            KTP_HCR_SECONDARY_AFFILIATIONS_COL,
            KTP_PRIORITY_COL,
            KTP_PRIORITY_GROUP_COL,
        )
        conn.execute(
            f'''
            CREATE TABLE {POPULATION_ECON_TABLE} AS
            SELECT "{KTP_POPULATION_INDEX_COL}",
                   {", ".join(f'NULL::VARCHAR AS "{col}"' for col in economy_columns)}
            FROM {POPULATION_TABLE}
            '''
        )
        conn.execute(
            f'''
            CREATE TABLE {SAMPLES_TABLE} AS
            SELECT "{KTP_HCR_FILENAME_COL}" AS "{KTP_FILENAME_COL}",
                   "{KTP_HCR_ROW_NUMBER_COL}" AS "{KTP_FRAGMENT_COL}",
                   CAST("{KTP_POPULATION_INDEX_COL}" + 7 AS VARCHAR) AS "{DRAW_LABEL}"
            FROM {POPULATION_TABLE}
            '''
        )
        conn.execute(
            f'CREATE TABLE {OUTERDICT_NAME_VIEW} '
            f'("{KTP_NAMEKEY_COL}" VARCHAR, "{KTP_FIRST_NAME_COL}" VARCHAR, '
            f'"{KTP_LAST_NAME_COL}" VARCHAR)'
        )
        conn.executemany(
            f'INSERT INTO {OUTERDICT_NAME_VIEW} VALUES (?, ?, ?)',
            [(name.to_json_key(), name.first_name, name.last_name) for name in names],
        )
        conn.execute(
            f'CREATE TABLE {REGISTERED_RESOURCES_TABLE} '
            '(resource_name VARCHAR, fragment_type VARCHAR)'
        )
        conn.execute(
            f'INSERT INTO {REGISTERED_RESOURCES_TABLE} VALUES (?, ?)',
            [xlsx_path.name, FragmentType.EXCEL_ROW.value],
        )

        step_07_match_xlsx.run(context)
        matched_rows = conn.execute(
            f'SELECT "{KTP_NAMEKEY_COL}", "{DRAW_LABEL}" FROM {XLSX_MATCH_VIEW}'
        ).fetchall()
        assert len(matched_rows) == expected_match_count
        assert {draw for _, draw in matched_rows} == {"7", "8"}
        draws_by_name = {
            name.first_name: {
                draw for source_key, draw in matched_rows if source_key == name.to_json_key()
            }
            for name in names
        }
        if expected_match_count == 4:
            assert list(draws_by_name.values()) == [{"7", "8"}, {"7", "8"}]
        else:
            assert list(draws_by_name.values()) == [{"7"}, {"8"}]

        for name, marker in zip(names, ("dotted author", "compact author"), strict=True):
            outer_dict.add_inner(
                name,
                InnerDict.from_mapping(
                    {KTP_SSNAD_FILENAME_COL: author_path.name, "author_marker": marker},
                    ParquetMatchProcedure(),
                ),
            )
        result = step_10_build_cards.run(context)
        cards = result.artifacts["cards"]
        assert set(cards) == expected_filenames
        collision_logs = [
            line for line in log_lines if line.startswith("Duplicate card filename")
        ]
        if expected_match_count == 4:
            assert len(collision_logs) == 2
            for name, filename, line in zip(
                names, sorted(expected_filenames), collision_logs, strict=True
            ):
                assert name.to_json_key() in line
                assert all(other.to_json_key() in line for other in names)
                assert filename in line
            first, second = sorted(expected_filenames)
            assert "dotted author" in cards[first]
            assert "compact author" not in cards[first]
            assert "compact author" in cards[second]
            assert "dotted author" not in cards[second]
        else:
            assert collision_logs == []
            assert "dotted author" in cards["7_AnneMarie_Lee"]
            assert "compact author" in cards["8_AnneMarie_Lee"]
    finally:
        conn.close()
