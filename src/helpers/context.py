from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from ..config import PipelineConfig
from ..data_models import OuterDict
from .diagnostics import DiagnosticsReport
from .pipeline_manager import PipelineManager
from .resources import PipelineResources


@dataclass
class StepResult:
    step_id: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class PipelineContext:
    config: PipelineConfig
    manager: PipelineManager
    conn: duckdb.DuckDBPyConnection
    diagnostics: DiagnosticsReport
    interactive: bool
    artifacts_dir: Path
    resources: PipelineResources | None = None
    outer_dict: OuterDict | None = None
