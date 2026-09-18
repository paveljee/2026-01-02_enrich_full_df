from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import Future
from enum import StrEnum
from typing import Annotated, NoReturn, Self

from pydantic import PrivateAttr

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models.http_request_log import HttpRequestLogRecord

logger = logging.getLogger(__name__)


@implements[BackendComponent.StoreAcknowledgmentProperty]()
class BackendStoreAcknowledgment(StrEnum):
    ACK = "ack"
    NAK = "nak"


@implements[BackendComponent.StoreExceptionProperty]()
class BackendStoreException(RuntimeError):
    def raise_exception(self) -> NoReturn:
        raise self

    @classmethod
    def _from_exception(cls, error: Exception) -> Self:
        wrapped = cls(str(error))
        wrapped.__cause__ = error
        return wrapped


# Exposed to structural type-checking through `@implements`
# under `ResponseRecordPromise.response_record`'s return type;
# signed off: human
type ResponseRecordPromiseResult[R] = Annotated[
    tuple[R, None] | tuple[None, BackendStoreException],
    "Compatible with BackendComponent.ResponseRecordPromiseResultProperty[R]",
]


@implements[BackendComponent.ResponseRecordPromiseProperty[HttpRequestLogRecord]]()
class ResponseRecordPromise[R: HttpRequestLogRecord](FrozenStrictModel):
    """Request durability and a shielded, Store-owned application result.

    The initial handle is not completion. Required response persistence precedes
    a successful result; failures resolve to (None, exc), independently of ACK/NAK.
    Awaiter cancellation never cancels the Store's completion work.
    """

    acknowledgment: BackendStoreAcknowledgment
    _result: ResponseRecordPromiseResult[R] | None = PrivateAttr(default=None)
    _future: Future[ResponseRecordPromiseResult[R]] | None = PrivateAttr(default=None)

    @classmethod
    def _resolved(
        cls,
        acknowledgment: BackendStoreAcknowledgment,
        result: ResponseRecordPromiseResult[R],
    ) -> Self:
        promise = cls(acknowledgment=acknowledgment)
        promise._result = result
        return promise

    @classmethod
    def _start(
        cls,
        acknowledgment: BackendStoreAcknowledgment,
        work: Callable[[], R],
        loop: asyncio.AbstractEventLoop,
    ) -> Self:
        promise = cls(acknowledgment=acknowledgment)

        async def complete() -> ResponseRecordPromiseResult[R]:
            try:
                return await asyncio.to_thread(work), None
            except Exception as error:
                logger.exception(Locale.STORE_RESPONSE_PROCESSING_FAILED_LOG)
                return None, BackendStoreException._from_exception(error)

        promise._future = asyncio.run_coroutine_threadsafe(complete(), loop)
        return promise

    async def response_record(self) -> ResponseRecordPromiseResult[R]:
        if self._result is not None:
            return self._result
        if self._future is None:
            raise BackendStoreException(Locale.STORE_PROMISE_COMPLETION_MISSING)
        return await asyncio.shield(asyncio.wrap_future(self._future))
