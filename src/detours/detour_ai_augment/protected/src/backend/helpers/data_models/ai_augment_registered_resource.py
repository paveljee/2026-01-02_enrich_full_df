from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Self

from pydantic import ConfigDict

from src.helpers.data_models import FragmentType, RegisteredResource, ResourceGroup

from ..locale import Locale

RESOURCE_PATH_KEY = "path"
RESOURCE_DESCRIPTION_KEY = "desc"
RESOURCE_SHA256_KEY = "sha256"


class AiAugmentRegisteredResource(RegisteredResource):
    """Immutable AI-augment registered-resource metadata."""

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_config_entry(
        cls,
        metadata: object,
        *,
        resource_key: str,
        fragment_type: FragmentType,
        verify_hash_on_init: bool,
    ) -> Self:
        try:
            if not isinstance(metadata, Mapping):
                raise TypeError
            path_value = metadata[RESOURCE_PATH_KEY]
            hash_value = metadata[RESOURCE_SHA256_KEY]
            description_value = metadata[RESOURCE_DESCRIPTION_KEY]
            if not all(
                isinstance(value, str)
                for value in (path_value, hash_value, description_value)
            ):
                raise TypeError
            path = Path(path_value)
            return cls(
                name=path.name,
                hash=hash_value,
                group=ResourceGroup.KTP_PIPELINE_ARTIFACT,
                fragment_type=fragment_type,
                description=description_value,
                url=path.resolve().as_uri(),
                verify_hash_on_init=verify_hash_on_init,
            )
        except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ValueError(
                Locale.CONFIGURED_RESOURCE_INVALID_TEMPLATE.format(
                    resource_key=resource_key
                )
            ) from exc
