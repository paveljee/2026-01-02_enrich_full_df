import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from ..vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL


class MatchingProcedure(Protocol):
    """Interface for dataset matching procedures used to build inner dicts."""

    dataset_id_field: str


class NameKey(BaseModel):
    """Typed name key that serializes to the JSON string used in OuterDict keys."""

    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(alias=KTP_FIRST_NAME_COL)
    last_name: str = Field(alias=KTP_LAST_NAME_COL)

    def to_json_key(self) -> str:
        return json.dumps(self.model_dump(by_alias=True), sort_keys=True)

    @classmethod
    def from_json_key(cls, key: str) -> "NameKey":
        return cls.model_validate(json.loads(key))


class InnerDict(BaseModel):
    """Wrapper for dataset rows with validation of the matching procedure."""

    data: dict[str, Any]
    procedure: Any

    @model_validator(mode="after")
    def validate_procedure(self) -> "InnerDict":
        dataset_id_field = getattr(self.procedure, "dataset_id_field", None)
        if not isinstance(dataset_id_field, str) or not dataset_id_field:
            raise ValueError("matching procedure must define a non-empty dataset_id_field")
        return self

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any], procedure: MatchingProcedure) -> "InnerDict":
        return cls(data=dict(mapping), procedure=procedure)


class OuterDict(BaseModel):
    """Outer dict mapping JSON-serialized NameKey strings to inner dict lists."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    _data: dict[str, list[InnerDict]] = PrivateAttr(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        data = kwargs.pop("data", None)
        super().__init__(**kwargs)
        if data is None:
            self._data = {}
        else:
            self._data = {key: list(value) for key, value in data.items()}

    @property
    def data(self) -> Mapping[str, tuple[InnerDict, ...]]:
        return MappingProxyType({k: tuple(v) for k, v in self._data.items()})

    @classmethod
    def from_name_keys(cls, name_keys: Iterable[NameKey]) -> "OuterDict":
        return cls(data={name_key.to_json_key(): [] for name_key in name_keys})

    def add_inner(self, name_key: NameKey, inner: InnerDict) -> None:
        self._data.setdefault(name_key.to_json_key(), []).append(inner)

    def add_inner_by_key(self, key: str, inner: InnerDict) -> None:
        self._data.setdefault(key, []).append(inner)

    def get_inner_by_key(self, key: str) -> tuple[InnerDict, ...]:
        return tuple(self._data.get(key, []))

    def items(self) -> Iterable[tuple[NameKey, tuple[InnerDict, ...]]]:
        for key, items in self._data.items():
            yield NameKey.from_json_key(key), tuple(items)

    def keys(self) -> Iterable[str]:
        return self._data.keys()

    def values(self) -> Iterable[tuple[InnerDict, ...]]:
        return (tuple(items) for items in self._data.values())

    def to_serializable(self) -> dict[str, list[dict[str, Any]]]:
        return {key: [inner.data for inner in items] for key, items in self._data.items()}

    def dump_json(self, path: str | Path) -> None:
        from pathlib import Path

        target = Path(path)
        target.write_text(
            json.dumps(self.to_serializable(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
