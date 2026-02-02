from __future__ import annotations

from pathlib import Path

from ..data_models import FragmentType, RegisteredResource, ResourceGroup


def _compute_hash_via_resource(path: Path) -> str:
    probe = RegisteredResource(
        name=path.name,
        hash="pending",
        group=ResourceGroup.REGISTERED_SAMPLES,
        fragment_type=FragmentType.PARQUET_ROW,
        url=path.resolve().as_uri(),
        verify_hash_on_init=False,
    )
    return probe._compute_hash()


def register_resource(
    path: Path,
    *,
    group: ResourceGroup,
    fragment_type: FragmentType,
    description: str | None = None,
    expected_hash: str | None = None,
) -> RegisteredResource:
    resource_hash = expected_hash or _compute_hash_via_resource(path)
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
