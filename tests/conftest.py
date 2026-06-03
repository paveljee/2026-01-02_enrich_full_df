from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mark_expr = (config.option.markexpr or "").strip()
    slow_requested = "slow" in mark_expr or "real_api" in mark_expr
    real_api_requested = "real_api" in mark_expr

    skip_slow = pytest.mark.skip(reason="slow test (run with: pytest -m slow)")
    skip_real_api = pytest.mark.skip(reason="real_api test (run with: pytest -m real_api)")
    for item in items:
        if not real_api_requested and "real_api" in item.keywords:
            item.add_marker(skip_real_api)
        elif not slow_requested and "slow" in item.keywords:
            item.add_marker(skip_slow)
