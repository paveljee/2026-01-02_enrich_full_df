from __future__ import annotations

import hashlib
from pathlib import Path


def file_hash(path: Path, *, algorithm: str = "sha256") -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def file_sha256(path: Path) -> str:
    return file_hash(path, algorithm="sha256")


def find_files_by_extension(directory: Path, extension: str, recursive: bool = False) -> list[Path]:
    pattern = f"*.{extension}"
    if recursive:
        return list(directory.rglob(pattern))
    return list(directory.glob(pattern))


__all__ = ["file_hash", "file_sha256", "find_files_by_extension"]
