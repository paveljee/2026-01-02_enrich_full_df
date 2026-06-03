from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import duckdb

from .config import PipelineConfig
from .data_models import FragmentType, RegisteredResource, ResourceGroup
from .duckdb_utils import duckdb_string_literal
from .files import find_files_by_extension
from .name_matching import sciscinet_author_alt_name_key_exprs_sql
from .vars import (
    AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY,
    HCR_XLSX_KEY_PREFIX,
    KTP_ALT_NAME_COL,
    KTP_AUTHOR_DETAILS_UNNEST_KEY,
    OPENALEX_AUTHOR_SEARCH_LOG_KEY,
    SSNAD_AUTHORID_COL,
    SSNAD_RAW_AUTHORID_COL,
    SSNAD_RAW_DISPLAY_NAME_ALTERNATIVES_COL,
    SSNAD_RAW_DISPLAY_NAME_COL,
    WORLD_BANK_XLSX_KEY,
)


@dataclass
class PipelineResources:
    parquet_resources: dict[str, RegisteredResource]
    xlsx_resources: dict[str, RegisteredResource]
    world_bank_resource: RegisteredResource
    docx_resources: dict[str, RegisteredResource]
    openalex_author_search_log_resource: RegisteredResource
    author_details_unnest_resource: RegisteredResource | None = None
    messages: list[str] = field(default_factory=list)


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


def _author_details_unnest_default_path(config: PipelineConfig) -> Path:
    rule_version = config.match_rule_version.ssn_name
    return config.output_dir / f"{KTP_AUTHOR_DETAILS_UNNEST_KEY}_v{rule_version}.parquet"


def _read_author_details_unnest_rule_version(
    path: Path,
    *,
    conn: duckdb.DuckDBPyConnection | None,
) -> int:
    owns_conn = conn is None
    metadata_conn = duckdb.connect() if owns_conn else conn
    assert metadata_conn is not None
    try:
        row = metadata_conn.execute(
            """
            SELECT decode(value) AS rule_version
            FROM parquet_kv_metadata(?)
            WHERE decode(key) = ?
            """,
            [str(path), AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY],
        ).fetchone()
    finally:
        if owns_conn:
            metadata_conn.close()
    if row is None or row[0] is None:
        raise ValueError(
            f"Missing {AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY} parquet metadata "
            f"in {KTP_AUTHOR_DETAILS_UNNEST_KEY}: {path}"
        )
    return int(str(row[0]))


def _validate_author_details_unnest_metadata(
    path: Path,
    *,
    rule_version: int,
    conn: duckdb.DuckDBPyConnection | None,
) -> None:
    stored_version = _read_author_details_unnest_rule_version(path, conn=conn)
    if stored_version != rule_version:
        raise ValueError(
            f"{KTP_AUTHOR_DETAILS_UNNEST_KEY} was built with SSN name rule "
            f"version {stored_version!r}; config requires {rule_version}."
        )


