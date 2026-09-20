from __future__ import annotations

from typing import Literal, Self

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.helpers.architecture import FrozenStrictModel, implements


@implements[BackendComponent.QueryRequestProperty]()
class QueryRequest(FrozenStrictModel):
    """Request the complete Backend snapshot, without filters or a request body."""

    def outbound_http(self) -> tuple[Literal["GET"], Literal["/query"]]:
        return "GET", "/query"

    @classmethod
    def from_http_request(
        cls, *, method: str, path: str, query: bytes, body: bytes,
    ) -> Self:
        request = cls()
        if (method, path) != request.outbound_http() or query or body:
            raise ValueError("Query requires GET /query without parameters or a body")
        return request
