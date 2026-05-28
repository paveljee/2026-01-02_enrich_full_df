from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.helpers.data_models import InnerDict, NameKey
from src.helpers.duckdb_utils import register_frame
from src.helpers.schema import (
    CARD_PARTITION_REVIEW_VIEW,
    CARD_PARTITION_TABLE,
    DOCX_OUTPUT_VIEW,
    PARQUET_OUTPUT_VIEW,
    XLSX_OUTPUT_VIEW,
)
from src.helpers.vars import (
    CARD_PARTITION_ARTIFACT_MODES,
    DRAW_LABEL,
    HCR_CATEGORY_COL,
    KTP_DOCX_MATCH_COL,
    KTP_ECONOMIES_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FF_AUTHOR_ID_COL,
    KTP_FF_DISCARD_COL,
    KTP_FF_NOTE_COL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    KTP_PARTITION_COL,
    KTP_PARTITION_DOCX_VALUE,
    KTP_PARTITION_FLAG_DOCX_ANY_COL,
    KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_ANY_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
    KTP_PARTITION_NO_RESOLUTION_VALUE,
    KTP_PARTITION_SSN_VALUE,
    KTP_PARTITION_XLSX_VALUE,
    KTP_SOURCE_KEY_COL,
    KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
    KTP_SSN_SUM_HIT_1PCT_COL,
    KTP_SSN_TOP_INSTITUTIONS_COL,
    KTP_SSNAD_MATCH_COL,
    KTP_XLSX_MATCH_COL,
    KTP_XLSX_MATCH_FIRST_TOKENS_KEY,
    KTP_XLSX_MATCH_LAST_NAME_NORM_KEY,
    KTP_XLSX_MATCH_RULE_KEY,
    KTP_XLSX_MATCH_RULE_V1,
    KTP_XLSX_MATCH_RULE_V2,
    KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY,
    KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY,
    SSNAD_CITED_BY_COUNT_COL,
    SSNAD_DISPLAY_NAME_ALTERNATIVES_COL,
    SSNAD_DISPLAY_NAME_COL,
    SSNAD_FILENAME_COL,
    SSNAD_WORKS_API_URL_COL,
    SSNAD_WORKS_COUNT_COL,
)
from src.steps import step_10_build_cards as step10


class DummyProcedure:
    dataset_id_field = KTP_SOURCE_KEY_COL


def _inner(data: dict[str, object]) -> InnerDict:
    return InnerDict.from_mapping(data, DummyProcedure())


def _name(first: str = "Ada", last: str = "Lovelace") -> NameKey:
    return NameKey(first_name=first, last_name=last)


def _xlsx_payload(*, exact: bool = True) -> str:
    return json.dumps(
        {
            KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY: ["ada"],
            KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY: "lovelace",
            KTP_XLSX_MATCH_FIRST_TOKENS_KEY: ["ada" if exact else "augusta"],
            KTP_XLSX_MATCH_LAST_NAME_NORM_KEY: "lovelace",
        }
    )


def _xlsx_v2_payload(*, rule: str, first_tokens: list[str] | None = None) -> str:
    return json.dumps(
        {
            KTP_XLSX_MATCH_RULE_KEY: rule,
            KTP_XLSX_MATCH_SOURCE_KEY_TOKENS_KEY: ["ada"],
            KTP_XLSX_MATCH_SOURCE_KEY_LAST_KEY: ["lovelace"],
            KTP_XLSX_MATCH_FIRST_TOKENS_KEY: first_tokens or ["ada"],
            KTP_XLSX_MATCH_LAST_NAME_NORM_KEY: ["lovelace"],
        }
    )


def _xlsx_inner(*, exact: bool = True, draw: object = 1) -> InnerDict:
    return _inner(
        {
            KTP_FILENAME_COL: "hcr.xlsx",
            KTP_FRAGMENT_COL: "11",
            KTP_FRAGMENT_TYPE_COL: "excel_row",
            DRAW_LABEL: draw,
            KTP_XLSX_MATCH_COL: _xlsx_payload(exact=exact),
        }
    )


def _docx_inner(*, complete: bool = True) -> InnerDict:
    return _inner(
        {
            KTP_FILENAME_COL: "manual.docx",
            KTP_FRAGMENT_COL: "1",
            KTP_FRAGMENT_TYPE_COL: "docx_row",
            "ktp.table_1_researcher_author": "Ada Lovelace",
            "ktp.table_1_affiliation": "Analytical Engine Lab" if complete else "",
        }
    )


