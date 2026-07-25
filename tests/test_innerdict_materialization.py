from __future__ import annotations

from types import SimpleNamespace

import duckdb
import pytest

from src.helpers.data_models import OuterDict
from src.helpers.duckdb_utils import (
    append_innerdicts_from_jsonlines_table,
    materialize_innerdicts_from_rows_table,
)
from src.helpers.jsonlines import loads_jsonlines
from src.helpers.schema import (
    INNERDICT_SOURCE_RELATIONS,
    INNERDICT_TABLE_SCHEMA,
)
from src.helpers.ssn_hit_selection import ssn_sum_hit_1pct_sql
from src.helpers.vars import DRAW_LABEL, KTP_SOURCE_KEY_COL


@pytest.mark.parametrize(
    ("table_name", "source_relation"),
    INNERDICT_SOURCE_RELATIONS.items(),
)
def test_innerdict_contract_materializes_and_hydrates_ordered_rows(
    table_name: str,
    source_relation: str,
) -> None:
    conn = duckdb.connect()
    try:
        conn.execute(
            f'''
            CREATE TABLE {source_relation} (
                "{KTP_SOURCE_KEY_COL}" VARCHAR,
                "{DRAW_LABEL}" VARCHAR,
                row_order INTEGER,
                integer_value BIGINT,
                nullable_value DOUBLE,
                boolean_value BOOLEAN,
                json_value JSON
            )
            '''
        )
        conn.executemany(
            f"INSERT INTO {source_relation} VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("key-a", "7", 1, 1186, None, True, '{"match":"first"}'),
                ("key-a", "7", 2, 7, 1.25, False, '{"match":"second"}'),
                ("key-b", "8", 3, 9, None, True, '{"match":"third"}'),
            ],
        )

        assert materialize_innerdicts_from_rows_table(
            conn,
            source_relation=source_relation,
            table_name=table_name,
        ) == (2, 3)

        described = conn.execute(f"DESCRIBE {table_name}").fetchall()
        assert [(row[0], row[1]) for row in described] == list(
            INNERDICT_TABLE_SCHEMA
        )
        persisted = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        assert [row[0] for row in persisted] == ["key-a", "key-b"]

        key_a_records = loads_jsonlines(persisted[0][1])
        assert [record["row_order"] for record in key_a_records] == [1, 2]
        assert all(KTP_SOURCE_KEY_COL not in record for record in key_a_records)
        assert key_a_records[0] == {
            DRAW_LABEL: "7",
            "row_order": 1,
            "integer_value": 1186,
            "nullable_value": None,
            "boolean_value": True,
            "json_value": '{"match":"first"}',
        }
        assert isinstance(key_a_records[0]["integer_value"], int)

        outer_dict = OuterDict(data={"key-a": [], "key-b": []})
        append_innerdicts_from_jsonlines_table(
            conn,
            table_name=table_name,
            outer_dict=outer_dict,
            procedure=SimpleNamespace(dataset_id_field="row_order"),
            required_columns={"row_order"},
        )
        assert [
            inner.data["row_order"]
            for inner in outer_dict.get_inner_by_key("key-a")
        ] == [1, 2]
        assert all(
            inner.data[DRAW_LABEL] == "7"
            for inner in outer_dict.get_inner_by_key("key-a")
        )
    finally:
        conn.close()


def test_innerdict_contract_materializes_empty_source() -> None:
    table_name, source_relation = next(iter(INNERDICT_SOURCE_RELATIONS.items()))
    conn = duckdb.connect()
    try:
        conn.execute(
            f'''
            CREATE TABLE {source_relation} (
                "{KTP_SOURCE_KEY_COL}" VARCHAR,
                row_order INTEGER
            )
            '''
        )

        assert materialize_innerdicts_from_rows_table(
            conn,
            source_relation=source_relation,
            table_name=table_name,
        ) == (0, 0)
        described = conn.execute(f"DESCRIBE {table_name}").fetchall()
        assert [(row[0], row[1]) for row in described] == list(
            INNERDICT_TABLE_SCHEMA
        )
        assert conn.execute(f"SELECT * FROM {table_name}").fetchall() == []
    finally:
        conn.close()


def test_innerdict_contract_rejects_hugeint_source() -> None:
    table_name, source_relation = next(iter(INNERDICT_SOURCE_RELATIONS.items()))
    conn = duckdb.connect()
    try:
        conn.execute(
            f'''
            CREATE TABLE {source_relation} (
                "{KTP_SOURCE_KEY_COL}" VARCHAR,
                metric HUGEINT
            )
            '''
        )
        conn.execute(f"INSERT INTO {source_relation} VALUES ('key-a', 1186)")

        with pytest.raises(ValueError, match="Cast domain-bounded values to BIGINT"):
            materialize_innerdicts_from_rows_table(
                conn,
                source_relation=source_relation,
                table_name=table_name,
            )
    finally:
        conn.close()


def test_ssn_sum_hit_1pct_sql_exposes_bigint_result() -> None:
    conn = duckdb.connect()
    try:
        conn.execute("CREATE TABLE hits (hit_1pct INTEGER)")
        conn.executemany("INSERT INTO hits VALUES (?)", [(1000,), (186,), (None,)])

        raw_type = conn.execute(
            "DESCRIBE SELECT SUM(COALESCE(hit_1pct, 0)) AS metric FROM hits"
        ).fetchone()
        assert raw_type is not None
        assert raw_type[1] == "HUGEINT"

        bounded_sum = ssn_sum_hit_1pct_sql("hit_1pct")
        bounded_type = conn.execute(
            f"DESCRIBE SELECT {bounded_sum} AS metric FROM hits"
        ).fetchone()
        assert bounded_type is not None
        assert bounded_type[1] == "BIGINT"
        assert conn.execute(f"SELECT {bounded_sum} FROM hits").fetchone() == (
            1186,
        )
    finally:
        conn.close()
