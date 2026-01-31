from __future__ import annotations

import hashlib
from pathlib import Path

from .data_models import FragmentType, RegisteredResource, ResourceGroup


def compute_sha256(path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def register_resource(
    path: Path,
    *,
    group: ResourceGroup,
    fragment_type: FragmentType,
    description: str | None = None,
    expected_hash: str | None = None,
) -> RegisteredResource:
    resource_hash = expected_hash or compute_sha256(path)
    return RegisteredResource(
        name=path.name,
        hash=resource_hash,
        group=group,
        fragment_type=fragment_type,
        description=description,
        url=path.resolve().as_uri(),
        verify_hash_on_init=True,
    )


def register_resources(
    paths: list[Path],
    *,
    group: ResourceGroup,
    fragment_type: FragmentType,
    description: str | None = None,
    expected_hashes: dict[str, str] | None = None,
) -> dict[str, RegisteredResource]:
    resources: dict[str, RegisteredResource] = {}
    for path in paths:
        expected_hash = expected_hashes.get(path.name) if expected_hashes else None
        resources[path.name] = register_resource(
            path,
            group=group,
            fragment_type=fragment_type,
            description=description,
            expected_hash=expected_hash,
        )
    return resources
