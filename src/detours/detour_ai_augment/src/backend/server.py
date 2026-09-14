from __future__ import annotations

import argparse
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI

from src.detours.detour_ai_augment.protected.src.backend import ipc
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.ai_augment_config import (  # noqa: E501
    AiAugmentDetourConfig,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale

from . import api
from .helpers.data_models.ai_augment_context import AiAugmentBackendContext

CONFIG_OPTION = "--config"
IPC_ONLY_OPTION = "--ipc-only"
DANGER_NO_VERIFY_HASH_OPTION = "--danger-no-verify-hash"


@asynccontextmanager
async def lifespan(
    app: FastAPI,
    runtime: AiAugmentBackendContext,
) -> AsyncGenerator[None, None]:
    async with api.lifespan(app, runtime):
        dashboard_query_server = ipc.start_full_dashboard_query_server(runtime)
        try:
            yield
        finally:
            ipc.stop_dashboard_query_server(dashboard_query_server)


def full_backend_application(runtime: AiAugmentBackendContext) -> FastAPI:
    @asynccontextmanager
    async def application_lifespan(
        app: FastAPI,
    ) -> AsyncGenerator[None, None]:
        async with lifespan(app, runtime):
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
    try:
        pipeline = AiAugmentDetourConfig.from_json(
            config_path,
            verify_hash_on_init=verify_hash_on_init,
        )
    except (OSError, ValueError) as exc:
        raise api._PushConfigurationError(
            Locale.CONFIG_INVALID_TEMPLATE.format(config_path=config_path)
        ) from exc
    if pipeline.output_format not in api.SUPPORTED_OUTPUT_FORMATS:
        raise api._PushConfigurationError(Locale.OUTPUT_FORMAT_INVALID)
    if not pipeline.db_file.is_file() or not os.access(pipeline.db_file, os.R_OK):
        raise api._PushConfigurationError(
            Locale.SOURCE_DUCKDB_UNREADABLE_TEMPLATE.format(
                db_file=pipeline.db_file
            )
        )
    if pipeline.output_format == api.DOCX_OUTPUT_FORMAT and (
        not pipeline.pandoc_reference_docx.is_file()
        or not os.access(pipeline.pandoc_reference_docx, os.R_OK)
    ):
        raise api._PushConfigurationError(Locale.DOCX_REFERENCE_UNREADABLE)
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
    try:
        singular_outerdicts = runtime.ai_augment_singular_outerdicts
        if configured_namekey is not None:
            api._configured_ai_augment_singular_outerdict(
                configured_namekey,
                singular_outerdicts,
            )
    except ValueError as exc:
        raise api._PushConfigurationError(str(exc)) from exc
    return runtime


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=Locale.CLI_DESCRIPTION)
    parser.add_argument(CONFIG_OPTION, required=True, type=Path)
    parser.add_argument(IPC_ONLY_OPTION, action="store_true")
    parser.add_argument(DANGER_NO_VERIFY_HASH_OPTION, action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    verify_hash_on_init = not args.danger_no_verify_hash
    api._acquire_backend_process_lock()
    try:
        runtime = configure_runtime(
            args.config,
            require_namekey=not args.ipc_only,
            verify_hash_on_init=verify_hash_on_init,
        )
        if args.ipc_only:
            with runtime.pipeline_config.backend_store.read_only():
                ipc.serve_dashboard_query_only(runtime)
        else:
            uvicorn.run(
                full_backend_application(runtime),
                host=api.SERVER_HOST,
                port=api.SERVER_PORT,
            )
    finally:
        api._release_backend_process_lock()


if __name__ == "__main__":
    main()
