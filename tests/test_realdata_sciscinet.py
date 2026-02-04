from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from src._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL
from src.data_models import FragmentType, NameKey, OuterDict, RegisteredResource, ResourceGroup
from src.sciscinet_parquet.matcher import match_parquet
from src.utils.name_keys import NAME_KEY_COL
from tests.real_data_utils import (
    SCISCINET_AUTHOR_DETAILS,
    SCISCINET_AUTHORS_PAPER,
    SCISCINET_HIT_LEVEL0,
    SCISCINET_HIT_LEVEL1,
    list_sample_csv_files,
)


def _build_sample_df(csv_path, limit: int = 25) -> pd.DataFrame | None:
    df = pd.read_csv(csv_path)
    if df.empty:
        return None
    df = df.head(limit).copy()

    if KTP_FIRST_NAME_COL in df.columns and KTP_LAST_NAME_COL in df.columns:
        first_col = KTP_FIRST_NAME_COL
        last_col = KTP_LAST_NAME_COL
    elif "hcr.first_name" in df.columns and "hcr.last_name" in df.columns:
        first_col = "hcr.first_name"
        last_col = "hcr.last_name"
    else:
        return None

    df["hcr.first_name"] = df[first_col].astype(str)
    df["hcr.last_name"] = df[last_col].astype(str)
    df[NAME_KEY_COL] = df.apply(
        lambda row: NameKey(
            first_name=str(row["hcr.first_name"]),
            last_name=str(row["hcr.last_name"]),
        ).to_json_key(),
        axis=1,
    )
    return df[[NAME_KEY_COL, "hcr.first_name", "hcr.last_name"]]


def test_sciscinet_parquet_real_data() -> None:
    if not (
        SCISCINET_AUTHOR_DETAILS.exists()
        and SCISCINET_AUTHORS_PAPER.exists()
        and SCISCINET_HIT_LEVEL0.exists()
        and SCISCINET_HIT_LEVEL1.exists()
    ):
        pytest.skip("SciSciNet parquet files not available.")

    csv_files = list_sample_csv_files(limit=1)
    if not csv_files:
        pytest.skip("Sample CSV files not available for SciSciNet matching.")

    sample_df = _build_sample_df(csv_files[0])
    if sample_df is None:
        pytest.skip("Sample CSV missing required name columns.")

    outer = OuterDict.from_name_keys(
        [NameKey.from_json_key(key) for key in sample_df[NAME_KEY_COL]]
    )

    # Avoid hashing multi-GB parquet files during tests.
    author_resource = RegisteredResource(
        name=SCISCINET_AUTHOR_DETAILS.name,
        hash="skip",
        group=ResourceGroup.SCISCINET_HF,
        fragment_type=FragmentType.AUTHOR_ID,
        url=SCISCINET_AUTHOR_DETAILS.resolve().as_uri(),
        verify_hash_on_init=False,
    )

    conn = duckdb.connect()
    try:
        conn.execute("INSTALL splink_udfs FROM community; LOAD splink_udfs;")
        match_parquet(
            conn,
            outer,
            sample_df,
            {author_resource.name: author_resource},
            author_details_path=str(SCISCINET_AUTHOR_DETAILS),
            authors_paper_path=str(SCISCINET_AUTHORS_PAPER),
            hit_papers_level0_path=str(SCISCINET_HIT_LEVEL0),
            hit_papers_level1_path=str(SCISCINET_HIT_LEVEL1),
        )
    finally:
        conn.close()

    assert any(inner_list for inner_list in outer.data.values())
