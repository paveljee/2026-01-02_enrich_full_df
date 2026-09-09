from __future__ import annotations

import argparse
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from . import api, ipc
from .helpers.locale import Locale

CONFIG_OPTION = "--config"
IPC_ONLY_OPTION = "--ipc-only"


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    api._acquire_backend_process_lock()
    try:
        if args.ipc_only:
            ipc.serve_dashboard_query_only(args.config)
        else:
            api.configure_runtime(args.config)
            uvicorn.run(
                full_backend_application(),
                host=api.SERVER_HOST,
                port=api.SERVER_PORT,
            )
    finally:
        api._release_backend_process_lock()


if __name__ == "__main__":
    main()
