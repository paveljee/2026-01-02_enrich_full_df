from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from src.data_models import FragmentType, RegisteredResource, ResourceGroup


def compute_sha256(path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def register_resources(
    paths: Iterable[Path],
    *,
    group: ResourceGroup,
    fragment_type: FragmentType,
    description: str | None = None,
) -> dict[str, RegisteredResource]:
    resources: dict[str, RegisteredResource] = {}
    for path in paths:
        resource = RegisteredResource(
            name=path.name,
            hash=compute_sha256(path),
            group=group,
            fragment_type=fragment_type,
            description=description,
            url=path.resolve().as_uri(),
        )
        resources[path.name] = resource
    return resources


def register_resources_from_config(
    files_config: dict[str, dict[str, str]],
    *,
    group: ResourceGroup,
    fragment_type: FragmentType,
    fragment_type_overrides: dict[str, FragmentType] | None = None,
) -> dict[str, RegisteredResource]:
    resources: dict[str, RegisteredResource] = {}
    for key, conf in files_config.items():
        path = Path(conf["path"]).expanduser()
        fragment = fragment_type_overrides.get(key) if fragment_type_overrides else None
        resource = RegisteredResource(
            name=path.name,
            hash=conf["sha256"],
            group=group,
            fragment_type=fragment or fragment_type,
            description=conf.get("desc"),
            url=path.resolve().as_uri(),
        )
        resources[key] = resource
    return resources