def _sciscinet_inner(fragment: str = "A1") -> InnerDict:
    return _inner(
        {
            SSNAD_FILENAME_COL: "author_details.parquet",
            KTP_FRAGMENT_COL: fragment,
            KTP_FRAGMENT_TYPE_COL: "author_id",
        }
    )


def _state(*inner_dicts: InnerDict, name: NameKey | None = None) -> step10.CardPartitionRuleState:
    return step10._evaluate_card_partition_state(
        name or _name(),
        tuple(inner_dicts),
        sciscinet_filenames={"author_details.parquet"},
        docx_filenames={"manual.docx"},
    )


def test_partition_values_follow_subset1_complement_priority() -> None:
    subset1 = _state(_xlsx_inner(), _docx_inner(), _sciscinet_inner())
    assert subset1.subset1_ok
    assert step10._partition_value(subset1) == KTP_PARTITION_NO_RESOLUTION_VALUE

    xlsx_only = _state(_xlsx_inner(exact=False), _docx_inner(), _sciscinet_inner())
    assert xlsx_only.xlsx_any
    assert xlsx_only.xlsx_non_exact_any
    assert step10._partition_value(xlsx_only) == KTP_PARTITION_XLSX_VALUE

    sciscinet_only = _state(_xlsx_inner(), _docx_inner())
    assert sciscinet_only.sciscinet_count == 0
    assert step10._partition_value(sciscinet_only) == KTP_PARTITION_SSN_VALUE

    xlsx_plus_sciscinet = _state(
        _xlsx_inner(exact=False),
        _docx_inner(),
        _sciscinet_inner("A1"),
        _sciscinet_inner("A2"),
    )
    assert step10._partition_value(xlsx_plus_sciscinet) == KTP_PARTITION_SSN_VALUE

    docx_only = _state(_xlsx_inner(), _docx_inner(complete=False), _sciscinet_inner())
    assert step10._partition_value(docx_only) == KTP_PARTITION_DOCX_VALUE

    xlsx_docx_sciscinet = _state(_xlsx_inner(exact=False), _docx_inner(complete=False))
    assert step10._partition_value(xlsx_docx_sciscinet) == KTP_PARTITION_DOCX_VALUE


def test_flags_cover_missing_invalid_and_multi_docx_cases() -> None:
    missing_xlsx = _state(_inner({KTP_FILENAME_COL: "hcr.xlsx"}), _docx_inner(), _sciscinet_inner())
    assert not missing_xlsx.xlsx_any
    assert not missing_xlsx.xlsx_non_exact_any
    assert step10._partition_value(missing_xlsx) == KTP_PARTITION_XLSX_VALUE

    invalid_xlsx = _state(
        _inner({KTP_FILENAME_COL: "hcr.xlsx", KTP_XLSX_MATCH_COL: "not-json"}),
        _docx_inner(),
        _sciscinet_inner(),
    )
    assert invalid_xlsx.xlsx_any
    assert invalid_xlsx.xlsx_non_exact_any

    missing_docx = _state(_xlsx_inner(), _sciscinet_inner())
    assert not missing_docx.docx_any
    assert not missing_docx.docx_table_1_required_all
    assert step10._partition_value(missing_docx) == KTP_PARTITION_DOCX_VALUE

    multi_docx_one_complete = _state(
        _xlsx_inner(),
        _docx_inner(complete=False),
        _docx_inner(complete=True),
        _sciscinet_inner(),
    )
    assert multi_docx_one_complete.docx_any
    assert multi_docx_one_complete.docx_table_1_required_all
    assert multi_docx_one_complete.subset1_ok


def test_v2_xlsx_v1_rule_payload_is_non_exact_for_partitioning() -> None:
    state = _state(
        _inner(
            {
                KTP_FILENAME_COL: "hcr.xlsx",
                KTP_XLSX_MATCH_COL: _xlsx_v2_payload(
                    rule=KTP_XLSX_MATCH_RULE_V1,
                    first_tokens=["ada", "nunes"],
                ),
            }
        ),
        _docx_inner(),
        _sciscinet_inner(),
    )

    assert state.xlsx_any
    assert state.xlsx_non_exact_any
    assert step10._partition_value(state) == KTP_PARTITION_XLSX_VALUE


def test_v2_xlsx_v2_rule_payload_is_exact_for_partitioning() -> None:
    state = _state(
        _inner(
            {
                KTP_FILENAME_COL: "hcr.xlsx",
                KTP_XLSX_MATCH_COL: _xlsx_v2_payload(rule=KTP_XLSX_MATCH_RULE_V2),
            }
        ),
        _docx_inner(),
        _sciscinet_inner(),
    )

    assert state.xlsx_any
    assert not state.xlsx_non_exact_any
    assert state.subset1_ok


