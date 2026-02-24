from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .vars import HCR_XLSX_KEY_PREFIX, REQUIRED_FILE_ENTRY_KEYS, REQUIRED_FILES_CONFIG_KEYS


class SampleDrawSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    size: int = Field(gt=0)
    replace: bool


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files_config: dict[str, dict[str, str]]
    db_file: Path
    state_file: Path
    output_dir: Path
    output_format: str
    pandoc_reference_docx: Path
    docx_dir: Path
    timezone: str
    sample_seed: int
    sample_draw_sizes: list[SampleDrawSpec]
    pilot_xlsx_name: str
    total_draws: int
    card_subset_mode: int

    @field_validator("sample_draw_sizes", mode="before")
    @classmethod
    def _normalize_sample_draw_sizes(
        cls, value: object
    ) -> list[int | dict[str, object]] | object:
        if not isinstance(value, list):
            return value
        normalized: list[int | dict[str, object]] = []
        for entry in value:
            if isinstance(entry, int):
                normalized.append({"size": entry, "replace": False})
            else:
                normalized.append(entry)
        return normalized

    @model_validator(mode="after")
    def _validate_files_config(self) -> PipelineConfig:
        if not self.files_config:
            raise ValueError(
                "Config must define non-empty 'files_config' with paths/hashes/descriptions."
            )

        missing_required_keys = sorted(REQUIRED_FILES_CONFIG_KEYS - set(self.files_config.keys()))
        if missing_required_keys:
            raise ValueError(
                "files_config missing required keys: " + ", ".join(missing_required_keys)
            )

        if not any(key.startswith(HCR_XLSX_KEY_PREFIX) for key in self.files_config):
            raise ValueError(
                "files_config must include at least one HCR XLSX entry "
                f"with key prefix '{HCR_XLSX_KEY_PREFIX}'."
            )

        for key, meta in self.files_config.items():
            if not isinstance(meta, dict):
                raise ValueError(f"files_config['{key}'] must be an object.")
            missing_entry_keys = sorted(REQUIRED_FILE_ENTRY_KEYS - set(meta.keys()))
            if missing_entry_keys:
                raise ValueError(
                    f"files_config['{key}'] missing required fields: "
                    + ", ".join(missing_entry_keys)
                )
            for required_key in REQUIRED_FILE_ENTRY_KEYS:
                value = meta.get(required_key)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(
                        f"files_config['{key}']['{required_key}'] must be a non-empty string."
                    )
        return self

    @classmethod
    def from_json(cls, path: Path) -> PipelineConfig:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
