from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import requests
from pydantic import PrivateAttr

from src.helpers.architecture import FrozenStrictModel
from src.helpers.data_models.http_request_log import (
    HttpRequestLogRecord,
    redact_http_request_log_query,
)

RequestKey = tuple[str, str, str, int | None, str, str, tuple[tuple[str, str], ...], str | None]
RecordGet = Callable[..., HttpRequestLogRecord]


class ReplayInputMissing(RuntimeError):
    """Recorded model inputs cannot be resolved without new observations."""


class ModelHttpRequired(RuntimeError):
    """Suspend evaluation until the Store has durably recorded this request."""

    def __init__(self, request: requests.PreparedRequest, **kwargs: Any) -> None:
        self.request = request
        self.send_kwargs = kwargs
        super().__init__("Model HTTP input must be recorded")


def request_body(request: requests.PreparedRequest) -> str | None:
    body = request.body
    if isinstance(body, bytes):
        return body.decode("utf-8")
    if body is not None and not isinstance(body, str):
        raise ValueError("Model HTTP logging requires a text request body")
    return body


def request_key(request: requests.PreparedRequest) -> RequestKey:
    if request.url is None or request.method is None:
        raise ValueError("Prepared HTTP request is incomplete")
    target = urlsplit(request.url)
    return (request.method, target.scheme, target.hostname or "", target.port,
            target.path, redact_http_request_log_query(target.query),
            tuple(sorted((k.lower(), v) for k, v in request.headers.items())),
            request_body(request))


def record_key(record: HttpRequestLogRecord) -> RequestKey:
    return (record.method, record.scheme, record.host, record.port, record.path,
            redact_http_request_log_query(record.query),
            tuple(sorted((k.lower(), v) for k, v in record.request_headers.items())),
            record.request_body)


class ModelHttpInterceptor(FrozenStrictModel):
    """Generic HTTP adapter: the supplied resolver owns persistence, not this class."""

    record_get: RecordGet
    _used: dict[UUID, HttpRequestLogRecord] = PrivateAttr(default_factory=dict)
    _requests: dict[RequestKey, HttpRequestLogRecord] = PrivateAttr(default_factory=dict)

    @property
    def records(self) -> tuple[HttpRequestLogRecord, ...]:
        return tuple(self._used.values())

    @property
    def record_ids(self) -> tuple[UUID, ...]:
        return tuple(self._used)

    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
        key = request_key(request)
        record = self._requests.get(key)
        if record is None:
            record = self.record_get(request, **kwargs)
            if record_key(record) != key:
                raise ReplayInputMissing("Recorded response does not match its request")
            self._requests[key] = record
        self._used[record.record_id] = record
        return record.to_response()

    @classmethod
    def current(cls) -> ModelHttpInterceptor:
        # Unscoped restoration is fail-closed, never a live transport fallback.
        current = _current.get()
        return current if current is not None else cls.from_records(())

    @classmethod
    def from_records(cls, records: Sequence[HttpRequestLogRecord]) -> ModelHttpInterceptor:
        by_request: dict[RequestKey, HttpRequestLogRecord] = {}
        for record in records:
            key = record_key(record)
            previous = by_request.get(key)
            if previous is not None and previous.record_id != record.record_id:
                raise ReplayInputMissing("Ambiguous model HTTP response references")
            by_request[key] = record

        def get(request: requests.PreparedRequest, **_kwargs: Any) -> HttpRequestLogRecord:
            try:
                return by_request[request_key(request)]
            except KeyError as exc:
                raise ReplayInputMissing("Missing referenced model HTTP response") from exc

        return cls(record_get=get)


_current: ContextVar[ModelHttpInterceptor | None] = ContextVar("model_http", default=None)


class _Session(requests.Session):
    def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
        current = _current.get()
        if current is None:
            return super().send(request, **kwargs)
        allow_redirects = kwargs.pop("allow_redirects", True)
        response = current.send(request, **kwargs)
        if allow_redirects:
            history = list(self.resolve_redirects(response, request, **kwargs))
            if history:
                history.insert(0, response)
                response = history.pop()
                response.history = history
        return response


class RequestsBinding:
    """Replace only the model module's requests binding; other threads remain untouched."""

    Session = _Session
    session = _Session

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        if _current.get() is None:
            return requests.request(method, url, **kwargs)
        with _Session() as session:
            return session.request(method, url, **kwargs)

    def __getattr__(self, name: str) -> Any:
        if _current.get() is None:
            return getattr(requests, name)
        if name in {"get", "post", "put", "patch", "delete", "head", "options"}:
            return lambda url, **kwargs: self.request(name.upper(), url, **kwargs)
        return getattr(requests, name)


@contextmanager
def model_http_context(http: ModelHttpInterceptor) -> Iterator[None]:
    token = _current.set(http)
    try:
        yield
    finally:
        _current.reset(token)