def test_partition_rows_sort_sciscinet_by_count_then_xlsx_tie_break() -> None:
    sc0_name = _name("Ada", "Zero")
    sc2_name = _name("Ada", "Two")
    sc2_xlsx_name = _name("Ada", "TwoXlsx")
    selected = [
        (
            sc2_xlsx_name,
            (
                _xlsx_inner(exact=False),
                _docx_inner(),
                _sciscinet_inner("1"),
                _sciscinet_inner("2"),
            ),
        ),
        (sc2_name, (_xlsx_inner(), _docx_inner(), _sciscinet_inner("1"), _sciscinet_inner("2"))),
        (sc0_name, (_xlsx_inner(), _docx_inner())),
    ]
    states = {
        name_key.to_json_key(): step10._evaluate_card_partition_state(
            name_key,
            tuple(inner_dicts),
            sciscinet_filenames={"author_details.parquet"},
            docx_filenames={"manual.docx"},
        )
        for name_key, inner_dicts in selected
    }

    df = step10._partition_rows_df(selected, state_by_source_key=states, subset_mode=2)

    assert df[KTP_LAST_NAME_COL].tolist() == ["Zero", "Two", "TwoXlsx"]
    assert df[KTP_PARTITION_FLAG_SSN_COUNT_COL].tolist() == [0, 2, 2]
    assert df[KTP_PARTITION_COL].tolist() == [
        KTP_PARTITION_SSN_VALUE,
        KTP_PARTITION_SSN_VALUE,
        KTP_PARTITION_SSN_VALUE,
    ]


def test_partition_artifact_modes_are_limited_to_subset1_and_subset2() -> None:
    assert CARD_PARTITION_ARTIFACT_MODES == {1, 2}


def _create_relation(
    conn: duckdb.DuckDBPyConnection,
    name: str,
    rows: list[dict[str, object]],
    columns: list[str],
) -> None:
    df = pd.DataFrame(rows, columns=columns)
    register_frame(conn, f"{name}_frame", df)
    conn.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {name}_frame")


