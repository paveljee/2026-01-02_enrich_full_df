"""Run the existing completed-artifact checker on retained files, without a new agent run.

The card comes from the Dashboard's production renderer and saved query snapshot.
This exercises the checker's card branch, but is not a Playwright/browser rerun.
The shared checker also rebuilds the final replay log in isolation.
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_detour_db import (  # noqa: E501
    AiAugmentDetourDB,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_registered_resource import (  # noqa: E501
    RESOURCE_PATH_KEY,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.store import (  # noqa: E501
    AiAugmentBackendStore,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL,
    MAP_SUBSET_0_TO_BATCH_KEY,
    REPLAY_LOG_KEY,
    TEXT_ENCODING,
)
from src.detours.detour_ai_augment.protected.tests.operator.test_operator_e2e import (
    OperatorRuntime,
    assert_completed_workflow_artifacts,
    assert_final_replay_rebuilds,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.ai_augment_dashboard_storage import (  # noqa: E501
    BACKEND_DATABASE_STORAGE_KEY,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.data_models.dashboard_query_snapshot import (  # noqa: E501
    DashboardQuerySnapshot,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.ui import (
    _BackendDatabaseClient,
)
from src.helpers.data_models.outerdict import NameKey


def main(
    source: Path,
    *,
    expected_namekey: NameKey,
    scratch_dir: Path,
    pipeline_db: Path,
    map_subset_csv: Path,
    extension_platform: str,
    extension_bin: Path,
) -> None:
    source = source.resolve()
    with tempfile.TemporaryDirectory(prefix="artifact-check-", dir=scratch_dir) as temporary:
        local = Path(temporary).resolve()
        (local / "scisci_process.duckdb").symlink_to(pipeline_db.resolve())
        shutil.copy2(
            source / "scisci_process__detour_ai-augment.duckdb",
            local / "scisci_process__detour_ai-augment.duckdb",
        )
        shutil.copy2(source / "backend-replay.jsonl", local / "backend-replay.jsonl")
        shutil.copytree(source / "nicegui", local / "nicegui")
        config = json.loads((source / "config.operator.json").read_text(encoding=TEXT_ENCODING))
        config["db_file"] = str(local / "scisci_process.duckdb")
        config["state_file"] = str(local / "state.json")
        config["output_dir"] = str(local / "output")
        config["rollout_cas_dir"] = str(source / "rollout-cas")
        config["files_config"][REPLAY_LOG_KEY][RESOURCE_PATH_KEY] = str(
            local / "backend-replay.jsonl"
        )
        config["files_config"][MAP_SUBSET_0_TO_BATCH_KEY][RESOURCE_PATH_KEY] = str(
            map_subset_csv.resolve()
        )
        config["duckdb_extensions"]["splink_udfs"]["bin"][extension_platform] = str(
            extension_bin.resolve()
        )
        config_path = local / "config.operator.json"
        config_path.write_text(json.dumps(config), encoding=TEXT_ENCODING)
        parsed = AiAugmentDetourConfig.from_json(config_path, verify_hash_on_init=False)
        store = AiAugmentBackendStore._from_resources(
            replay_log=parsed.replay_log,
            detour_db=AiAugmentDetourDB.from_pipeline_db(
                parsed.db_file, duckdb_extensions=parsed.duckdb_extensions,
            ),
            rollout_cas=parsed.rollout_cas,
        )
        runtime = OperatorRuntime(
            repository_root=Path.cwd(),
            config_path=config_path,
            backend_store=store,
            replay_log_path=local / "backend-replay.jsonl",
            rollout_cas_dir=source / "rollout-cas",
            dashboard_socket_path=local / "dashboard.sock",
        )
        saved = json.loads(
            (local / "nicegui/storage-general.json").read_text(encoding=TEXT_ENCODING)
        )
        snapshot = DashboardQuerySnapshot.from_serialized_json(
            json.dumps(saved[BACKEND_DATABASE_STORAGE_KEY])
        )
        researcher = snapshot.researchers_by_namekey[expected_namekey.to_json_key()]
        card = _BackendDatabaseClient(
            socket_path=runtime.dashboard_socket_path,
            pipeline_config=parsed,
        ).card(researcher)
        marker = f"**`{KTP_AI_AUGMENT_RUN_OUTCOME_RESPONSE_BODY_COL}`**: `"
        rendered_outcome_body = card.split(marker, maxsplit=1)[1].split("`", maxsplit=1)[0]
        assert_completed_workflow_artifacts(
            runtime,
            namekey=expected_namekey,
            card_text=card,
            browser_run_outcome_response_body=rendered_outcome_body,
        )
        assert_final_replay_rebuilds(runtime)
        print("ARTIFACT_CHECK_PASSED (post-run assertions and backend replay; no browser)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Retained operator-artifact directory")
    parser.add_argument(
        "--expected-namekey", required=True, type=NameKey.from_json_key,
        help="Expected target NameKey as a JSON object, independent of the replay log",
    )
    parser.add_argument("--scratch-dir", type=Path, default=Path("tmp"))
    parser.add_argument("--pipeline-db", type=Path, default=Path("data/scisci_process.duckdb"))
    parser.add_argument("--map-subset-csv", type=Path, default=Path("tmp/map_subset0_to_batch.csv"))
    parser.add_argument("--extension-platform", default="linux_amd64")
    parser.add_argument(
        "--extension-bin", type=Path,
        default=Path.home()
        / ".duckdb/extensions/v1.5.1/linux_amd64/splink_udfs.duckdb_extension",
    )
    args = parser.parse_args()
    main(
        args.source,
        expected_namekey=args.expected_namekey,
        scratch_dir=args.scratch_dir,
        pipeline_db=args.pipeline_db,
        map_subset_csv=args.map_subset_csv,
        extension_platform=args.extension_platform,
        extension_bin=args.extension_bin,
    )
