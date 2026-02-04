from __future__ import annotations

import pytest

from src.data_models import InnerDict, NameKey, OuterDict


class DummyProcedure:
    dataset_id_field = "ktp.source_key"


class BadProcedure:
    dataset_id_field = ""


def test_namekey_json_roundtrip_unicode() -> None:
    key = NameKey(first_name="Renee", last_name="O'Connor")
    json_key = key.to_json_key()
    restored = NameKey.from_json_key(json_key)
    assert restored.first_name == "Renee"
    assert restored.last_name == "O'Connor"


def test_innerdict_requires_dataset_id_field() -> None:
    with pytest.raises(ValueError, match="dataset_id_field"):
        InnerDict.from_mapping({"a": 1}, BadProcedure())


def test_outer_dict_add_ensure_items() -> None:
    ada = NameKey(first_name="Ada", last_name="Lovelace")
    grace = NameKey(first_name="Grace", last_name="Hopper")
    outer = OuterDict.from_name_keys([ada, grace])

    inner = InnerDict.from_mapping({"x": 1}, DummyProcedure())
    outer.add_inner(ada, inner)

    assert len(outer.get_inner_by_key(ada.to_json_key())) == 1
    assert outer.get_inner_by_key(grace.to_json_key()) == ()

    items = list(outer.items())
    assert items[0][0] == ada
    assert items[1][0] == grace
