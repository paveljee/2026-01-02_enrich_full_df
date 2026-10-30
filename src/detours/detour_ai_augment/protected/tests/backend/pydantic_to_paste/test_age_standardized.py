import json
from datetime import date
from typing import Final
from uuid import UUID

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from src.detours.detour_ai_augment.protected.src.backend.helpers.codex_parse import (
    render_standardized_submission_value,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models import (
    pydantic_to_paste as schema,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.post_commit_validation import (  # noqa: E501
    _age_evidence_violations,
    _assessment_public_detail,
    _CodexFcoRow,
    _CodexFcRow,
    _CodexTurnRefRow,
    _EvidenceAssessment,
    _RolloutIndex,
    _SessionMetadata,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.data_models.pydantic_to_paste import (  # noqa: E501
    EARLIEST_YEAR,
    HCR_CUTOFF_YEAR,
    HUMAN_LIFESPAN,
    LATEST_BIRTH_YEAR,
    Age,
    AgeAtDeathFromBirth,
    AgeAtDeathFromFirstPublication,
    AgeFromBirth,
    AgeFromFirstPublication,
    AgeSensitivityInterval,
    AgeStandardized,
    BiologicalAgeAtDeath,
    BirthComputation,
    BirthToDeathComputation,
    ComputedNumeral,
    CurrentAgeFromFirstPublication,
    CurrentBiologicalAge,
    DateOfBirth,
    DateOfDeath,
    DateOfFirstPublication,
    FirstPublicationComputation,
    FirstPublicationToDeathComputation,
    PublicationSpanAtDeath,
    ReportedNumeral,
)
from src.detours.detour_ai_augment.protected.src.backend.helpers.locale import Locale
from src.detours.detour_ai_augment.protected.src.backend.helpers.vars import (
    COMPACT_JSON_SEPARATORS,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    NOT_REPORTED_VALUE,
)
from src.detours.detour_ai_augment.src.control_centre.dashboard.helpers.render import (
    martin_serialize_standardized_cell,
)

NR: Final = NOT_REPORTED_VALUE
FIELD_VALUE_FIELD, FIELD_EVIDENCE_FIELD = schema.FieldSubmission.model_fields
(FIELD_STANDARDIZED_VALUE_FIELD,) = (
    schema.StandardizedFieldSubmission.model_fields.keys()
    - schema.FieldSubmission.model_fields.keys()
)
TEST_EVIDENCE = [
    {"excerpt": "Exact cited text.", "url": "https://example.test/result"}
]
AS_OF = date(2026, 10, 27)


def birth_age(birth: DateOfBirth, reported: str, as_of: date = AS_OF) -> AgeFromBirth:
    inferred = birth.infer_age(as_of)
    assert isinstance(inferred, CurrentBiologicalAge)
    return AgeFromBirth(
        age=ComputedNumeral(
            computed=BirthComputation(
                basis="birth",
                birth=ReportedNumeral[DateOfBirth](reported=reported, inferred=birth),
                as_of=as_of,
            ),
            inferred=inferred,
        ),
    )


def publication_age(
    publication: DateOfFirstPublication, reported: str, as_of: date = AS_OF
) -> AgeFromFirstPublication:
    inferred = publication.infer_age(as_of)
    assert isinstance(inferred, CurrentAgeFromFirstPublication)
    return AgeFromFirstPublication(
        age=ComputedNumeral(
            computed=FirstPublicationComputation(
                basis="first_publication",
                first_publication=ReportedNumeral[DateOfFirstPublication](
                    reported=reported, inferred=publication
                ),
                as_of=as_of,
            ),
            inferred=inferred,
        ),
    )


@pytest.mark.parametrize(
    (
        "basis", "counterpart", "reported", "reported_numeral",
        "as_of", "expected_age", "variant",
    ),
    (
        (
            "birth", "birth", "1976",
            {"year": 1976, "month": NR, "day": NR},
            "2026-10-19", {"lower": 49, "upper": 50}, AgeFromBirth,
        ),
        (
            "birth", "birth", "1 Dec 1976",
            {"year": 1976, "month": 12, "day": 1},
            "2026-10-19", 49, AgeFromBirth,
        ),
        (
            "first_publication", "first_publication", "2005",
            {"year": 2005, "month": NR, "day": NR},
            "2026-10-19", {"lower": 20, "upper": 21},
            AgeFromFirstPublication,
        ),
        (
            "first_publication", "first_publication", "1 Nov 2005",
            {"year": 2005, "month": 11, "day": 1},
            "2026-10-19", 20, AgeFromFirstPublication,
        ),
    ),
)
def test_age_standardized_accepts_reported_basis_and_computed_age(
    basis: str,
    counterpart: str,
    reported: str,
    reported_numeral: dict[str, int | str],
    as_of: str,
    expected_age: int | dict[str, int],
    variant: type[BaseModel],
) -> None:
    payload = {
        FIELD_VALUE_FIELD: "Plain-text research value.",
        FIELD_STANDARDIZED_VALUE_FIELD: {
            "age": {
                "provenance": "computed",
                "computed": {
                    "basis": basis,
                    counterpart: {
                        "provenance": "reported",
                        "reported": reported,
                        "inferred": reported_numeral,
                    },
                    "as_of": as_of,
                },
                "inferred": expected_age,
            },
        },
        FIELD_EVIDENCE_FIELD: TEST_EVIDENCE,
    }
    parsed = schema.AgeFirstPublicationSubmission.model_validate_json(
        json.dumps(payload)
    )

    assert type(parsed.standardized_value) is variant
    assert parsed.standardized_value.model_dump(mode="json") == payload[
        FIELD_STANDARDIZED_VALUE_FIELD
    ]
    assert schema.AgeFirstPublicationSubmission.model_validate_json(
        parsed.model_dump_json()
    ) == parsed


@pytest.mark.parametrize(
    ("basis", "source_key", "reported", "source_date", "expected", "martin_expected"),
    (
        (
            "birth", "birth", "October 1968",
            {"year": 1968, "month": 10, "day": NR},
            {"lower": 57, "upper": 58},
            "**AI-generated text**:\n\n```\n"
            "57, 58\ncomputed\n  2026-10-27\n  birth\n"
            "    1968, 10, NR\n    reported\n    October 1968\n```",
        ),
        (
            "first_publication", "first_publication", "2005",
            {"year": 2005, "month": NR, "day": NR},
            {"lower": 20, "upper": 21},
            "**AI-generated text**:\n\n```\n"
            "20, 21\ncomputed\n  2026-10-27\n  first_publication\n"
            "    2005, NR, NR\n    reported\n    2005\n```",
        ),
    ),
)
def test_operator_age_examples_serialize_exactly(
    basis: str,
    source_key: str,
    reported: str,
    source_date: dict[str, int | str],
    expected: dict[str, int],
    martin_expected: str,
) -> None:
    payload = {
        "age": {
            "provenance": "computed",
            "computed": {
                "basis": basis,
                source_key: {
                    "provenance": "reported",
                    "reported": reported,
                    "inferred": source_date,
                },
                "as_of": "2026-10-27",
            },
            "inferred": expected,
        }
    }
    adapter: TypeAdapter[AgeStandardized] = TypeAdapter(AgeStandardized)
    value = adapter.validate_json(json.dumps(payload))
    assert isinstance(value, (AgeFromBirth, AgeFromFirstPublication))
    assert value.model_dump(mode="json") == payload
    canonical = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=COMPACT_JSON_SEPARATORS,
    )
    rendered = render_standardized_submission_value(canonical)
    assert martin_serialize_standardized_cell(rendered) == martin_expected


@pytest.mark.parametrize(
    ("inferred_age", "birth_provenance", "age_provenance"),
    (
        (49, "reported", "computed"),
        (50, "computed", "computed"),
        (50, "reported", "reported"),
    ),
)
def test_age_standardized_rejects_wrong_computation_or_provenance(
    inferred_age: int,
    birth_provenance: str,
    age_provenance: str,
) -> None:
    payload = {
        FIELD_VALUE_FIELD: "Plain-text research value.",
        FIELD_STANDARDIZED_VALUE_FIELD: {
            "age": {
                "provenance": age_provenance,
                "computed": {
                    "basis": "birth",
                    "birth": {
                        "provenance": birth_provenance,
                        "reported": "1 Oct 1976",
                        "inferred": {"year": 1976, "month": 10, "day": 1},
                    },
                    "as_of": "2026-10-19",
                },
                "inferred": inferred_age,
            },
        },
        FIELD_EVIDENCE_FIELD: TEST_EVIDENCE,
    }

    with pytest.raises(ValidationError):
        schema.AgeFirstPublicationSubmission.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    ("basis", "counterpart"),
    (("birth", "first_publication"), ("first_publication", "birth")),
)
def test_age_standardized_rejects_mismatched_computation_basis(
    basis: str,
    counterpart: str,
) -> None:
    payload = {
        FIELD_VALUE_FIELD: "Plain-text research value.",
        FIELD_STANDARDIZED_VALUE_FIELD: {
            "age": {
                "provenance": "computed",
                "computed": {
                    "basis": basis,
                    counterpart: {
                        "provenance": "reported",
                        "reported": "1 Oct 1976",
                        "inferred": {"year": 1976, "month": 10, "day": 1},
                    },
                    "as_of": "2026-10-19",
                },
                "inferred": 50,
            },
        },
        FIELD_EVIDENCE_FIELD: TEST_EVIDENCE,
    }

    with pytest.raises(ValidationError):
        schema.AgeFirstPublicationSubmission.model_validate_json(json.dumps(payload))


def test_complete_date_is_a_real_date() -> None:
    value = DateOfBirth(year=2000, month=10, day=27)
    assert value.as_date() == date(2000, 10, 27)
    assert value.bounds() == (date(2000, 10, 27), date(2000, 10, 27))


def test_year_only_bounds() -> None:
    value = DateOfBirth(year=2000, month=NR, day=NR)
    assert value.bounds() == (date(2000, 1, 1), date(2000, 12, 31))


def test_year_and_month_bounds() -> None:
    value = DateOfFirstPublication(year=2024, month=2, day=NR)
    assert value.bounds() == (date(2024, 2, 1), date(2024, 2, 29))


def test_incomplete_dates_cannot_be_converted_to_exact_date() -> None:
    for value in (
        DateOfBirth(year=2000, month=NR, day=NR),
        DateOfBirth(year=2000, month=10, day=NR),
    ):
        with pytest.raises(ValueError, match="incomplete"):
            value.as_date()


def test_year_is_mandatory() -> None:
    with pytest.raises(ValidationError):
        DateOfBirth.model_validate({"month": NR, "day": NR})
    with pytest.raises(ValidationError):
        DateOfBirth.model_validate({"year": NR, "month": NR, "day": NR})


def test_day_requires_month() -> None:
    with pytest.raises(ValidationError, match="Day requires reported month"):
        DateOfBirth(year=2000, month=NR, day=27)


@pytest.mark.parametrize(
    "month, day",
    [
        (0, 1), (13, 1), (1, 0), (1, 32),
        (4, 31), (2, 30),
    ],
)
def test_invalid_months_and_days(month: int, day: int) -> None:
    with pytest.raises(ValidationError):
        DateOfBirth(year=2000, month=month, day=day)


def test_leap_year_calendar_validation() -> None:
    assert DateOfBirth(year=2000, month=2, day=29).as_date() == date(2000, 2, 29)
    with pytest.raises(ValidationError):
        DateOfBirth(year=2001, month=2, day=29)


@pytest.mark.parametrize(
    "field, value",
    [("year", "2000"), ("month", "10"), ("day", "27"), ("day", True)],
)
def test_date_components_are_strict(field: str, value: str | bool) -> None:
    data: dict[str, int | str | bool] = dict(year=2000, month=10, day=27)
    data[field] = value
    with pytest.raises(ValidationError):
        DateOfBirth.model_validate(data)


def test_year_lower_bound_and_specific_upper_bounds() -> None:
    with pytest.raises(ValidationError):
        DateOfBirth(year=EARLIEST_YEAR - 1, month=NR, day=NR)
    with pytest.raises(ValidationError):
        DateOfBirth(year=LATEST_BIRTH_YEAR + 1, month=NR, day=NR)
    with pytest.raises(ValidationError):
        DateOfFirstPublication(year=HCR_CUTOFF_YEAR + 1, month=NR, day=NR)


def test_exact_birth_age_on_birthday() -> None:
    birth = DateOfBirth(year=2000, month=10, day=27)
    result = birth.infer_age(AS_OF)
    assert isinstance(result, CurrentBiologicalAge)
    assert result.root == 26


def test_exact_birth_age_before_birthday() -> None:
    result = DateOfBirth(year=2000, month=10, day=28).infer_age(AS_OF)
    assert result.root == 25


def test_year_only_birth_creates_sensitivity_interval() -> None:
    result = DateOfBirth(year=2000, month=NR, day=NR).infer_age(AS_OF)
    interval = result.root
    assert isinstance(interval, AgeSensitivityInterval)
    assert (interval.lower, interval.upper) == (25, 26)


def test_month_only_birth_may_create_sensitivity_interval() -> None:
    result = DateOfBirth(year=2000, month=10, day=NR).infer_age(AS_OF)
    interval = result.root
    assert isinstance(interval, AgeSensitivityInterval)
    assert (interval.lower, interval.upper) == (25, 26)


def test_month_only_birth_may_collapse_to_point() -> None:
    september = DateOfBirth(year=2000, month=9, day=NR).infer_age(AS_OF)
    november = DateOfBirth(year=2000, month=11, day=NR).infer_age(AS_OF)
    assert september.root == 26
    assert november.root == 25


def test_current_year_birth_is_below_researcher_age_minimum() -> None:
    with pytest.raises(ValidationError):
        DateOfBirth(year=2000, month=NR, day=NR).infer_age(date(2000, 6, 15))


def test_completely_future_date_is_rejected() -> None:
    with pytest.raises(ValueError, match="after as_of"):
        DateOfBirth(year=2000, month=7, day=NR).infer_age(date(2000, 6, 15))


def test_first_publication_exact_age_and_basis() -> None:
    publication = DateOfFirstPublication(year=2020, month=10, day=27)
    result = publication.infer_age(AS_OF)
    assert isinstance(result, CurrentAgeFromFirstPublication)
    assert result.root == 6


def test_first_publication_year_only_interval() -> None:
    publication = DateOfFirstPublication(year=2020, month=NR, day=NR)
    result = publication.infer_age(AS_OF)
    interval = result.root
    assert isinstance(interval, AgeSensitivityInterval)
    assert (interval.lower, interval.upper) == (5, 6)


def test_age_sensitivity_interval_must_be_ordered_and_in_range() -> None:
    with pytest.raises(ValidationError):
        AgeSensitivityInterval(lower=26, upper=26)
    with pytest.raises(ValidationError):
        AgeSensitivityInterval(lower=27, upper=26)
    with pytest.raises(ValidationError):
        AgeSensitivityInterval(lower=HUMAN_LIFESPAN[0] - 1, upper=26)
    with pytest.raises(ValidationError):
        AgeSensitivityInterval(lower=26, upper=HUMAN_LIFESPAN[1] + 1)


def test_current_age_point_is_strict_and_lifespan_bounded() -> None:
    for value in ("26", 26.0, True, HUMAN_LIFESPAN[1] + 1):
        with pytest.raises(ValidationError):
            CurrentBiologicalAge.model_validate(value)


def test_inferred_age_outside_human_lifespan_is_rejected() -> None:
    birth = DateOfBirth(year=2000, month=1, day=1)
    with pytest.raises(ValidationError):
        birth.infer_age(date(2000 + HUMAN_LIFESPAN[1] + 1, 1, 1))


def test_birth_provenance_pair_is_accepted_and_retained() -> None:
    birth = DateOfBirth(year=2000, month=NR, day=NR)
    result = birth_age(birth, "Born in 2000")
    assert result.age.computed.birth.provenance == "reported"
    assert result.age.computed.birth.reported == "Born in 2000"
    assert result.age.computed.birth.inferred == birth
    assert result.age.provenance == "computed"
    assert result.age.computed.as_of == AS_OF
    assert isinstance(result.age.inferred.root, AgeSensitivityInterval)
    assert (result.age.inferred.root.lower, result.age.inferred.root.upper) == (25, 26)


def test_first_publication_provenance_pair_is_accepted() -> None:
    publication = DateOfFirstPublication(year=2020, month=10, day=27)
    result = publication_age(publication, "First published 27 October 2020")
    assert result.age.computed.first_publication.reported == "First published 27 October 2020"
    assert result.age.inferred.root == 6
    assert result.age.computed.basis == "first_publication"


def test_wrong_computed_age_is_rejected_by_provenance_pair() -> None:
    birth = DateOfBirth(year=2000, month=NR, day=NR)
    reported = ReportedNumeral[DateOfBirth](reported="Born in 2000", inferred=birth)
    wrong = ComputedNumeral[
        CurrentBiologicalAge, BirthComputation
    ](
        computed=BirthComputation(basis="birth", birth=reported, as_of=AS_OF),
        inferred=CurrentBiologicalAge(root=26),
    )
    with pytest.raises(ValidationError):
        AgeFromBirth(age=wrong)


def test_wrong_basis_is_rejected_by_typed_computation() -> None:
    birth = ReportedNumeral[DateOfBirth](
        reported="Born in 2000", inferred=DateOfBirth(year=2000, month=NR, day=NR)
    )
    publication = ReportedNumeral[DateOfFirstPublication](
        reported="Published in 2020",
        inferred=DateOfFirstPublication(year=2020, month=NR, day=NR),
    )
    with pytest.raises(ValidationError):
        BirthComputation.model_validate({
            "basis": "first_publication", "birth": birth, "as_of": AS_OF,
        })
    with pytest.raises(ValidationError):
        FirstPublicationComputation.model_validate({
            "basis": "birth", "first_publication": publication, "as_of": AS_OF,
        })


def test_provenance_literals_cannot_be_falsified() -> None:
    birth = DateOfBirth(year=2000, month=10, day=27)
    with pytest.raises(ValidationError):
        ReportedNumeral[DateOfBirth].model_validate({
            "provenance": "computed", "reported": "2000-10-27", "inferred": birth,
        })
    with pytest.raises(ValidationError):
        ComputedNumeral[CurrentBiologicalAge, BirthComputation].model_validate({
            "provenance": "reported",
            "computed": BirthComputation(
                basis="birth",
                birth=ReportedNumeral[DateOfBirth](reported="2000-10-27", inferred=birth),
                as_of=AS_OF,
            ),
            "inferred": CurrentBiologicalAge(root=26),
        })


def test_top_level_age_standardized_accepts_both_paths_and_not_reported() -> None:
    birth = DateOfBirth(year=2000, month=10, day=27)
    birth_pair = birth_age(birth, "Born 2000-10-27")
    publication = DateOfFirstPublication(year=2020, month=10, day=27)
    publication_pair = publication_age(publication, "Published 2020-10-27")
    adapter: TypeAdapter[AgeStandardized] = TypeAdapter(AgeStandardized)
    assert isinstance(adapter.validate_python(birth_pair), AgeFromBirth)
    assert isinstance(adapter.validate_python(publication_pair), AgeFromFirstPublication)
    assert adapter.validate_python(NR) == NR


def test_birth_pair_json_round_trip() -> None:
    birth = DateOfBirth(year=2000, month=NR, day=NR)
    pair = birth_age(birth, "Born in 2000")
    restored = AgeFromBirth.model_validate_json(pair.model_dump_json())
    assert restored == pair


def test_first_publication_pair_rejects_incorrect_age() -> None:
    publication = DateOfFirstPublication(year=2020, month=NR, day=NR)
    reported = ReportedNumeral[DateOfFirstPublication](
        reported="First published in 2020", inferred=publication
    )
    wrong = ComputedNumeral[
        CurrentAgeFromFirstPublication,
        FirstPublicationComputation,
    ](
        computed=FirstPublicationComputation(
            basis="first_publication", first_publication=reported, as_of=AS_OF
        ),
        inferred=CurrentAgeFromFirstPublication(root=6),
    )
    with pytest.raises(ValidationError):
        AgeFromFirstPublication(age=wrong)


def test_birth_pair_rejects_wrong_basis_even_if_inference_called_directly() -> None:
    birth = DateOfBirth(year=2000, month=10, day=27)
    inferred_age = birth.infer_age(AS_OF)
    reported = ReportedNumeral[DateOfBirth](
        reported="Born 2000-10-27", inferred=birth
    )
    with pytest.raises(ValidationError):
        AgeFromBirth.model_validate({
            "age": {
                "computed": {
                    "basis": "first_publication",
                    "birth": reported.model_dump(),
                    "as_of": AS_OF,
                },
                "inferred": inferred_age.model_dump(),
            }
        })


def test_deceased_birth_age_round_trips_and_keeps_age_at_death_type() -> None:
    birth = DateOfBirth(year=1963, month=9, day=20)
    death = DateOfDeath(year=2020, month=10, day=27)
    inferred = birth.infer_age(death)
    assert type(inferred) is BiologicalAgeAtDeath
    assert inferred.root == 57
    value = AgeAtDeathFromBirth(
        age=ComputedNumeral(
            computed=BirthToDeathComputation(
                basis="birth",
                birth=ReportedNumeral[DateOfBirth](
                    reported="September 20, 1963", inferred=birth,
                ),
                as_of=ReportedNumeral[DateOfDeath](
                    reported="October 27, 2020", inferred=death,
                ),
            ),
            inferred=inferred,
        ),
    )
    adapter: TypeAdapter[AgeStandardized] = TypeAdapter(AgeStandardized)
    restored = adapter.validate_json(value.model_dump_json())
    assert type(restored) is AgeAtDeathFromBirth
    assert restored == value
    assert restored.age.inferred.model_dump(mode="json") == 57


def test_deceased_publication_span_round_trips() -> None:
    publication = DateOfFirstPublication(year=2005, month=1, day=1)
    death = DateOfDeath(year=2020, month=10, day=27)
    inferred = publication.infer_age(death)
    assert type(inferred) is PublicationSpanAtDeath
    assert inferred.root == 15
    value = AgeAtDeathFromFirstPublication(
        age=ComputedNumeral(
            computed=FirstPublicationToDeathComputation(
                basis="first_publication",
                first_publication=ReportedNumeral[DateOfFirstPublication](
                    reported="2005-01-01", inferred=publication,
                ),
                as_of=ReportedNumeral[DateOfDeath](
                    reported="2020-10-27", inferred=death,
                ),
            ),
            inferred=inferred,
        ),
    )
    adapter: TypeAdapter[AgeStandardized] = TypeAdapter(AgeStandardized)
    assert adapter.validate_json(value.model_dump_json()) == value


def test_unknown_birth_and_death_dates_produce_age_at_death_range() -> None:
    birth = DateOfBirth(year=1963, month=NR, day=NR)
    death = DateOfDeath(year=2020, month=NR, day=NR)
    inferred = birth.infer_age(death)
    assert type(inferred) is BiologicalAgeAtDeath
    assert inferred.root == AgeSensitivityInterval(lower=56, upper=57)


def test_death_is_required_only_for_deceased_variant() -> None:
    birth = DateOfBirth(year=1963, month=9, day=20)
    assert type(birth_age(birth, "September 20, 1963")) is AgeFromBirth
    living = BirthComputation(
        basis="birth",
        birth=ReportedNumeral[DateOfBirth](
            reported="September 20, 1963", inferred=birth,
        ),
        as_of=AS_OF,
    )
    with pytest.raises(ValidationError):
        BirthToDeathComputation.model_validate(living.model_dump())


def test_death_cannot_precede_birth() -> None:
    birth = DateOfBirth(year=1963, month=9, day=20)
    with pytest.raises(ValueError, match="Event occurs after death"):
        birth.infer_age(DateOfDeath(year=1962, month=NR, day=NR))


DECEASED_BIRTH_JSON = """{
  "age": {
    "provenance": "computed",
    "computed": {
      "basis": "birth",
      "birth": {
        "provenance": "reported",
        "reported": "September 20, 1963",
        "inferred": {"year": 1963, "month": 9, "day": 20}
      },
      "as_of": {
        "provenance": "reported",
        "reported": "October 27, 2020",
        "inferred": {"year": 2020, "month": 10, "day": 27}
      }
    },
    "inferred": 57
  }
}"""

DECEASED_PUBLICATION_JSON = """{
  "age": {
    "provenance": "computed",
    "computed": {
      "basis": "first_publication",
      "first_publication": {
        "provenance": "reported",
        "reported": "2005",
        "inferred": {"year": 2005, "month": "NR", "day": "NR"}
      },
      "as_of": {
        "provenance": "reported",
        "reported": "2020",
        "inferred": {"year": 2020, "month": "NR", "day": "NR"}
      }
    },
    "inferred": {"lower": 14, "upper": 15}
  }
}"""


@pytest.mark.parametrize(
    ("serialized", "variant", "expected_age"),
    (
        (DECEASED_BIRTH_JSON, AgeAtDeathFromBirth, 57),
        (
            DECEASED_PUBLICATION_JSON,
            AgeAtDeathFromFirstPublication,
            AgeSensitivityInterval(lower=14, upper=15),
        ),
    ),
)
def test_deceased_standardized_json_examples(
    serialized: str,
    variant: type[BaseModel],
    expected_age: int | AgeSensitivityInterval,
) -> None:
    adapter: TypeAdapter[AgeStandardized] = TypeAdapter(AgeStandardized)
    value = adapter.validate_json(serialized)
    assert isinstance(value, Age)
    assert type(value) is variant
    assert value.age.inferred.root == expected_age
    assert isinstance(value, (AgeAtDeathFromBirth, AgeAtDeathFromFirstPublication))
    assert value.age.computed.as_of.provenance == "reported"
    assert value.model_dump(mode="json") == json.loads(serialized)


def test_deceased_birth_martin_serializes_exactly() -> None:
    adapter: TypeAdapter[AgeStandardized] = TypeAdapter(AgeStandardized)
    value = adapter.validate_json(DECEASED_BIRTH_JSON)
    assert isinstance(value, AgeAtDeathFromBirth)
    canonical = json.dumps(
        value.model_dump(mode="json"),
        ensure_ascii=False,
        separators=COMPACT_JSON_SEPARATORS,
    )
    rendered = render_standardized_submission_value(canonical)
    assert martin_serialize_standardized_cell(rendered) == (
        "**AI-generated text**:\n\n```\n"
        "57\ncomputed\n"
        "    2020, 10, 27\n    reported\n    October 27, 2020\n"
        "  birth\n"
        "    1963, 9, 20\n    reported\n    September 20, 1963\n```"
    )


def test_deceased_age_requires_death_evidence() -> None:
    adapter: TypeAdapter[AgeStandardized] = TypeAdapter(AgeStandardized)
    value = adapter.validate_json(DECEASED_BIRTH_JSON)
    birth_excerpt = schema.WebSearchExcerpt(
        excerpt="Born September 20, 1963",
        url="https://example.test/birth",
    )
    birth_only = schema.AgeFirstPublicationSubmission(
        value="Born in 1963; died in 2020.",
        standardized_value=value,
        web_search_excerpts=[birth_excerpt],
    )

    def rollout_index(*results: str) -> _RolloutIndex:
        return _RolloutIndex(
            session=_SessionMetadata(
                session_id=UUID(int=0),
                timestamp="",
                rollout_filename="",
                summary_json="{}",
            ),
            fc_rows=(_CodexFcRow(
                timestamp="2026-10-27T00:00:00Z",
                fc_id="fc",
                call_id="call",
                name="run",
                namespace="web",
                arguments_json="{}",
            ),),
            fco_rows=(_CodexFcoRow(
                timestamp="2026-10-27T00:00:00Z",
                fco_id="fco",
                call_id="call",
            ),),
            turn_ref_rows=tuple(
                _CodexTurnRefRow(
                    ref_id=f"ref-{index}",
                    call_id="call",
                    domain=None,
                    snippet=None,
                    thumbnail_url=None,
                    title=None,
                    url=f"https://example.test/{index}",
                    cite_text=result,
                )
                for index, result in enumerate(results)
            ),
        )

    birth_result = "Born September 20, 1963"
    death_result = "Died October 27, 2020"
    location = (
        f"{KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL}.standardized_value."
        "age.computed.as_of.reported"
    )
    violations = _age_evidence_violations(
        birth_only,
        rollout_index=rollout_index(birth_result),
        push_response_record=object(),  # type: ignore[arg-type]
    )
    assert len(violations) == 1
    assert violations[0].message == (
        Locale.STANDARDIZED_REPORTED_NOT_IN_WEB_RESULTS_TEMPLATE.format(location=location)
    )
    near_violations = _age_evidence_violations(
        birth_only,
        rollout_index=rollout_index(birth_result, death_result.lower()),
        push_response_record=object(),  # type: ignore[arg-type]
    )
    assert len(near_violations) == 1
    assert near_violations[0].message == (
        Locale.STANDARDIZED_REPORTED_NEAR_ITEM_TEMPLATE.format(location=location)
    )
    for rejected, template in (
        (violations, Locale.STANDARDIZED_REPORTED_NOT_IN_WEB_RESULTS_TEMPLATE),
        (near_violations, Locale.STANDARDIZED_REPORTED_NEAR_ITEM_TEMPLATE),
    ):
        detail = _assessment_public_detail(
            _EvidenceAssessment(items=()),
            pull_response_record=object(),  # type: ignore[arg-type]
            progress_template=None,
            violations=rejected,
        )
        assert f"- {template.format(location=location)}" in detail.splitlines()
    assert not _age_evidence_violations(
        birth_only,
        rollout_index=rollout_index(birth_result, death_result),
        push_response_record=object(),  # type: ignore[arg-type]
    )
