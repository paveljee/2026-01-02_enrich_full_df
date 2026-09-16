from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_serializer,
    model_validator,
)

from src.detours.detour_ai_augment.protected.src.architecture import (
    BackendComponent,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import (
    Locale,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    DOCX_COLUMNS,
    AiAugmentCohort,
    AiAugmentIneligibilityCategory,
)
from src.helpers.architecture import FrozenStrictModel, implements
from src.helpers.data_models import (
    InnerDict,
    NameKey,
)
from src.helpers.procedures import (
    DocxMatchProcedure,
    ParquetMatchProcedure,
    XlsxMatchProcedure,
)
from src.helpers.vars import (
    DRAW_LABEL,
    KTP_DOCX_OPTIONAL_EMPTY_COLS,
)

from ....control_centre.dashboard.helpers.data_models.run_outcome import (
    NAME_KEY_HEADER,
    name_key_from_header_value,
)
from .committed_innerdict import CommittedInnerDict, _CommittedInnerDictJson


class _AiAugmentSingularOuterDictJson(FrozenStrictModel):
    namekey: NameKey
    xlsx_innerdicts: tuple[dict[str, Any], ...]
    ssn_innerdicts: tuple[dict[str, Any], ...]
    docx_innerdicts: tuple[dict[str, Any], ...]
    committed_innerdicts: tuple[_CommittedInnerDictJson, ...]
    ai_augment_rnd: int = Field(ge=1)
    ai_augment_cohort: AiAugmentCohort
    ai_augment_ineligibility_category: AiAugmentIneligibilityCategory | None

    @classmethod
    def from_ai_augment_singular_outerdict(cls, value: AiAugmentSingularOuterDict) -> Self:
        return cls(
            namekey=value.namekey,
            xlsx_innerdicts=tuple(
                innerdict.data for innerdict in value.xlsx_innerdicts
            ),
            ssn_innerdicts=tuple(
                innerdict.data for innerdict in value.ssn_innerdicts
            ),
            docx_innerdicts=tuple(
                innerdict.data for innerdict in value.docx_innerdicts
            ),
            committed_innerdicts=tuple(
                _CommittedInnerDictJson.from_committed_innerdict(innerdict)
                for innerdict in value.committed_innerdicts
            ),
            ai_augment_rnd=value.ai_augment_rnd,
            ai_augment_cohort=value.ai_augment_cohort,
            ai_augment_ineligibility_category=(
                value.ai_augment_ineligibility_category
            ),
        )


@implements[BackendComponent.ControlCentrePort.AiAugmentSingularOuterDictProperty]()
class AiAugmentSingularOuterDict(BaseModel):
    """Note `validate_assignment=True` and `frozen=False`"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        strict=True,
        validate_assignment=True,
    )

    namekey: NameKey
    ai_augment_rnd: int = Field(ge=1)
    ai_augment_cohort: AiAugmentCohort
    ai_augment_ineligibility_category: AiAugmentIneligibilityCategory | None = None
    xlsx_innerdicts: tuple[InnerDict, ...]
    ssn_innerdicts: tuple[InnerDict, ...]
    docx_innerdicts: tuple[InnerDict, ...]
    committed_innerdicts: tuple[CommittedInnerDict, ...] = ()

    @property
    def draw_numbers(self) -> tuple[str, ...]:
        return tuple(
            sorted({
                str(value).strip()
                for innerdict in (
                    *self.xlsx_innerdicts,
                    *self.ssn_innerdicts,
                    *self.docx_innerdicts,
                )
                if (value := innerdict.data.get(DRAW_LABEL)) is not None
                and str(value).strip()
            })
        )

    @property
    def draw_number(self) -> str:
        return ", ".join(self.draw_numbers)

    def validate_ai_augment_singular_outerdict(self) -> Self:
        if (
            self.ai_augment_cohort is AiAugmentCohort.INELIGIBLE
        ) is not (self.ai_augment_ineligibility_category is not None):
            raise ValueError("AI augment eligibility classification is inconsistent")
        if not self.xlsx_innerdicts:
            raise ValueError("AI augment XLSX source rows are missing")
        commit_ids = tuple(
            committed.commit_record.record_id
            for committed in self.committed_innerdicts
        )
        if len(set(commit_ids)) != len(commit_ids):
            raise ValueError("AI augment committed innerdict IDs are duplicated")
        if commit_ids != tuple(sorted(commit_ids, key=lambda value: value.int)):
            raise ValueError("AI augment committed innerdicts are not ordered")
        for committed in self.committed_innerdicts:
            committed_namekey = name_key_from_header_value(
                committed.commit_record.request_headers.get(NAME_KEY_HEADER)
            )
            if committed_namekey != self.namekey:
                raise ValueError(
                    "AI augment committed innerdict has "
                    "a different namekey in request headers"
                )
        return self

    def ground_truth_innerdict(self) -> InnerDict | None:
        if self.ai_augment_cohort is AiAugmentCohort.NO_GROUND_TRUTH:
            return None
        required_columns = tuple(
            column
            for column in DOCX_COLUMNS
            if column not in KTP_DOCX_OPTIONAL_EMPTY_COLS
        )
        complete_rows = tuple(
            innerdict
            for innerdict in self.docx_innerdicts
            if all(
                column in innerdict.data
                and bool(str(innerdict.data[column]).strip())
                for column in required_columns
            )
        )
        if not complete_rows:
            raise ValueError(Locale.GROUND_TRUTH_DOCX_INCOMPLETE)
        return complete_rows[0]

    @model_validator(mode="after")
    def _validate_ai_augment_singular_outerdict(self) -> Self:
        return self.validate_ai_augment_singular_outerdict()

    @classmethod
    def from_serialized(cls, value: Mapping[str, object]) -> Self:
        serialized = _AiAugmentSingularOuterDictJson.model_validate_json(json.dumps(value))
        return cls(
            namekey=serialized.namekey,
            xlsx_innerdicts=tuple(
                InnerDict.from_mapping(innerdict, XlsxMatchProcedure())
                for innerdict in serialized.xlsx_innerdicts
            ),
            ssn_innerdicts=tuple(
                InnerDict.from_mapping(innerdict, ParquetMatchProcedure())
                for innerdict in serialized.ssn_innerdicts
            ),
            docx_innerdicts=tuple(
                InnerDict.from_mapping(innerdict, DocxMatchProcedure())
                for innerdict in serialized.docx_innerdicts
            ),
            committed_innerdicts=tuple(
                CommittedInnerDict.from_serialized(innerdict.model_dump(mode="json"))
                for innerdict in serialized.committed_innerdicts
            ),
            ai_augment_rnd=serialized.ai_augment_rnd,
            ai_augment_cohort=serialized.ai_augment_cohort,
            ai_augment_ineligibility_category=(
                serialized.ai_augment_ineligibility_category
            ),
        )

    def serialize(self) -> dict[str, object]:
        return _AiAugmentSingularOuterDictJson.from_ai_augment_singular_outerdict(self).model_dump(
            mode="json"
        )

    @model_serializer
    def _serialize(self) -> dict[str, object]:
        return self.serialize()
