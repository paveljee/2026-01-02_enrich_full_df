from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mark_expr = (config.option.markexpr or "").strip()
    if "slow" in mark_expr:
        return

    skip_slow = pytest.mark.skip(reason="slow test (run with: pytest -m slow)")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
