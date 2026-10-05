from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import duckdb
import pytest

from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    EXCLUDED_NAMEKEY,
    HTTP_POST_METHOD,
    INIT_PATH,
    MAP_SUBSET_0_TO_BATCH_KEY,
    NAME_KEY_HEADER,
    NANOSECONDS_PER_MICROSECOND,
    REPLAY_LOG_KEY,
    SYNTHETIC_COMMIT_HOST,
    SYNTHETIC_COMMIT_SCHEME,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.init_request import (
    BackendInitRequestRecord,
)
from src.detours.detour_ai_augment.src.shared import name_key_header_value
from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models import NameKey
from src.helpers.duckdb_utils import duckdb_quote_identifier as quote
from src.helpers.schema import (
    CARD_PARTITION_TABLE,
    DOCX_INNERDICT_TABLE,
    PARQUET_INNERDICT_TABLE,
    XLSX_INNERDICT_TABLE,
)
from src.helpers.vars import (
    BATCH_LABEL,
    DRAW_LABEL,
    KTP_FILENAME_COL,
    KTP_FIRST_NAME_COL,
    KTP_FRAGMENT_COL,
    KTP_FRAGMENT_TYPE_COL,
    KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
    KTP_INNERDICT_JSONLINES_COL,
    KTP_LAST_NAME_COL,
    KTP_NAMEKEY_COL,
    KTP_PARTITION_COL,
    KTP_PARTITION_FLAG_SSN_COUNT_COL,
    KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL,
)

ROOT = Path(__file__).resolve().parents[6]
STARTUP_NAMEKEY = NameKey(first_name="Case 000", last_name="Startup")


def init_request_record(namekey: NameKey) -> BackendInitRequestRecord:
    return BackendInitRequestRecord(
        schema_version=KTP_HTTP_REQUEST_LOG_SCHEMA_VERSION_V1_1,
        method=HTTP_POST_METHOD,
        scheme=SYNTHETIC_COMMIT_SCHEME,
        host=SYNTHETIC_COMMIT_HOST,
        port=None,
        path=INIT_PATH,
        query="",
        request_headers={NAME_KEY_HEADER: name_key_header_value(namekey)},
        request_body=None,
        response_code=None,
        response_headers=None,
        response_body=None,
        received_at_unix_usec=None,
        ready_to_respond_at_unix_usec=(
            time.time_ns() // NANOSECONDS_PER_MICROSECOND
        ),
        duration_usec=0,
    )


class StartupFiles(FrozenStrictModel):
    config: Path
    source: Path
    replay: Path
    detour: Path
    process_temp: Path

    def environment(self, namekey: str | None = STARTUP_NAMEKEY.to_json_key()) -> dict[str, str]:
        environment = dict(os.environ, TMPDIR=str(self.process_temp))
        environment.pop("FASTAPI_DETOUR_NAMEKEY", None)
        if namekey is not None:
            environment["FASTAPI_DETOUR_NAMEKEY"] = namekey
        return environment

    def repin(self) -> None:
        config = json.loads(self.config.read_text())
        config["files_config"][REPLAY_LOG_KEY]["sha256"] = hashlib.sha256(
            self.replay.read_bytes()
        ).hexdigest()
        self.config.write_text(json.dumps(config))


