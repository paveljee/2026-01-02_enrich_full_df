from __future__ import annotations

import json
from typing import Iterable


def dumps_jsonlines(rows: Iterable[dict]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)


def loads_jsonlines(payload: str) -> list[dict]:
    if not payload:
        return []
    lines = [line for line in payload.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]
