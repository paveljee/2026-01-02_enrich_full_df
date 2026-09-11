from __future__ import annotations

import argparse
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale

from . import api, ipc

CONFIG_OPTION = "--config"
IPC_ONLY_OPTION = "--ipc-only"
DANGER_NO_VERIFY_HASH_OPTION = "--danger-no-verify-hash"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    async with api.lifespan(app):
        dashboard_query_server = ipc.start_full_dashboard_query_server()
        try:
            yield
        finally:
            ipc.stop_dashboard_query_server(dashboard_query_server)


def full_backend_application() -> FastAPI:
    api.app.router.lifespan_context = lifespan
    return api.app


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
        if args.ipc_only:
            ipc.serve_dashboard_query_only(
                args.config,
                verify_hash_on_init=verify_hash_on_init,
            )
        else:
            api.configure_runtime(
                args.config,
                verify_hash_on_init=verify_hash_on_init,
            )
            uvicorn.run(
                full_backend_application(),
                host=api.SERVER_HOST,
                port=api.SERVER_PORT,
            )
    finally:
        api._release_backend_process_lock()


if __name__ == "__main__":
    main()
