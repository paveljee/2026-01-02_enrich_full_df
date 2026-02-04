from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import PipelineConfig
from ..data_models import FragmentType, RegisteredResource, ResourceGroup
from ..utils.files import find_files_by_extension
from ..utils.resources import register_resource, register_resources


@dataclass
class PipelineResources:
    parquet_resources: dict[str, RegisteredResource]
    xlsx_resources: dict[str, RegisteredResource]
    world_bank_resource: RegisteredResource
    docx_resources: dict[str, RegisteredResource]


def discover_xlsx_files(xlsx_dir: Path) -> list[Path]:
    return sorted(find_files_by_extension(xlsx_dir, "xlsx", recursive=False))


def discover_docx_files(docx_dir: Path) -> list[Path]:
    return sorted(find_files_by_extension(docx_dir, "docx", recursive=False))


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

    xlsx_files = discover_xlsx_files(config.xlsx_dir)
    xlsx_resources = register_resources(
        xlsx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.EXCEL_ROW,
        description="HCR XLSX inputs",
    )
    world_bank_resource = register_resource(
        config.world_bank_xlsx,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.EXCEL_ROW,
        description="World Bank country list",
    )
    docx_files = discover_docx_files(config.docx_dir)
    docx_resources = register_resources(
        docx_files,
        group=ResourceGroup.KTP_PILOT_SAMPLE,
        fragment_type=FragmentType.DOCX_ROW,
        description="KTP DOCX inputs",
    )

    return PipelineResources(
        parquet_resources=parquet_resources,
        xlsx_resources=xlsx_resources,
        world_bank_resource=world_bank_resource,
        docx_resources=docx_resources,
    )
