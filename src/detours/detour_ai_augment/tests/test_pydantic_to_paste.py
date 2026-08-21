from __future__ import annotations

import importlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values
from pydantic import BaseModel, ValidationError

pytest.importorskip("pydantic_extra_types")

from src.detours.detour_ai_augment.src.backend.helpers.data_models import (  # noqa: E402
    pydantic_to_paste as schema,
)
from src.detours.detour_ai_augment.src.backend.helpers.data_models.submission_init import (  # noqa: E402
    Submission,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = REPOSITORY_ROOT / ".env"

TEST_OPENALEX_API_KEY = "test-openalex-api-key"
TEST_EXCERPT = "Exact cited text."
TEST_URL = "https://example.test/result"
FIELD_VALUE_FIELD, FIELD_EVIDENCE_FIELD = schema.FieldSubmission.model_fields
(FIELD_STANDARDIZED_VALUE_FIELD,) = (
    schema.StandardizedFieldSubmission.model_fields.keys()
    - schema.FieldSubmission.model_fields.keys()
)
EVIDENCE_EXCERPT_FIELD, EVIDENCE_URL_FIELD = schema.WebSearchExcerpt.model_fields
(COMMENTS_VALUE_FIELD,) = schema.CommentsSubmission.model_fields
TEST_EVIDENCE = [
    {
        EVIDENCE_EXCERPT_FIELD: TEST_EXCERPT,
        EVIDENCE_URL_FIELD: TEST_URL,
    }
]
STANFORD_OPENALEX_ID = "https://openalex.org/I97018004"
STANFORD_OPENALEX_API_URL = "https://api.openalex.org/institutions/I97018004"
STANFORD_ROR = "https://ror.org/00f54p054"
STANFORD_ROR_API_URL = "https://api.ror.org/v2/organizations/00f54p054"
STANFORD_NAME = "Stanford University"

FIELD_MODEL_CASES = (
    (
        schema.ResearcherAuthorSubmission,
        {
            "first_name": "Fei-Fei",
            "last_name": "Li",
            "orcid": "https://orcid.org/0000-0002-7481-0810",
            "openalex_id": "https://openalex.org/A5100450462",
        },
    ),
    (
        schema.PlaceOfResidenceSubmission,
        {"place": "Stanford, California", "location": "US"},
    ),
    (
        schema.RaceEthnicityLanguageCultureSubmission,
        {
            "race": "NA",
            "ethnicity": "NA",
            "language": ["eng", "cmn"],
            "culture": "NA",
        },
    ),
    (schema.GenderSubmission, "Woman"),
    (schema.AgeFirstPublicationSubmission, 1976),
    (
        schema.EducationSubmission,
        [
            {
                "degree_conferred": "Ph.D.",
                "isced_level": "8",
                "place_conferred": {
                    "organization_name": "Caltech",
                    "openalex_id": "NR",
                    "ror": "NR",
                },
                "year_conferred": 2005,
            }
        ],
    ),
    (
        schema.AcademicPositionsSubmission,
        [
            {
                "academic_position": "Professor",
                "academic_institution": {
                    "organization_name": "Stanford University",
                    "openalex_id": "NR",
                    "ror": "NR",
                },
            }
        ],
    ),
    (schema.SocialCapitalSubmission, ["National Academy member"]),
    (
        schema.ResearcherLinksSubmission,
        [{"url": "https://example.test/profile", "verified_with_orcid": True}],
    ),
)

FIELD_MODEL_UNAVAILABLE_CASES = (
    (
        schema.ResearcherAuthorSubmission,
        {
            "first_name": "NR",
            "last_name": "NA",
            "orcid": "NR",
            "openalex_id": "NA",
        },
    ),
    (
        schema.PlaceOfResidenceSubmission,
        {"place": "NR", "location": "NA"},
    ),
    (
        schema.RaceEthnicityLanguageCultureSubmission,
        {"race": "NA", "ethnicity": "NA", "language": "NR", "culture": "NA"},
    ),
    (schema.GenderSubmission, "NR"),
    (schema.AgeFirstPublicationSubmission, "NA"),
    (schema.EducationSubmission, "NR"),
    (schema.AcademicPositionsSubmission, "NA"),
    (schema.SocialCapitalSubmission, "NR"),
    (schema.ResearcherLinksSubmission, "NA"),
)


@dataclass(frozen=True)
class FakeResponse:
    status_code: int
    payload: dict[str, Any]

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


@pytest.mark.parametrize(
    ("model", "standardized_value"),
    FIELD_MODEL_CASES,
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_field_submission_models_round_trip(
    model: type[BaseModel],
    standardized_value: object,
) -> None:
    payload = {
        FIELD_VALUE_FIELD: "Plain-text research value.",
        FIELD_STANDARDIZED_VALUE_FIELD: standardized_value,
        FIELD_EVIDENCE_FIELD: TEST_EVIDENCE,
    }

    parsed = model.model_validate_json(json.dumps(payload))

    assert model.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(
    ("model", "standardized_value"),
    FIELD_MODEL_UNAVAILABLE_CASES,
    ids=lambda value: value.__name__ if isinstance(value, type) else None,
)
def test_field_submission_models_support_nr_and_na(
    model: type[BaseModel],
    standardized_value: object,
) -> None:
    payload = {
        FIELD_VALUE_FIELD: "NR or NA",
        FIELD_STANDARDIZED_VALUE_FIELD: standardized_value,
        FIELD_EVIDENCE_FIELD: TEST_EVIDENCE,
    }

    parsed = model.model_validate_json(json.dumps(payload))

    assert parsed.model_dump(mode="json")[FIELD_STANDARDIZED_VALUE_FIELD] == (
        standardized_value
    )


def test_comments_submission_is_optional_plain_text_without_evidence_or_standardization() -> None:
    assert schema.CommentsSubmission.model_validate({
        COMMENTS_VALUE_FIELD: "Identity caveat."
    }).value == "Identity caveat."
    with pytest.raises(ValidationError):
        schema.CommentsSubmission.model_validate({
            COMMENTS_VALUE_FIELD: "Identity caveat.",
            FIELD_STANDARDIZED_VALUE_FIELD: "NA",
        })
    with pytest.raises(ValidationError):
        schema.CommentsSubmission.model_validate({
            COMMENTS_VALUE_FIELD: "Identity caveat.",
            FIELD_EVIDENCE_FIELD: [],
        })


def test_academic_institution_skips_external_validation_for_nr_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_get(*_args: object, **_kwargs: object) -> None:
        pytest.fail("NR identifiers must not make external requests")

    monkeypatch.setattr(schema.requests, "get", unexpected_get)

    institution = schema.AcademicInstitution.model_validate({
        "organization_name": "Caltech",
        "openalex_id": "NR",
        "ror": "NR",
    })

    assert institution.organization_name == "Caltech"


def test_academic_institution_validates_openalex_and_ror_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        STANFORD_OPENALEX_API_URL: FakeResponse(
            status_code=200,
            payload={"display_name": STANFORD_NAME, "ror": STANFORD_ROR},
        ),
        STANFORD_ROR_API_URL: FakeResponse(
            status_code=200,
            payload={
                "names": [{"value": STANFORD_NAME, "types": ["ror_display"]}],
            },
        ),
    }
    requested_urls: list[str] = []

    def fake_get(
        url: str,
        *,
        params: dict[str, str | None] | None = None,
        timeout: float,
    ) -> FakeResponse:
        assert timeout == schema.INSTITUTION_REQUEST_TIMEOUT_SECONDS
        if url == STANFORD_OPENALEX_API_URL:
            assert params == {"api_key": TEST_OPENALEX_API_KEY}
        else:
            assert params is None
        requested_urls.append(url)
        return responses[url]

    monkeypatch.setenv(schema.EXPORT_OPENALEX_API_KEY, TEST_OPENALEX_API_KEY)
    monkeypatch.setattr(schema.requests, "get", fake_get)

    institution = schema.AcademicInstitution.model_validate({
        "organization_name": STANFORD_NAME,
        "openalex_id": STANFORD_OPENALEX_ID,
        "ror": STANFORD_ROR,
    })

    assert institution.organization_name == STANFORD_NAME
    assert requested_urls == [STANFORD_OPENALEX_API_URL, STANFORD_ROR_API_URL]


def test_l_fei_fei_fixture_builds_without_external_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_get(*_args: object, **_kwargs: object) -> None:
        pytest.fail("the static submission fixture must not make external requests")

    module_name = (
        "src.detours.detour_ai_augment.src.backend.helpers.data_models.submission_fixture"
    )
    fixture_module = importlib.import_module(module_name)
    monkeypatch.setattr(schema.requests, "get", unexpected_get)

    fixture_module = importlib.reload(fixture_module)

    assert fixture_module.L_FEI_FEI_INITIAL_FIXTURE.identity == ("L.", "Fei-Fei")
    assert isinstance(fixture_module.L_FEI_FEI_INITIAL_FIXTURE.submission, Submission)
    assert fixture_module.L_FEI_FEI_RETRY_FIXTURE.identity == ("L.", "Fei-Fei")
    assert isinstance(
        fixture_module.L_FEI_FEI_RETRY_FIXTURE.submission,
        schema.StandardizedSubmission,
    )


@pytest.mark.real_api
def test_academic_institution_round_trips_against_real_apis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_key = os.environ.get(schema.EXPORT_OPENALEX_API_KEY) or dotenv_values(
        ENV_PATH
    ).get(schema.EXPORT_OPENALEX_API_KEY)
    if not api_key:
        pytest.skip(f"{schema.EXPORT_OPENALEX_API_KEY} is unavailable")
    monkeypatch.setenv(schema.EXPORT_OPENALEX_API_KEY, api_key)

    institution = schema.AcademicInstitution.model_validate({
        "organization_name": STANFORD_NAME,
        "openalex_id": STANFORD_OPENALEX_ID,
        "ror": STANFORD_ROR,
    })

    assert institution.model_dump(mode="json") == {
        "organization_name": STANFORD_NAME,
        "openalex_id": STANFORD_OPENALEX_ID,
        "ror": STANFORD_ROR,
    }
