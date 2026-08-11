from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import duckdb

from src.helpers.data_models import NameKey
from src.helpers.init_pipeline import init_pipeline
from src.helpers.jsonlines import dumps_jsonlines
from src.helpers.schema import (
    OUTERDICT_STUB_TABLE,
    PARQUET_INNERDICT_TABLE,
    PARQUET_LEGACY_ROWS_INNERDICT_TABLE,
)
from src.helpers.vars import (
    KTP_FRAGMENT_COL,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_NAMEKEY_COL,
    STEP_BUILD_OUTERDICT,
    STEP_MATCH_PARQUET,
)


def test_resume_hydrates_parquet_from_jsonlines_innerdict_table(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.helpers.init_pipeline as init_module
    import src.helpers.pipeline_manager as pipeline_manager_module

    source_key = NameKey(
        **{"ktp.first_name": "Ada", "ktp.last_name": "Lovelace"}
    ).to_json_key()
    db_file = tmp_path / "pipeline.duckdb"
    state_file = tmp_path / "pipeline_state.json"
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    state_file.write_text(
        json.dumps({"steps_completed": [STEP_BUILD_OUTERDICT, STEP_MATCH_PARQUET]}),
        encoding="utf-8",
    )

    conn = duckdb.connect(str(db_file))
    try:
        conn.execute(
            f'CREATE TABLE {OUTERDICT_STUB_TABLE} '
            f'("{KTP_NAMEKEY_COL}" VARCHAR)'
        )
        conn.execute(f"INSERT INTO {OUTERDICT_STUB_TABLE} VALUES (?)", [source_key])
        conn.execute(
            f'''
            CREATE TABLE {PARQUET_INNERDICT_TABLE} (
                "{KTP_NAMEKEY_COL}" VARCHAR,
                "{KTP_INNERDICT_JSONLINES_COL}" VARCHAR
            )
            '''
        )
        conn.execute(
            f"INSERT INTO {PARQUET_INNERDICT_TABLE} VALUES (?, ?)",
            [source_key, dumps_jsonlines([{KTP_FRAGMENT_COL: "A123"}])],
        )
        conn.execute(
            f'''
            CREATE TABLE {PARQUET_LEGACY_ROWS_INNERDICT_TABLE} (
                "{KTP_NAMEKEY_COL}" VARCHAR,
                "{KTP_FRAGMENT_COL}" VARCHAR
            )
            '''
        )
        conn.execute(
            f'INSERT INTO {PARQUET_LEGACY_ROWS_INNERDICT_TABLE} VALUES (?, ?)',
            [source_key, "legacy-value"],
        )
    finally:
        conn.close()

    config = SimpleNamespace(
        state_file=state_file,
        db_file=db_file,
        duckdb_extensions={},
    )
    monkeypatch.setattr(init_module.PipelineConfig, "from_json", staticmethod(lambda _path: config))
    monkeypatch.setattr(init_module, "register_pipeline_resources", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        pipeline_manager_module,
        "load_duckdb_extension",
        lambda *_args, **_kwargs: None,
    )

    result = init_pipeline(
        argparse.Namespace(config=config_path, new=False),
        interactive=False,
        reset_confirmed=False,
    )
    try:
        assert result.context.outer_dict is not None
        innerdicts = result.context.outer_dict.get_inner_by_key(source_key)
        assert len(innerdicts) == 1
        assert innerdicts[0].data == {KTP_FRAGMENT_COL: "A123"}
    finally:
        result.monitor.stop()
        result.context.manager.close()
