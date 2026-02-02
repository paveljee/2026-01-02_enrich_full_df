from __future__ import annotations

from pathlib import Path

import duckdb

from src._vars import KTP_FILENAME_COL
from src.data_models import FragmentType, NameKey, OuterDict, ResourceGroup
from src.sciscinet_parquet.matcher import match_parquet
from src.utils.name_keys import NAME_KEY_COL
from src.utils.resources import register_resource


def _write_parquet(path: Path, create_sql: str, insert_sql: str) -> None:
    conn = duckdb.connect()
    try:
        conn.execute(create_sql)
        conn.execute(insert_sql)
        conn.execute(f"COPY (SELECT * FROM input) TO '{path}' (FORMAT 'parquet')")
    finally:
        conn.close()


def test_match_parquet_builds_records(tmp_path: Path) -> None:
    author_details = tmp_path / "author_details.parquet"
    authors_paper = tmp_path / "authors_paper.parquet"
    hit0 = tmp_path / "hit_level0.parquet"
    hit1 = tmp_path / "hit_level1.parquet"

    _write_parquet(
        author_details,
        "CREATE TABLE input(authorid VARCHAR, display_name VARCHAR, display_name_alternatives VARCHAR)",
        """
        INSERT INTO input VALUES
            ('A1', 'Ada Lovelace', '["A. Lovelace"]'),
            ('A2', 'Alan Turing', '["A. Turing"]');
        """,
    )
    _write_parquet(
        authors_paper,
        "CREATE TABLE input(authorid VARCHAR, paperid VARCHAR)",
        """
        INSERT INTO input VALUES
            ('A1', 'P1'),
            ('A1', 'P2'),
            ('A2', 'P3');
        """,
    )
    _write_parquet(
        hit0,
        "CREATE TABLE input(paperid VARCHAR, fieldid VARCHAR, hit_1pct INTEGER)",
        """
        INSERT INTO input VALUES
            ('P1', 'F1', 1),
            ('P2', 'F2', 1);
        """,
    )
    _write_parquet(
        hit1,
        "CREATE TABLE input(paperid VARCHAR, fieldid VARCHAR, hit_1pct INTEGER)",
        """
        INSERT INTO input VALUES
            ('P2', 'F2', 1),
            ('P3', 'F3', 1);
        """,
    )

    name_key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    sample_df = pd.DataFrame(
        {
            NAME_KEY_COL: [name_key],
            "hcr.first_name": ["Ada"],
            "hcr.last_name": ["Lovelace"],
        }
    )
    outer = OuterDict.from_name_keys([NameKey(first_name="Ada", last_name="Lovelace")])

    resources = {
        author_details.name: register_resource(
            author_details,
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
        )
    }

    conn = duckdb.connect()
    try:
        match_parquet(
            conn,
            outer,
            sample_df,
            resources,
            author_details_path=str(author_details),
            authors_paper_path=str(authors_paper),
            hit_papers_level0_path=str(hit0),
            hit_papers_level1_path=str(hit1),
        )
    finally:
        conn.close()

    assert name_key in outer.data
    assert len(outer.data[name_key]) == 1

    record = outer.data[name_key][0].data
    assert record["authorid"] == "A1"
    assert record[KTP_FILENAME_COL] == author_details.name
    assert "ktp.source_key" in record