def source_population(path: Path, release_map: Path) -> None:
    """Synthetic source tables satisfy the real 307-person population invariants."""
    groups = (
        (196, "subset 1", 1, False, 0),
        (78, "unreleased", 4, False, 1),
        (1, "subset 1", 1, False, 0),  # the explicitly excluded duplicate identity
        (3, "subset 8", 1, False, 0),
        (7, "unreleased", 2, False, 0),
        (6, "unreleased", 4, True, 1),
        (16, "unreleased", 4, False, 2),
    )
    with duckdb.connect(str(path)) as connection, release_map.open("w") as mapping:
        writer = csv.writer(mapping)
        writer.writerow((DRAW_LABEL, BATCH_LABEL))
        for table in (XLSX_INNERDICT_TABLE, PARQUET_INNERDICT_TABLE, DOCX_INNERDICT_TABLE):
            connection.execute(
                f"CREATE TABLE {quote(table)} ("
                f"{quote(KTP_NAMEKEY_COL)} VARCHAR, {quote(KTP_INNERDICT_JSONLINES_COL)} VARCHAR)"
            )
        connection.execute(
            f"CREATE TABLE {quote(CARD_PARTITION_TABLE)} ("
            f"{quote(KTP_NAMEKEY_COL)} VARCHAR, {quote(KTP_PARTITION_COL)} INTEGER, "
            f"{quote(KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL)} BOOLEAN, "
            f"{quote(KTP_PARTITION_FLAG_SSN_COUNT_COL)} INTEGER)"
        )
        source_rows: list[tuple[str, str]] = []
        classifications: list[tuple[str, int, bool, int]] = []
        for count, batch, partition, nonexact, ssn_count in groups:
            for _ in range(count):
                index = len(source_rows)
                namekey = (
                    NameKey.from_json_key(EXCLUDED_NAMEKEY) if index == 274
                    else NameKey(first_name=f"Case {index:03}", last_name="Startup")
                )
                draws = (str(index), f"extra-{index}") if index < 5 else (str(index),)
                rows = []
                for draw in draws:
                    writer.writerow((draw, batch))
                    rows.append(json.dumps({
                        KTP_NAMEKEY_COL: namekey.to_json_key(),
                        KTP_FIRST_NAME_COL: namekey.first_name,
                        KTP_LAST_NAME_COL: namekey.last_name,
                        KTP_FILENAME_COL: "startup.xlsx",
                        KTP_FRAGMENT_COL: index + 1,
                        KTP_FRAGMENT_TYPE_COL: "csv_row",
                        DRAW_LABEL: draw,
                    }))
                source_rows.append((namekey.to_json_key(), "\n".join(rows)))
                classifications.append((namekey.to_json_key(), partition, nonexact, ssn_count))
        connection.executemany(f"INSERT INTO {quote(XLSX_INNERDICT_TABLE)} VALUES (?, ?)",
                               source_rows)
        connection.executemany(f"INSERT INTO {quote(CARD_PARTITION_TABLE)} VALUES (?, ?, ?, ?)",
                               classifications)


@pytest.fixture
def startup_files(tmp_path: Path) -> StartupFiles:
    from src.detours.detour_ai_augment.src.backend import server as backend_server
    from src.detours.detour_ai_augment.src.backend.helpers.data_models.ai_augment_backend_store import (  # noqa: E501
        initialize_backend_store,
    )

    source = tmp_path / "source.duckdb"
    release_map = tmp_path / "release-map.csv"
    source_population(source, release_map)
    replay = tmp_path / "replay.jsonl"
    replay.write_bytes(b"")
    config: dict[str, Any] = json.loads((ROOT / "config_ai_augment.json").read_text())
    config.update(db_file=str(source), output_dir=str(tmp_path / "output"),
                  state_file=str(tmp_path / "state.json"), rollout_cas_dir=str(tmp_path / "cas"))
    for key, path in ((MAP_SUBSET_0_TO_BATCH_KEY, release_map), (REPLAY_LOG_KEY, replay)):
        config["files_config"][key] = {
            "path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "desc": "isolated startup fixture",
        }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    runtime = backend_server.configure_runtime(config_path)
    with initialize_backend_store(
        runtime, ipc_only=False, init_request_record=init_request_record(STARTUP_NAMEKEY),
        new=True, confirmed=True,
        confirm_replay=lambda: False,
    ) as store:
        detour_path = store._detour_db_path
    source.chmod(0o400)
    process_temp = tmp_path / "process-temp"
    process_temp.mkdir()
    files = StartupFiles(
        config=config_path,
        source=source,
        replay=replay,
        detour=detour_path,
        process_temp=process_temp,
    )
    files.repin()
    return files
