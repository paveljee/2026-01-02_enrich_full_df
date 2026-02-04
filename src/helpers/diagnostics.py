from __future__ import annotations

from datetime import datetime
from pathlib import Path


class DiagnosticsReport:
    def __init__(self, base_dir: Path) -> None:
        base_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = base_dir / f"repl_diagnostics_{timestamp}.md"
        self.path.write_text("# REPL Diagnostics Report\n\n", encoding="utf-8")

    def add_section(self, title: str, lines: list[str]) -> None:
        content = [f"## {title}", ""] + [f"- {line}" for line in lines] + [""]
        self.path.write_text(
            self.path.read_text(encoding="utf-8") + "\n".join(content),
            encoding="utf-8",
        )
