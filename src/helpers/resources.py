from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import PipelineConfig
from .data_models import FragmentType, RegisteredResource, ResourceGroup
from .files import find_files_by_extension
from .vars import HCR_XLSX_KEY_PREFIX, WORLD_BANK_XLSX_KEY


@dataclass
class PipelineResources:
    parquet_resources: dict[str, RegisteredResource]
    xlsx_resources: dict[str, RegisteredResource]
    world_bank_resource: RegisteredResource
    docx_resources: dict[str, RegisteredResource]


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


def discover_docx_files(docx_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in find_files_by_extension(docx_dir, "docx", recursive=False)
        if not path.name.startswith("~$")
    )


def configured_hcr_xlsx_entries(config: PipelineConfig) -> list[tuple[str, dict[str, str]]]:
    entries = [
        (key, value)
        for key, value in config.files_config.items()
        if key.startswith(HCR_XLSX_KEY_PREFIX)
    ]
    return sorted(entries, key=lambda item: item[0])


def configured_hcr_xlsx_paths(config: PipelineConfig) -> list[Path]:
    paths: list[Path] = []
    for _, meta in configured_hcr_xlsx_entries(config):
        path = Path(meta["path"])
        if path.name.startswith("~$"):
            continue
        paths.append(path)
    return paths


def register_pipeline_resources(config: PipelineConfig) -> PipelineResources:
    files = config.files_config
    parquet_resources = {
        Path(files["author_details"]["path"]).name: register_resource(
            Path(files["author_details"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
            description=files["author_details"]["desc"],
            expected_hash=files["author_details"]["sha256"],
        ),
        Path(files["authors"]["path"]).name: register_resource(
            Path(files["authors"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
            description=files["authors"]["desc"],
            expected_hash=files["authors"]["sha256"],
        ),
        Path(files["authors_paper"]["path"]).name: register_resource(
            Path(files["authors_paper"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description=files["authors_paper"]["desc"],
            expected_hash=files["authors_paper"]["sha256"],
        ),
        Path(files["hit_papers_0"]["path"]).name: register_resource(
            Path(files["hit_papers_0"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description=files["hit_papers_0"]["desc"],
            expected_hash=files["hit_papers_0"]["sha256"],
        ),
        Path(files["hit_papers_1"]["path"]).name: register_resource(
            Path(files["hit_papers_1"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description=files["hit_papers_1"]["desc"],
            expected_hash=files["hit_papers_1"]["sha256"],
        ),
        Path(files["fields"]["path"]).name: register_resource(
            Path(files["fields"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PARQUET_ROW,
            description=files["fields"]["desc"],
            expected_hash=files["fields"]["sha256"],
        ),
    }

    xlsx_files = configured_hcr_xlsx_paths(config)
    if not xlsx_files:
        raise FileNotFoundError(
            "No HCR XLSX files configured in files_config "
            f"(keys must start with '{HCR_XLSX_KEY_PREFIX}')."
        )
    xlsx_hashes = {
        Path(meta["path"]).name: meta["sha256"]
        for _, meta in configured_hcr_xlsx_entries(config)
        if "sha256" in meta and meta["sha256"]
    }
    xlsx_resources = register_resources(
        xlsx_files,
        group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
        fragment_type=FragmentType.EXCEL_ROW,
        description="HCR XLSX inputs",
        expected_hashes=xlsx_hashes,
    )
    if WORLD_BANK_XLSX_KEY not in files:
        raise KeyError(f"Missing '{WORLD_BANK_XLSX_KEY}' entry in files_config")
    world_bank_meta = files[WORLD_BANK_XLSX_KEY]
    world_bank_resource = register_resource(
        Path(world_bank_meta["path"]),
        group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
        fragment_type=FragmentType.EXCEL_ROW,
        description=world_bank_meta.get("desc", "World Bank country list"),
        expected_hash=world_bank_meta.get("sha256"),
    )
    docx_files = discover_docx_files(config.docx_dir)
    docx_resources = register_resources(
        docx_files,
        group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
        fragment_type=FragmentType.DOCX_ROW,
        description="KTP DOCX inputs",
    )

    return PipelineResources(
        parquet_resources=parquet_resources,
        xlsx_resources=xlsx_resources,
        world_bank_resource=world_bank_resource,
        docx_resources=docx_resources,
    )


__all__ = [
    "PipelineResources",
    "configured_hcr_xlsx_entries",
    "configured_hcr_xlsx_paths",
    "discover_docx_files",
    "register_pipeline_resources",
    "register_resource",
    "register_resources",
]
