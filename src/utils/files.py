from __future__ import annotations

from pathlib import Path


def find_files_by_extension(directory: Path, extension: str, recursive: bool = False) -> list[Path]:
    pattern = f"*.{extension}"
    if recursive:
        return list(directory.rglob(pattern))
    return list(directory.glob(pattern))
