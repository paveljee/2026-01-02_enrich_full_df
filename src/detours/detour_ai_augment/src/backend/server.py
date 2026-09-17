from __future__ import annotations

import argparse
import logging
import os
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI
from rich.console import Console

from src.detours.detour_ai_augment.protected.src.backend import ipc
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    BACKEND_STORE_CLOSED_CLEANLY,
)

from . import api
from .helpers.data_models.ai_augment_backend_store import AiAugmentBackendStore
from .helpers.data_models.ai_augment_context import AiAugmentBackendContext

CONFIG_OPTION = "--config"
IPC_ONLY_OPTION = "--ipc-only"
DANGER_NO_VERIFY_HASH_OPTION = "--danger-no-verify-hash"
logger = logging.getLogger(__name__)


@contextmanager
def backend_store_lifecycle(
    runtime: AiAugmentBackendContext, *, new: bool, confirmed: bool, yes: bool = False,
) -> Iterator[AiAugmentBackendStore]:
    if not confirmed:
        raise ValueError("Backend startup confirmation required; use --yes to bypass the prompt.")
    acquired_lock = api.BACKEND_PROCESS_LOCK_DESCRIPTOR is None
    if acquired_lock:
        api._acquire_backend_process_lock()
    try:
        store = runtime.pipeline_config.backend_store
        logger.info("Opening writable Backend Store: new=%s", new)
        if new:
            store.rebuild_from_log(
                runtime, reset_confirmed=confirmed,
                confirm_replay=lambda: confirm_nonempty_replay(yes=yes),
            )
        with store.writable(runtime):
            logger.info("Writable Backend Store ready")
            yield store
    finally:
        if acquired_lock:
            api._release_backend_process_lock()
    # Not reached on failed startup, application, task settlement or resource cleanup.
    logger.info("Writable Backend Store closed cleanly")
    print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)


@asynccontextmanager
async def lifespan(
    app: FastAPI, runtime: AiAugmentBackendContext, *,
    new: bool, confirmed: bool, yes: bool = False,
) -> AsyncGenerator[None, None]:
    with backend_store_lifecycle(runtime, new=new, confirmed=confirmed, yes=yes):
        async with api.lifespan(app, runtime):
            dashboard_query_server = ipc.start_full_dashboard_query_server(runtime)
            try:
                yield
            finally:
                ipc.stop_dashboard_query_server(dashboard_query_server)


def full_backend_application(
    runtime: AiAugmentBackendContext, *, new: bool, confirmed: bool, yes: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def application_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with lifespan(app, runtime, new=new, confirmed=confirmed, yes=yes):
            yield

    api.app.state.runtime = runtime
    api.app.router.lifespan_context = application_lifespan
    return api.app


def configure_runtime(
    config_path: Path,
    *,
    require_namekey: bool = True,
    verify_hash_on_init: bool = True,
) -> AiAugmentBackendContext:
    logger.info("Loading Backend configuration/resources: %s; verify_hashes=%s",
                config_path, verify_hash_on_init)
    try:
        pipeline = AiAugmentDetourConfig.from_json(
            config_path,
            verify_hash_on_init=verify_hash_on_init,
        )
    except (OSError, ValueError) as exc:
        raise api._PushConfigurationError(
            Locale.CONFIG_INVALID_TEMPLATE.format(config_path=config_path)
        ) from exc
    if not pipeline.db_file.is_file() or not os.access(pipeline.db_file, os.R_OK):
        raise api._PushConfigurationError(
            Locale.SOURCE_DUCKDB_UNREADABLE_TEMPLATE.format(
                db_file=pipeline.db_file
            )
        )
    try:
        ZoneInfo(pipeline.timezone)
    except (KeyError, ValueError) as exc:
        raise api._PushConfigurationError(
            Locale.TIMEZONE_INVALID_TEMPLATE.format(timezone=pipeline.timezone)
        ) from exc

    configured_namekey = api._configured_namekey() if require_namekey else None
    runtime = AiAugmentBackendContext(
        pipeline_config=pipeline,
        configured_namekey=configured_namekey,
    )
    logger.info("Loading researchers from read-only source DB: %s", pipeline.db_file)
    try:
        singular_outerdicts = runtime.ai_augment_singular_outerdicts
        if configured_namekey is not None:
            api._configured_ai_augment_singular_outerdict(
                configured_namekey,
                singular_outerdicts,
            )
    except ValueError as exc:
        raise api._PushConfigurationError(str(exc)) from exc
    logger.info("Backend runtime ready: %d researchers; selected=%s",
                len(singular_outerdicts), configured_namekey)
    return runtime


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=Locale.CLI_DESCRIPTION)
    parser.add_argument(CONFIG_OPTION, required=True, type=Path)
    parser.add_argument(IPC_ONLY_OPTION, action="store_true")
    parser.add_argument(DANGER_NO_VERIFY_HASH_OPTION, action="store_true")
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--resume", "--continue", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args(argv)
    if args.ipc_only:
        # Initialization flags have no effect in query-only mode.
        args.new = False
        args.resume = False
    elif args.new == args.resume:
        parser.error("Full Backend requires exactly one of --new or --resume/--continue")
    return args


def confirm_startup(args: argparse.Namespace) -> bool:
    if args.yes:
        return True
    prompt = (
        "Recreate the AI augment detour database from the replay log? [y/N] "
        if args.new else "Resume the AI augment detour database without rebuilding? [y/N] "
    )
    try:
        confirmed = Console().input(prompt, markup=False).strip().lower() == "y"
    except EOFError:
        confirmed = False
    if not confirmed:
        raise ValueError("Backend startup confirmation required; use --yes to bypass the prompt.")
    return True


def confirm_nonempty_replay(*, yes: bool) -> bool:
    if yes:
        return True
    try:
        return Console().input(
            "Registered a nonempty replay log. Replay it into the new database? [y/N] ",
            markup=False,
        ).strip().lower() == "y"
    except EOFError:
        return False


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args(argv)
    logger.info("Starting Backend: config=%s; ipc_only=%s; new=%s; resume=%s",
                args.config, args.ipc_only, args.new, args.resume)
    confirmed = False if args.ipc_only else confirm_startup(args)
    verify_hash_on_init = not args.danger_no_verify_hash
    api._acquire_backend_process_lock()
    try:
        runtime = configure_runtime(
            args.config,
            require_namekey=not args.ipc_only,
            verify_hash_on_init=verify_hash_on_init,
        )
        if args.ipc_only:
            logger.info("Opening read-only Backend Store: %s",
                        runtime.pipeline_config.backend_store.detour_db_path)
            with runtime.pipeline_config.backend_store.read_only():
                logger.info("Read-only Backend Store ready; starting query-only IPC")
                ipc.serve_dashboard_query_only(runtime)
            logger.info("Query-only IPC stopped; read-only Backend Store closed cleanly")
            print(BACKEND_STORE_CLOSED_CLEANLY, flush=True)
        else:
            logger.info("Starting Backend HTTP API at %s:%s", api.SERVER_HOST, api.SERVER_PORT)
            uvicorn.run(
                full_backend_application(
                    runtime, new=args.new, confirmed=confirmed, yes=args.yes,
                ),
                host=api.SERVER_HOST,
                port=api.SERVER_PORT,
            )
    except BaseException:
        logger.exception("Backend failed; exiting without recovery")
        raise
    finally:
        api._release_backend_process_lock()
        logger.info("Backend process lock released")


if __name__ == "__main__":
    main()