def _create_author_details_unnest_parquet(
    conn: duckdb.DuckDBPyConnection,
    *,
    author_details_path: Path,
    output_path: Path,
    rule_version: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_sql = (
        "KV_METADATA {"
        f"{duckdb_string_literal(AUTHOR_DETAILS_UNNEST_RULE_VERSION_METADATA_KEY)}: ?"
        "}"
    )
    key_selects = []
    for key_expr in sciscinet_author_alt_name_key_exprs_sql(
        "r.raw_alt_name",
        rule_version=rule_version,
    ):
        key_selects.append(
            f"""
            SELECT
                r."{SSNAD_AUTHORID_COL}" AS "{SSNAD_AUTHORID_COL}",
                {key_expr} AS "{KTP_ALT_NAME_COL}"
            FROM raw_alt_names r
            """
        )
    expanded_sql = "\n            UNION ALL\n".join(key_selects)
    conn.execute(
        f"""
        COPY (
            WITH raw_alt_names AS (
                SELECT
                    ad."{SSNAD_RAW_AUTHORID_COL}" AS "{SSNAD_AUTHORID_COL}",
                    raw_alt.raw_alt_name AS raw_alt_name
                FROM read_parquet(?) ad
                CROSS JOIN UNNEST(
                    list_concat(
                        CASE
                            WHEN ad."{SSNAD_RAW_DISPLAY_NAME_COL}" IS NULL
                                THEN CAST([] AS VARCHAR[])
                            ELSE [CAST(ad."{SSNAD_RAW_DISPLAY_NAME_COL}" AS VARCHAR)]
                        END,
                        COALESCE(
                            CAST(
                                json(ad."{SSNAD_RAW_DISPLAY_NAME_ALTERNATIVES_COL}")
                                AS VARCHAR[]
                            ),
                            CAST([] AS VARCHAR[])
                        )
                    )
                ) AS raw_alt(raw_alt_name)
            ),
            expanded AS (
                {expanded_sql}
            )
            SELECT DISTINCT
                "{SSNAD_AUTHORID_COL}",
                "{KTP_ALT_NAME_COL}"
            FROM expanded
            WHERE "{KTP_ALT_NAME_COL}" IS NOT NULL
              AND trim(CAST("{KTP_ALT_NAME_COL}" AS VARCHAR)) <> ''
        ) TO ? (FORMAT PARQUET, {metadata_sql})
        """,
        [str(output_path), str(author_details_path), str(rule_version)],
    )


def _ensure_author_details_unnest_resource(
    config: PipelineConfig,
    *,
    conn: duckdb.DuckDBPyConnection | None,
    log: Callable[[str], None] | None = None,
) -> tuple[RegisteredResource | None, list[str]]:
    files = config.files_config
    rule_version = config.match_rule_version.ssn_name
    messages: list[str] = []
    meta = files.get(KTP_AUTHOR_DETAILS_UNNEST_KEY)
    if meta is not None:
        path = Path(meta["path"])
        resource = register_resource(
            path,
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=FragmentType.AUTHOR_ID,
            description=meta.get("desc", "SciSciNet author details unnested names"),
            expected_hash=meta.get("sha256"),
        )
        _validate_author_details_unnest_metadata(path, rule_version=rule_version, conn=conn)
        messages.append(f"Validated {KTP_AUTHOR_DETAILS_UNNEST_KEY}, rule version: {rule_version}")
        return resource, messages

    path = _author_details_unnest_default_path(config)
    if path.exists():
        _validate_author_details_unnest_metadata(path, rule_version=rule_version, conn=conn)
        resource = register_resource(
            path,
            group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
            fragment_type=FragmentType.AUTHOR_ID,
            description="SciSciNet author details unnested names",
        )
        messages.append(f"Reused {KTP_AUTHOR_DETAILS_UNNEST_KEY}: {path}")
        return resource, messages

    if conn is None:
        return None, messages

    author_details_path = Path(files["author_details"]["path"])
    if log is not None:
        log(
            "HEAVY step ahead: creating "
            f"{KTP_AUTHOR_DETAILS_UNNEST_KEY} from author_details display names "
            "and alternatives."
        )
        log(f"{KTP_AUTHOR_DETAILS_UNNEST_KEY} output: {path}")
        log(
            f"{KTP_AUTHOR_DETAILS_UNNEST_KEY} SSN name rule version: v{rule_version}"
        )
    _create_author_details_unnest_parquet(
        conn,
        author_details_path=author_details_path,
        output_path=path,
        rule_version=rule_version,
    )
    resource = register_resource(
        path,
        group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
        fragment_type=FragmentType.AUTHOR_ID,
        description="SciSciNet author details unnested names",
    )
    messages.append(f"Created {KTP_AUTHOR_DETAILS_UNNEST_KEY}: {path}")
    messages.append(f"{KTP_AUTHOR_DETAILS_UNNEST_KEY} sha256: {resource.hash}")
    return resource, messages


def _ensure_openalex_author_search_log_resource(
    config: PipelineConfig,
) -> tuple[RegisteredResource, list[str]]:
    meta = config.files_config[OPENALEX_AUTHOR_SEARCH_LOG_KEY]
    path = Path(meta["path"])
    resource = register_resource(
        path,
        group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
        fragment_type=FragmentType.CSV_ROW,
        description=meta.get("desc", "OpenAlex author search log"),
        expected_hash=meta.get("sha256"),
    )
    try:
        with path.open("r+", encoding="utf-8"):
            pass
    except OSError as exc:
        raise ValueError(
            f"Could not open {OPENALEX_AUTHOR_SEARCH_LOG_KEY} for append/update: {path}"
        ) from exc
    return resource, [f"Validated {OPENALEX_AUTHOR_SEARCH_LOG_KEY} writable log"]


def register_pipeline_resources(
    config: PipelineConfig,
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
    log: Callable[[str], None] | None = None,
) -> PipelineResources:
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
        Path(files["paper_author_affiliation"]["path"]).name: register_resource(
            Path(files["paper_author_affiliation"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PAPER_ID,
            description=files["paper_author_affiliation"]["desc"],
            expected_hash=files["paper_author_affiliation"]["sha256"],
        ),
        Path(files["affiliations"]["path"]).name: register_resource(
            Path(files["affiliations"]["path"]),
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.PARQUET_ROW,
            description=files["affiliations"]["desc"],
            expected_hash=files["affiliations"]["sha256"],
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
    author_details_unnest_resource, messages = _ensure_author_details_unnest_resource(
        config,
        conn=conn,
        log=log,
    )
    openalex_author_search_log_resource, openalex_messages = (
        _ensure_openalex_author_search_log_resource(config)
    )
    messages.extend(openalex_messages)
    if author_details_unnest_resource is not None:
        parquet_resources[author_details_unnest_resource.name] = author_details_unnest_resource

    return PipelineResources(
        parquet_resources=parquet_resources,
        xlsx_resources=xlsx_resources,
        world_bank_resource=world_bank_resource,
        docx_resources=docx_resources,
        author_details_unnest_resource=author_details_unnest_resource,
        openalex_author_search_log_resource=openalex_author_search_log_resource,
        messages=messages,
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
