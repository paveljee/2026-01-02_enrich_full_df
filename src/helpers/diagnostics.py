from __future__ import annotations

from pathlib import Path


class DiagnosticsReport:
    def __init__(self, base_dir: Path) -> None:
        base_dir.mkdir(parents=True, exist_ok=True)
        self.path = base_dir / "repl_diagnostics.md"
        if not self.path.exists():
            self.path.write_text("# REPL Diagnostics Report\n\n", encoding="utf-8")

    def add_section(self, title: str, lines: list[str]) -> None:
        content = [f"## {title}", ""] + [f"- {line}" for line in lines] + [""]
        self.path.write_text(
            self.path.read_text(encoding="utf-8") + "\n".join(content),
            encoding="utf-8",
        )