def test_partition_review_view_has_specified_order_and_placeholders() -> None:
    conn = duckdb.connect(":memory:")
    partition_rows = pd.DataFrame(
        [
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_PARTITION_COL: KTP_PARTITION_XLSX_VALUE,
                KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: True,
                KTP_PARTITION_FLAG_XLSX_ANY_COL: True,
                KTP_PARTITION_FLAG_SSN_COUNT_COL: 1,
                KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: True,
                KTP_PARTITION_FLAG_DOCX_ANY_COL: True,
                "card_subset_mode": 2,
                DRAW_LABEL: "1",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Xlsx",
            },
            {
                KTP_SOURCE_KEY_COL: "sc-zero-source",
                KTP_PARTITION_COL: KTP_PARTITION_SSN_VALUE,
                KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: False,
                KTP_PARTITION_FLAG_XLSX_ANY_COL: True,
                KTP_PARTITION_FLAG_SSN_COUNT_COL: 0,
                KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: True,
                KTP_PARTITION_FLAG_DOCX_ANY_COL: True,
                "card_subset_mode": 2,
                DRAW_LABEL: "2",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "ScZero",
            },
            {
                KTP_SOURCE_KEY_COL: "sc-one-source",
                KTP_PARTITION_COL: KTP_PARTITION_SSN_VALUE,
                KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: False,
                KTP_PARTITION_FLAG_XLSX_ANY_COL: True,
                KTP_PARTITION_FLAG_SSN_COUNT_COL: 2,
                KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: True,
                KTP_PARTITION_FLAG_DOCX_ANY_COL: True,
                "card_subset_mode": 2,
                DRAW_LABEL: "2",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "ScOne",
            },
            {
                KTP_SOURCE_KEY_COL: "docx-source",
                KTP_PARTITION_COL: KTP_PARTITION_DOCX_VALUE,
                KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: False,
                KTP_PARTITION_FLAG_XLSX_ANY_COL: True,
                KTP_PARTITION_FLAG_SSN_COUNT_COL: 1,
                KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: False,
                KTP_PARTITION_FLAG_DOCX_ANY_COL: True,
                "card_subset_mode": 2,
                DRAW_LABEL: "3",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Docx",
            },
        ]
    )
    step10._materialize_partition_table(conn, partition_rows)

    _create_relation(
        conn,
        XLSX_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "hcr.xlsx",
                KTP_FRAGMENT_COL: "11",
                KTP_FRAGMENT_TYPE_COL: "excel_row",
                DRAW_LABEL: "1",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Xlsx",
                HCR_CATEGORY_COL: "Highly Cited",
                KTP_ECONOMIES_COL: "United Kingdom",
                KTP_ECONOMY_MATCH_COL: "exact",
                KTP_HCR_PRIMARY_AFFILIATIONS_COL: "Analytical Engine Lab",
                KTP_HCR_SECONDARY_AFFILIATIONS_COL: "Royal Society",
                KTP_XLSX_MATCH_COL: _xlsx_payload(exact=False),
            },
            {
                KTP_SOURCE_KEY_COL: "sc-zero-source",
                KTP_FILENAME_COL: "hcr.xlsx",
                KTP_FRAGMENT_COL: "12",
                KTP_FRAGMENT_TYPE_COL: "excel_row",
                DRAW_LABEL: "2",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "ScZero",
                HCR_CATEGORY_COL: "ScZero HCR",
                KTP_ECONOMIES_COL: "France",
                KTP_ECONOMY_MATCH_COL: "singleton xlsx",
                KTP_HCR_PRIMARY_AFFILIATIONS_COL: "ScZero Xlsx Lab",
                KTP_HCR_SECONDARY_AFFILIATIONS_COL: "",
                KTP_XLSX_MATCH_COL: _xlsx_payload(),
            },
            {
                KTP_SOURCE_KEY_COL: "sc-one-source",
                KTP_FILENAME_COL: "hcr.xlsx",
                KTP_FRAGMENT_COL: "13",
                KTP_FRAGMENT_TYPE_COL: "excel_row",
                DRAW_LABEL: "2",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "ScOne",
                HCR_CATEGORY_COL: "ScOne HCR",
                KTP_ECONOMIES_COL: "Canada",
                KTP_ECONOMY_MATCH_COL: "singleton xlsx",
                KTP_HCR_PRIMARY_AFFILIATIONS_COL: "ScOne Xlsx Lab",
                KTP_HCR_SECONDARY_AFFILIATIONS_COL: "",
                KTP_XLSX_MATCH_COL: _xlsx_payload(),
            },
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            DRAW_LABEL,
            KTP_FIRST_NAME_COL,
            KTP_LAST_NAME_COL,
            HCR_CATEGORY_COL,
            KTP_ECONOMIES_COL,
            KTP_ECONOMY_MATCH_COL,
            KTP_HCR_PRIMARY_AFFILIATIONS_COL,
            KTP_HCR_SECONDARY_AFFILIATIONS_COL,
            KTP_XLSX_MATCH_COL,
        ],
    )
    _create_relation(
        conn,
        PARQUET_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "author_details.parquet",
                KTP_FRAGMENT_COL: "A-xlsx",
                KTP_FRAGMENT_TYPE_COL: "author_id",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Xlsx",
                SSNAD_DISPLAY_NAME_COL: "Ada Xlsx OpenAlex",
                SSNAD_DISPLAY_NAME_ALTERNATIVES_COL: "[]",
                KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL: "['Math']",
                KTP_SSNAD_MATCH_COL: "xlsx-ssn-match",
                KTP_SSN_SUM_HIT_1PCT_COL: 2,
                KTP_SSN_TOP_INSTITUTIONS_COL: "Xlsx Singleton Institution",
                SSNAD_WORKS_COUNT_COL: 10,
                SSNAD_CITED_BY_COUNT_COL: 20,
                SSNAD_WORKS_API_URL_COL: "https://api.openalex.org/authors/A-xlsx",
            },
            {
                KTP_SOURCE_KEY_COL: "sc-one-source",
                KTP_FILENAME_COL: "author_details.parquet",
                KTP_FRAGMENT_COL: "A-sc-one",
                KTP_FRAGMENT_TYPE_COL: "author_id",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "ScOne",
                SSNAD_DISPLAY_NAME_COL: "Ada ScOne OpenAlex",
                SSNAD_DISPLAY_NAME_ALTERNATIVES_COL: "[]",
                KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL: "['Physics']",
                KTP_SSNAD_MATCH_COL: "sc-one-ssn-match",
                KTP_SSN_SUM_HIT_1PCT_COL: 5,
                KTP_SSN_TOP_INSTITUTIONS_COL: "ScOne Singleton Institution",
                SSNAD_WORKS_COUNT_COL: 30,
                SSNAD_CITED_BY_COUNT_COL: 40,
                SSNAD_WORKS_API_URL_COL: "https://api.openalex.org/authors/A-sc-one",
            },
            {
                KTP_SOURCE_KEY_COL: "docx-source",
                KTP_FILENAME_COL: "author_details.parquet",
                KTP_FRAGMENT_COL: "A-docx",
                KTP_FRAGMENT_TYPE_COL: "author_id",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Docx",
                SSNAD_DISPLAY_NAME_COL: "Ada Docx OpenAlex",
                SSNAD_DISPLAY_NAME_ALTERNATIVES_COL: "[]",
                KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL: "['Biology']",
                KTP_SSNAD_MATCH_COL: "docx-ssn-match",
                KTP_SSN_SUM_HIT_1PCT_COL: 7,
                KTP_SSN_TOP_INSTITUTIONS_COL: "Docx Singleton Institution",
                SSNAD_WORKS_COUNT_COL: 50,
                SSNAD_CITED_BY_COUNT_COL: 60,
                SSNAD_WORKS_API_URL_COL: "https://api.openalex.org/authors/A-docx",
            },
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            KTP_FIRST_NAME_COL,
            KTP_LAST_NAME_COL,
            SSNAD_DISPLAY_NAME_COL,
            SSNAD_DISPLAY_NAME_ALTERNATIVES_COL,
            KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
            KTP_SSNAD_MATCH_COL,
            KTP_SSN_SUM_HIT_1PCT_COL,
            KTP_SSN_TOP_INSTITUTIONS_COL,
            SSNAD_WORKS_COUNT_COL,
            SSNAD_CITED_BY_COUNT_COL,
            SSNAD_WORKS_API_URL_COL,
        ],
    )
    _create_relation(
        conn,
        DOCX_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "docx-source",
                KTP_FILENAME_COL: "manual.docx",
                KTP_FRAGMENT_COL: "7",
                KTP_FRAGMENT_TYPE_COL: "docx_row",
                DRAW_LABEL: "3",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Docx",
                KTP_DOCX_MATCH_COL: "docx-primary-match",
                "ktp.table_1_researcher_author": "Ada Docx",
                "ktp.table_1_affiliation": "Difference Institute",
            },
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "manual.docx",
                KTP_FRAGMENT_COL: "8",
                KTP_FRAGMENT_TYPE_COL: "docx_row",
                DRAW_LABEL: "1",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Xlsx",
                KTP_DOCX_MATCH_COL: "xlsx-docx-match",
                "ktp.table_1_researcher_author": "Ada Xlsx Docx",
                "ktp.table_1_affiliation": "Xlsx Singleton Institute",
            },
            {
                KTP_SOURCE_KEY_COL: "sc-zero-source",
                KTP_FILENAME_COL: "manual.docx",
                KTP_FRAGMENT_COL: "9",
                KTP_FRAGMENT_TYPE_COL: "docx_row",
                DRAW_LABEL: "2",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "ScZero",
                KTP_DOCX_MATCH_COL: "sc-zero-docx-match",
                "ktp.table_1_researcher_author": "Ada ScZero Docx",
                "ktp.table_1_affiliation": "ScZero Singleton Institute",
            },
            {
                KTP_SOURCE_KEY_COL: "sc-one-source",
                KTP_FILENAME_COL: "manual.docx",
                KTP_FRAGMENT_COL: "10",
                KTP_FRAGMENT_TYPE_COL: "docx_row",
                DRAW_LABEL: "2",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "ScOne",
                KTP_DOCX_MATCH_COL: "sc-one-docx-match",
                "ktp.table_1_researcher_author": "Ada ScOne Docx",
                "ktp.table_1_affiliation": "ScOne Singleton Institute",
            },
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            DRAW_LABEL,
            KTP_FIRST_NAME_COL,
            KTP_LAST_NAME_COL,
            KTP_DOCX_MATCH_COL,
            "ktp.table_1_researcher_author",
            "ktp.table_1_affiliation",
        ],
    )

    review_columns = step10._create_partition_review_view(conn)
    review_df = conn.execute(f"SELECT * FROM {CARD_PARTITION_REVIEW_VIEW}").df()

    assert conn.execute(f"SELECT COUNT(*) FROM {CARD_PARTITION_TABLE}").fetchone() == (4,)
    assert review_df.columns.tolist() == review_columns
    assert review_df.columns.tolist() == [
        KTP_SOURCE_KEY_COL,
        KTP_PARTITION_COL,
        KTP_FILENAME_COL,
        KTP_FRAGMENT_COL,
        KTP_FRAGMENT_TYPE_COL,
        KTP_FF_AUTHOR_ID_COL,
        KTP_FF_DISCARD_COL,
        KTP_FF_NOTE_COL,
        DRAW_LABEL,
        KTP_FIRST_NAME_COL,
        KTP_LAST_NAME_COL,
        SSNAD_DISPLAY_NAME_COL,
        SSNAD_DISPLAY_NAME_ALTERNATIVES_COL,
        HCR_CATEGORY_COL,
        KTP_SSN_FIELD_DISPLAY_NAMES_LIST_COL,
        KTP_ECONOMIES_COL,
        KTP_ECONOMY_MATCH_COL,
        KTP_HCR_PRIMARY_AFFILIATIONS_COL,
        KTP_HCR_SECONDARY_AFFILIATIONS_COL,
        KTP_SSN_TOP_INSTITUTIONS_COL,
        KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
        KTP_PARTITION_FLAG_XLSX_ANY_COL,
        KTP_XLSX_MATCH_COL,
        KTP_PARTITION_FLAG_SSN_COUNT_COL,
        KTP_SSNAD_MATCH_COL,
        KTP_SSN_SUM_HIT_1PCT_COL,
        SSNAD_WORKS_COUNT_COL,
        SSNAD_CITED_BY_COUNT_COL,
        SSNAD_WORKS_API_URL_COL,
        KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL,
        KTP_PARTITION_FLAG_DOCX_ANY_COL,
        KTP_DOCX_MATCH_COL,
        "ktp.table_1_researcher_author",
        "ktp.table_1_affiliation",
    ]
    assert review_df[KTP_SOURCE_KEY_COL].tolist() == [
        "xlsx-source",
        "sc-zero-source",
        "sc-one-source",
        "docx-source",
    ]
    assert review_df[KTP_FF_DISCARD_COL].isna().all()
    assert review_df[KTP_FF_NOTE_COL].isna().all()

    xlsx_row = review_df[review_df[KTP_SOURCE_KEY_COL] == "xlsx-source"].iloc[0]
    assert xlsx_row[KTP_FILENAME_COL] == "hcr.xlsx\nauthor_details.parquet\nmanual.docx"
    assert xlsx_row[KTP_FF_AUTHOR_ID_COL] == "A-xlsx"
    assert xlsx_row[SSNAD_DISPLAY_NAME_COL] == "Ada Xlsx OpenAlex"
    assert xlsx_row[KTP_DOCX_MATCH_COL] == "xlsx-docx-match"
    assert xlsx_row["ktp.table_1_affiliation"] == "Xlsx Singleton Institute"

    sc_placeholder = review_df[review_df[KTP_SOURCE_KEY_COL] == "sc-zero-source"].iloc[0]
    assert sc_placeholder[KTP_FILENAME_COL] == "hcr.xlsx\nmanual.docx"
    assert pd.isna(sc_placeholder[KTP_FF_AUTHOR_ID_COL])
    assert pd.isna(sc_placeholder[SSNAD_DISPLAY_NAME_COL])
    assert sc_placeholder[HCR_CATEGORY_COL] == "ScZero HCR"
    assert sc_placeholder[KTP_DOCX_MATCH_COL] == "sc-zero-docx-match"
    assert sc_placeholder[KTP_PARTITION_FLAG_SSN_COUNT_COL] == 0

    sc_row = review_df[review_df[KTP_SOURCE_KEY_COL] == "sc-one-source"].iloc[0]
    assert sc_row[KTP_FRAGMENT_COL] == "13\nA-sc-one\n10"
    assert sc_row[KTP_FF_AUTHOR_ID_COL] == "A-sc-one"
    assert sc_row[HCR_CATEGORY_COL] == "ScOne HCR"
    assert sc_row["ktp.table_1_affiliation"] == "ScOne Singleton Institute"

    docx_row = review_df[review_df[KTP_SOURCE_KEY_COL] == "docx-source"].iloc[0]
    assert docx_row[KTP_FILENAME_COL] == "author_details.parquet\nmanual.docx"
    assert docx_row["ktp.table_1_affiliation"] == "Difference Institute"
    assert docx_row[KTP_FF_AUTHOR_ID_COL] == "A-docx"
    assert docx_row[SSNAD_DISPLAY_NAME_COL] == "Ada Docx OpenAlex"
    assert pd.isna(docx_row[HCR_CATEGORY_COL])


