from __future__ import annotations

import json

from src.helpers.data_models import InnerDict, NameKey, OuterDict


class DummyProcedure:
    dataset_id_field = "ktp.source_key"


def test_outerdict_dump_json(tmp_path) -> None:
    key = NameKey(first_name="Ada", last_name="Lovelace").to_json_key()
    outer = OuterDict.from_name_keys([NameKey(first_name="Ada", last_name="Lovelace")])
    inner = InnerDict.from_mapping(
        {"ktp.filename": "file.xlsx", "ktp.fragment": "1"},
        DummyProcedure(),
    )
    outer.add_inner_by_key(key, inner)

    path = tmp_path / "outer.json"
    outer.dump_json(path)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert key in payload
    assert payload[key][0]["ktp.filename"] == "file.xlsx"
