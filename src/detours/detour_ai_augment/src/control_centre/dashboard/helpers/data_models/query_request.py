from __future__ import annotations

from src.detours.detour_ai_augment.protected.src.architecture import (
    ControlCentreComponent,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import NameKey


@implements[ControlCentreComponent.BackendPort.QueryRequestProperty]()
class QueryRequest(FrozenStrictModel):
    namekey: NameKey | None