def test_partition_review_view_merges_all_available_context_values() -> None:
    conn = duckdb.connect(":memory:")
    partition_rows = pd.DataFrame(
        [
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_PARTITION_COL: KTP_PARTITION_XLSX_VALUE,
                KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: True,
                KTP_PARTITION_FLAG_XLSX_ANY_COL: True,
                KTP_PARTITION_FLAG_SSN_COUNT_COL: 2,
                KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: True,
                KTP_PARTITION_FLAG_DOCX_ANY_COL: True,
                "card_subset_mode": 2,
                DRAW_LABEL: "1",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Merged",
            }
        ]
    )
    step10._materialize_partition_table(conn, partition_rows)

    _create_relation(
        conn,
        XLSX_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "hcr.xlsx",
                KTP_FRAGMENT_COL: "11",
                KTP_FRAGMENT_TYPE_COL: "excel_row",
                DRAW_LABEL: "1",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Merged",
                HCR_CATEGORY_COL: "Highly Cited",
                KTP_XLSX_MATCH_COL: _xlsx_payload(exact=False),
            }
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            DRAW_LABEL,
            KTP_FIRST_NAME_COL,
            KTP_LAST_NAME_COL,
            HCR_CATEGORY_COL,
            KTP_XLSX_MATCH_COL,
        ],
    )
    _create_relation(
        conn,
        PARQUET_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "author_details.parquet",
                KTP_FRAGMENT_COL: "A-1",
                KTP_FRAGMENT_TYPE_COL: "author_id",
                SSNAD_DISPLAY_NAME_COL: "Ada One",
            },
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "author_details.parquet",
                KTP_FRAGMENT_COL: "A-2",
                KTP_FRAGMENT_TYPE_COL: "author_id",
                SSNAD_DISPLAY_NAME_COL: "Ada Two",
            },
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            SSNAD_DISPLAY_NAME_COL,
        ],
    )
    _create_relation(
        conn,
        DOCX_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "manual.docx",
                KTP_FRAGMENT_COL: "1",
                KTP_FRAGMENT_TYPE_COL: "docx_row",
                KTP_DOCX_MATCH_COL: "docx-one\nline",
            },
            {
                KTP_SOURCE_KEY_COL: "xlsx-source",
                KTP_FILENAME_COL: "manual.docx",
                KTP_FRAGMENT_COL: "2",
                KTP_FRAGMENT_TYPE_COL: "docx_row",
                KTP_DOCX_MATCH_COL: "docx-two",
            },
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            KTP_DOCX_MATCH_COL,
        ],
    )

    step10._create_partition_review_view(conn)
    review_row = conn.execute(f"SELECT * FROM {CARD_PARTITION_REVIEW_VIEW}").df().iloc[0]

    assert review_row[KTP_FF_AUTHOR_ID_COL] == "A-1\nA-2"
    assert review_row[SSNAD_DISPLAY_NAME_COL] == "Ada One\nAda Two"
    assert review_row[KTP_DOCX_MATCH_COL] == "docx-one\nline\n-----\ndocx-two"


