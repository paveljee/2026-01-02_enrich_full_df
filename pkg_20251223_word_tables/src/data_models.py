import json
from typing import Any, Iterable, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._vars import KTP_FIRST_NAME_COL, KTP_LAST_NAME_COL


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

    data: dict[str, list[InnerDict]] = Field(default_factory=dict)

    @classmethod
    def from_name_keys(cls, name_keys: Iterable[NameKey]) -> "OuterDict":
        return cls(data={name_key.to_json_key(): [] for name_key in name_keys})

    def add_inner(self, name_key: NameKey, inner: InnerDict) -> None:
        self.data.setdefault(name_key.to_json_key(), []).append(inner)

    def add_inner_by_key(self, key: str, inner: InnerDict) -> None:
        self.data.setdefault(key, []).append(inner)

    def ensure_inner_list(self, name_key: NameKey) -> list[InnerDict]:
        return self.data.setdefault(name_key.to_json_key(), [])

    def ensure_inner_list_by_key(self, key: str) -> list[InnerDict]:
        return self.data.setdefault(key, [])

    def items(self) -> Iterable[tuple[NameKey, list[InnerDict]]]:
        for key, items in self.data.items():
            yield NameKey.from_json_key(key), items
