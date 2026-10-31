from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field


class LimaMount(BaseModel):
    """Note `extra="ignore"`"""

    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    location: str
    mount_point: str = Field(alias="mountPoint")


class LimaConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    param: Mapping[str, str]
    mounts: tuple[LimaMount, ...]