def test_partition_review_view_includes_no_resolution_partition_context() -> None:
    conn = duckdb.connect(":memory:")
    partition_rows = pd.DataFrame(
        [
            {
                KTP_SOURCE_KEY_COL: "subset1-source",
                KTP_PARTITION_COL: KTP_PARTITION_NO_RESOLUTION_VALUE,
                KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: False,
                KTP_PARTITION_FLAG_XLSX_ANY_COL: True,
                KTP_PARTITION_FLAG_SSN_COUNT_COL: 1,
                KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: True,
                KTP_PARTITION_FLAG_DOCX_ANY_COL: True,
                "card_subset_mode": 1,
                DRAW_LABEL: "1",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Subset",
            }
        ]
    )
    step10._materialize_partition_table(conn, partition_rows)

    _create_relation(
        conn,
        XLSX_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "subset1-source",
                KTP_FILENAME_COL: "hcr.xlsx",
                KTP_FRAGMENT_COL: "21",
                KTP_FRAGMENT_TYPE_COL: "excel_row",
                HCR_CATEGORY_COL: "Highly Cited",
                KTP_XLSX_MATCH_COL: _xlsx_payload(),
            }
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            HCR_CATEGORY_COL,
            KTP_XLSX_MATCH_COL,
        ],
    )
    _create_relation(
        conn,
        PARQUET_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "subset1-source",
                KTP_FILENAME_COL: "author_details.parquet",
                KTP_FRAGMENT_COL: "A-subset",
                KTP_FRAGMENT_TYPE_COL: "author_id",
                SSNAD_DISPLAY_NAME_COL: "Ada Subset OpenAlex",
                KTP_SSNAD_MATCH_COL: "ssn-match",
            }
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            SSNAD_DISPLAY_NAME_COL,
            KTP_SSNAD_MATCH_COL,
        ],
    )
    _create_relation(
        conn,
        DOCX_OUTPUT_VIEW,
        [
            {
                KTP_SOURCE_KEY_COL: "subset1-source",
                KTP_FILENAME_COL: "manual.docx",
                KTP_FRAGMENT_COL: "4",
                KTP_FRAGMENT_TYPE_COL: "docx_row",
                KTP_DOCX_MATCH_COL: "docx-match",
                "ktp.table_1_affiliation": "Subset Institute",
            }
        ],
        [
            KTP_SOURCE_KEY_COL,
            KTP_FILENAME_COL,
            KTP_FRAGMENT_COL,
            KTP_FRAGMENT_TYPE_COL,
            KTP_DOCX_MATCH_COL,
            "ktp.table_1_affiliation",
        ],
    )

    step10._create_partition_review_view(conn)
    review_df = conn.execute(f"SELECT * FROM {CARD_PARTITION_REVIEW_VIEW}").df()

    assert len(review_df) == 1
    review_row = review_df.iloc[0]
    assert review_row[KTP_PARTITION_COL] == KTP_PARTITION_NO_RESOLUTION_VALUE
    assert review_row[KTP_FILENAME_COL] == "hcr.xlsx\nauthor_details.parquet\nmanual.docx"
    assert review_row[KTP_FF_AUTHOR_ID_COL] == "A-subset"
    assert review_row[HCR_CATEGORY_COL] == "Highly Cited"
    assert review_row[SSNAD_DISPLAY_NAME_COL] == "Ada Subset OpenAlex"
    assert review_row["ktp.table_1_affiliation"] == "Subset Institute"


