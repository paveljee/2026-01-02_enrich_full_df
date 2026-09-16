import os
import threading
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generic, Protocol, Self, TypeVar, cast

from pydantic import BaseModel

from src.detours.detour_ai_augment.src.backend.helpers.data_models.model_http_interceptor import (  # noqa: E501
    ModelHttpInterceptor,
    RequestsBinding,
    model_http_context,
)

from ..vars import (
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_LINKS_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
)


class ValueSubmission(Protocol):
    value: str


# to be supplied by `pydantic_to_paste` downstream
TFieldSubmission = TypeVar("TFieldSubmission", bound=ValueSubmission)
TCommentsSubmission = TypeVar("TCommentsSubmission", bound=ValueSubmission)


class SubmissionMixin(Generic[TFieldSubmission, TCommentsSubmission]):
    researcher_author: TFieldSubmission
    place_of_residence: TFieldSubmission
    race_ethnicity_language_culture: TFieldSubmission
    gender: TFieldSubmission
    age_first_publication: TFieldSubmission
    education: TFieldSubmission
    academic_positions: TFieldSubmission
    social_capital: TFieldSubmission
    links: TFieldSubmission
    comments: TCommentsSubmission | None

    @classmethod
    def model_validate_with_http_records(
        cls,
        value: str | bytes,
        *,
        http: ModelHttpInterceptor | None = None,
    ) -> Self:
        with submission_http_context(http if http is not None else ModelHttpInterceptor.current()):
            model = cast(type[BaseModel], cls)
            return cast(Self, model.model_validate_json(value))

    def evidence_items(self) -> tuple[tuple[str, "TFieldSubmission"], ...]:
        return (
            (KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL, self.researcher_author),
            (KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL, self.place_of_residence),
            (
                KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
                self.race_ethnicity_language_culture,
            ),
            (KTP_AI_AUGMENT_GENDER_COL, self.gender),
            (KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL, self.age_first_publication),
            (KTP_AI_AUGMENT_EDUCATION_COL, self.education),
            (KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL, self.academic_positions),
            (KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL, self.social_capital),
            (KTP_AI_AUGMENT_LINKS_COL, self.links),
        )

    def normalized_values(self) -> dict[str, str]:
        values = {column: field.value for column, field in self.evidence_items()}
        if self.comments is not None:
            values[KTP_AI_AUGMENT_COMMENTS_COL] = self.comments.value
        return values


# The pasted validator reads a credential and mutates its module-level params before
# making HTTP calls. Keep that provider-specific adaptation out of generic transport.
_openalex_params: ContextVar[dict[str, str | None] | None] = ContextVar(
    "submission_openalex_params", default=None
)
_install_lock = threading.Lock()
_installed = False


class _OsBinding:
    def getenv(self, key: str, default: str | None = None) -> str | None:
        if _openalex_params.get() is not None and key == "OPENALEX_API_KEY":
            # Replay needs no secret. The live Store adds credentials at capture only.
            return "REDACTED"
        return os.getenv(key, default)


class _ParamsBinding(MutableMapping[str, str | None]):
    def __init__(self, original: dict[str, str | None]) -> None:
        self.original = original

    def _mapping(self) -> dict[str, str | None]:
        current = _openalex_params.get()
        return self.original if current is None else current

    def __getitem__(self, key: str) -> str | None:
        return self._mapping()[key]

    def __setitem__(self, key: str, value: str | None) -> None:
        self._mapping()[key] = value

    def __delitem__(self, key: str) -> None:
        del self._mapping()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping())

    def __len__(self) -> int:
        return len(self._mapping())


@contextmanager
def submission_http_context(http: ModelHttpInterceptor) -> Iterator[None]:
    global _installed
    with _install_lock:
        if not _installed:
            from . import pydantic_to_paste

            # Change only this module's bindings, never requests.get or os.environ.
            setattr(pydantic_to_paste, "requests", RequestsBinding())
            setattr(pydantic_to_paste, "os", _OsBinding())
            setattr(pydantic_to_paste, "OPENALEX_PARAMS",
                    _ParamsBinding(dict(pydantic_to_paste.OPENALEX_PARAMS)))
            _installed = True
    token = _openalex_params.set({})
    try:
        with model_http_context(http):
            yield
    finally:
        _openalex_params.reset(token)