def test_partition_review_view_merges_json_typed_context_values_as_display_text() -> None:
    conn = duckdb.connect(":memory:")
    partition_rows = pd.DataFrame(
        [
            {
                KTP_SOURCE_KEY_COL: "sc-source",
                KTP_PARTITION_COL: KTP_PARTITION_SSN_VALUE,
                KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL: False,
                KTP_PARTITION_FLAG_XLSX_ANY_COL: True,
                KTP_PARTITION_FLAG_SSN_COUNT_COL: 0,
                KTP_PARTITION_FLAG_DOCX_TABLE_1_REQUIRED_ALL_COL: True,
                KTP_PARTITION_FLAG_DOCX_ANY_COL: True,
                "card_subset_mode": 2,
                DRAW_LABEL: "1",
                KTP_FIRST_NAME_COL: "Ada",
                KTP_LAST_NAME_COL: "Json",
            }
        ]
    )
    step10._materialize_partition_table(conn, partition_rows)
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {XLSX_OUTPUT_VIEW} AS
        SELECT
            'sc-source' AS "{KTP_SOURCE_KEY_COL}",
            'hcr.xlsx' AS "{KTP_FILENAME_COL}",
            '1' AS "{KTP_FRAGMENT_COL}",
            'excel_row' AS "{KTP_FRAGMENT_TYPE_COL}",
            json('["United States"]') AS "{KTP_ECONOMIES_COL}"
        UNION ALL
        SELECT
            'sc-source' AS "{KTP_SOURCE_KEY_COL}",
            'hcr.xlsx' AS "{KTP_FILENAME_COL}",
            '2' AS "{KTP_FRAGMENT_COL}",
            'excel_row' AS "{KTP_FRAGMENT_TYPE_COL}",
            json('["Canada"]') AS "{KTP_ECONOMIES_COL}"
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {PARQUET_OUTPUT_VIEW} AS
        SELECT CAST(NULL AS VARCHAR) AS "{KTP_SOURCE_KEY_COL}"
        WHERE FALSE
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE VIEW {DOCX_OUTPUT_VIEW} AS
        SELECT CAST(NULL AS VARCHAR) AS "{KTP_SOURCE_KEY_COL}"
        WHERE FALSE
        """
    )

    step10._create_partition_review_view(conn)
    review_row = conn.execute(f"SELECT * FROM {CARD_PARTITION_REVIEW_VIEW}").df().iloc[0]

    assert review_row[KTP_ECONOMIES_COL] == '["United States"]\n["Canada"]'
