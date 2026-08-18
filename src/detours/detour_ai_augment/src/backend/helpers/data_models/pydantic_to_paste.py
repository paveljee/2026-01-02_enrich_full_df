#!/usr/bin/env python3

# --- pyproject.toml ---
# [project]
# requires-python = ">=3.14.2,<3.15"
# dependencies = [
#     "pydantic==2.13.4",
#     "pydantic-extra-types==2.11.1",
#     "pycountry==24.6.1",
#     "requests==2.32.5",
# ]

import os
from datetime import date
from enum import StrEnum
from http import HTTPStatus
from typing import (
    Annotated,
    Literal,
    Self,
    TypeAlias,
    TypeVar,
    get_args,
)
from urllib.parse import urlsplit
import requests

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PositiveInt,
    StrictStr,
    StringConstraints,
    model_validator,
)

from pydantic_extra_types.country import CountryAlpha2
from pydantic_extra_types.language_code import ISO639_3

# OpenAPI hint: patch this
from ..locale import Locale

# OpenAPI hint: see submission example
from ..vars import (
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_COMMENTS_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_LINKS_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
)

MIN_VALUE_CHARACTERS = 1
MIN_TARGET_WEB_SEARCH_QUERY_LANGUAGES = 1
MIN_EDUCATION_RECORDS = 1
MIN_ACADEMIC_POSITIONS = 1
MIN_SOCIAL_CAPITAL_ITEMS = 1
MIN_RESEARCHER_LINKS = 1
MIN_EXCERPT_CHARACTERS = 1
MIN_URL_CHARACTERS = 1
MIN_EXCERPTS_PER_FIELD = 1

MAX_PUSH_BODY_BYTES = 2 * 1024 * 1024
MAX_VALUE_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_EXCERPT_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_URL_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_EXCERPTS_PER_FIELD = MAX_PUSH_BODY_BYTES

EARLIEST_YEAR = 1900
LATEST_BIRTH_YEAR = 2010  # 2026 minus 16

DEFAULT_TARGET_WEB_SEARCH_QUERY_LANGUAGE = "eng"

OPENALEX_SCHEME = "https"
OPENALEX_HOST = "api.openalex.org"
OPENALEX_INSTITUTIONS_PATH = "/institutions"
EXPORT_OPENALEX_API_KEY = "OPENALEX_API_KEY"
OPENALEX_PARAMS = {"api_key": None}  # updated later
OPENALEX_INSTITUTION_NAME_FIELD = "display_name"
OPENALEX_ROR_FIELD = "ror"

ROR_SCHEME = "https"
ROR_HOST = "api.ror.org"
ROR_ORGANIZATIONS_PATH = "/v2/organizations"
ROR_NAMES_KEY = "names"
ROR_NAME_VALUE_KEY = "value"
ROR_NAME_TYPES_KEY = "types"
ROR_DISPLAY_NAME_TYPE = "ror_display"

INSTITUTION_REQUEST_TIMEOUT_SECONDS = 30.0

T = TypeVar("T")

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

SubmissionText: TypeAlias = Annotated[
    StrictStr,
    StringConstraints(
        min_length=MIN_VALUE_CHARACTERS,
        max_length=MAX_PUSH_BODY_BYTES,
    ),
    AfterValidator(
        lambda value: value
        if value.strip()
        else (_ for _ in ()).throw(ValueError(Locale.VALUE_NONBLANK))
    ),
]

NotReported: TypeAlias = Literal["NR"]
NotAvailableOrApplicable: TypeAlias = Literal["NA"]
SubmissionValue: TypeAlias = T | NotReported | NotAvailableOrApplicable


# KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL
class ResearcherAuthorStandardized(StrictModel):
    first_name: SubmissionValue[SubmissionText]
    last_name: SubmissionValue[SubmissionText]
    orcid: SubmissionValue[HttpUrl]
    openalex_id: SubmissionValue[HttpUrl]


# KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL
Location: TypeAlias = CountryAlpha2

class PlaceOfResidenceStandardized(StrictModel):
    place: SubmissionValue[SubmissionText]
    location: SubmissionValue[Location]


# KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL
Language: TypeAlias = ISO639_3

class CLDRLanguageOfficialStatus(StrEnum):
    """https://www.unicode.org/cldr/charts/48/supplemental/territory_language_information.html"""
    OFFICIAL = "official"
    OFFICIAL_REGIONAL = "official_regional"
    DE_FACTO_OFFICIAL = "de_facto_official"

class LanguageOfLocation(StrictModel):
    language: Language
    official_status: CLDRLanguageOfficialStatus
    location: Location

LanguagePersonUsesOrUsed: TypeAlias = Language
LanguagePublicationIsIn: TypeAlias = Language
LanguageOfPlaceOfResidence: TypeAlias = LanguageOfLocation
LanguageOfAcademicInstitution: TypeAlias = LanguageOfLocation

TargetWebSearchQueryLanguage: TypeAlias = (
    LanguagePersonUsesOrUsed
    | LanguagePublicationIsIn
    | LanguageOfPlaceOfResidence
    | LanguageOfAcademicInstitution
    | Language  # any other relevant
)

class RaceEthnicityLanguageCultureStandardized(StrictModel):
    race: NotAvailableOrApplicable  # banned
    ethnicity: NotAvailableOrApplicable  # banned
    language: SubmissionValue[
        list[TargetWebSearchQueryLanguage],
    ] = Field(
        min_length=MIN_TARGET_WEB_SEARCH_QUERY_LANGUAGES,
        default_factory=lambda: [Language(DEFAULT_TARGET_WEB_SEARCH_QUERY_LANGUAGE)],
    )
    culture: NotAvailableOrApplicable  # banned

# KTP_AI_AUGMENT_GENDER_COL
GenderStandardized: TypeAlias = SubmissionValue[
    Literal["Man", "Woman", "Other"]
]


# KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL
Year = Annotated[int, Field(ge=EARLIEST_YEAR)]
CurrentAge: TypeAlias = PositiveInt
YearOfBirth: TypeAlias = Annotated[
    int,
    Field(ge=EARLIEST_YEAR, le=LATEST_BIRTH_YEAR),
]
DateOfBirth: TypeAlias = date
YearOfFirstPublication: TypeAlias = Year
DateOfFirstPublication: TypeAlias = date
AgeStandardized: TypeAlias = SubmissionValue[
    CurrentAge
    | YearOfBirth
    | DateOfBirth
    | YearOfFirstPublication
    | DateOfFirstPublication
]


# KTP_AI_AUGMENT_EDUCATION_COL
class AcademicInstitution(StrictModel):
    organization_name: SubmissionValue[SubmissionText]
    openalex_id: SubmissionValue[HttpUrl]
    ror: SubmissionValue[HttpUrl]

    @model_validator(mode="after")
    def validate_institution(self) -> Self:
        nr_or_na = frozenset(
            get_args(NotReported) + get_args(NotAvailableOrApplicable)
        )

        # OpenAlex
        if self.openalex_id not in nr_or_na:
            OPENALEX_PARAMS.update(
                api_key=os.getenv(EXPORT_OPENALEX_API_KEY),
            )
            if None in OPENALEX_PARAMS.values():
                raise ValueError(Locale.OPENALEX_API_KEY_MISSING)
            openalex_id = (
                urlsplit(str(self.openalex_id)).path.rstrip("/").rsplit("/", 1)[-1]
            )
            r = requests.get(
                (
                    f"{OPENALEX_SCHEME}://{OPENALEX_HOST}"
                    f"{OPENALEX_INSTITUTIONS_PATH}/{openalex_id}"
                ),
                params=OPENALEX_PARAMS,
                timeout=INSTITUTION_REQUEST_TIMEOUT_SECONDS,
            )
            if r.status_code == HTTPStatus.NOT_FOUND:
                raise ValueError(
                    Locale.OPENALEX_INSTITUTION_UNKNOWN_TEMPLATE.format(
                        openalex_id=self.openalex_id
                    )
                )
            r.raise_for_status()
            oa = r.json()
            if (
                self.organization_name not in nr_or_na
                and oa[OPENALEX_INSTITUTION_NAME_FIELD] != self.organization_name
            ):
                raise ValueError(
                    Locale.OPENALEX_INSTITUTION_NAME_MISMATCH_TEMPLATE.format(
                        actual=oa[OPENALEX_INSTITUTION_NAME_FIELD],
                        submitted=self.organization_name,
                    )
                )

            if (
                self.ror not in nr_or_na
                and oa.get(OPENALEX_ROR_FIELD) != str(self.ror)
            ):
                raise ValueError(
                    Locale.OPENALEX_INSTITUTION_ROR_MISMATCH_TEMPLATE.format(
                        actual=oa.get(OPENALEX_ROR_FIELD),
                        submitted=self.ror,
                    )
                )

        # ROR
        if self.ror not in nr_or_na:
            ror_id = urlsplit(str(self.ror)).path.rstrip("/").rsplit("/", 1)[-1]
            r = requests.get(
                (
                    f"{ROR_SCHEME}://{ROR_HOST}"
                    f"{ROR_ORGANIZATIONS_PATH}/{ror_id}"
                ),
                timeout=INSTITUTION_REQUEST_TIMEOUT_SECONDS,
            )
            if r.status_code == HTTPStatus.NOT_FOUND:
                raise ValueError(
                    Locale.ROR_INSTITUTION_UNKNOWN_TEMPLATE.format(ror=self.ror)
                )
            r.raise_for_status()
            ror = r.json()
            ror_name = next(
                name[ROR_NAME_VALUE_KEY]
                for name in ror[ROR_NAMES_KEY]
                if ROR_DISPLAY_NAME_TYPE in name[ROR_NAME_TYPES_KEY]
            )
            if (
                self.organization_name not in nr_or_na
                and ror_name != self.organization_name
            ):
                raise ValueError(
                    Locale.ROR_INSTITUTION_NAME_MISMATCH_TEMPLATE.format(
                        actual=ror_name,
                        submitted=self.organization_name,
                    )
                )

        return self

class ISCEDTertiaryLevel(StrEnum):
    """https://unesdoc.unesco.org/ark:/48223/pf0000219109_eng"""
    # LEVEL_0 = "0"  # Early childhood
    # LEVEL_1 = "1"  # Primary
    # LEVEL_2 = "2"  # Lower secondary
    # LEVEL_3 = "3"  # Upper secondary
    # LEVEL_4 = "4"  # Post-secondary non-tertiary
    LEVEL_5 = "5"  # Short-cycle tertiary
    LEVEL_6 = "6"  # Bachelor's or equivalent
    LEVEL_7 = "7"  # Master's or equivalent
    LEVEL_8 = "8"  # Doctoral or equivalent

class EducationRecord(StrictModel):
    degree_conferred: SubmissionValue[SubmissionText]
    isced_level: SubmissionValue[ISCEDTertiaryLevel]
    place_conferred: SubmissionValue[AcademicInstitution]
    year_conferred: SubmissionValue[Year]

EducationStandardized: TypeAlias = SubmissionValue[Annotated[
    list[EducationRecord],
    Field(min_length=MIN_EDUCATION_RECORDS),
]]


# KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL
class FormerAcademicPosition(StrictModel):
    academic_position: SubmissionValue[SubmissionText]
    academic_institution: SubmissionValue[AcademicInstitution]
    start: SubmissionValue[Year]
    end: SubmissionValue[Year]

class CurrentAcademicPosition(StrictModel):
    academic_position: SubmissionValue[SubmissionText]
    academic_institution: SubmissionValue[AcademicInstitution]

AcademicPositionsStandardized: TypeAlias = SubmissionValue[Annotated[
    list[FormerAcademicPosition | CurrentAcademicPosition],
    Field(min_length=MIN_ACADEMIC_POSITIONS),
]]


# KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL
SocialCapitalStandardized: TypeAlias = SubmissionValue[Annotated[
    list[SubmissionText],
    Field(min_length=MIN_SOCIAL_CAPITAL_ITEMS),
]]


# KTP_AI_AUGMENT_LINKS_COL
class ResearcherLink(StrictModel):
    url: SubmissionValue[HttpUrl]
    verified_with_orcid: SubmissionValue[bool]

ResearcherLinksStandardized: TypeAlias = SubmissionValue[Annotated[
    list[ResearcherLink],
    Field(min_length=MIN_RESEARCHER_LINKS),
]]

# KTP_AI_AUGMENT_COMMENTS_COL
# no standardized value

class WebSearchExcerpt(StrictModel):
    excerpt: StrictStr = Field(
        description="Exact contiguous excerpt copied verbatim from the cited web-tool result.",
        min_length=MIN_EXCERPT_CHARACTERS,
        max_length=MAX_EXCERPT_CHARACTERS,
        pattern=r"\S",
    )
    url: StrictStr = Field(
        description="Exact URL associated with that web-tool result.",
        min_length=MIN_URL_CHARACTERS,
        max_length=MAX_URL_CHARACTERS,
        pattern=r"\S",
    )

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if not self.excerpt.strip() or not self.url.strip():
            raise ValueError(Locale.EXCERPT_URL_NONBLANK)
        return self


class EvidenceWithdrawal(StrictModel):
    action: Literal["withdraw_unverified_evidence"]
    reason: Literal["not_present_in_web_results"]
    attested: Literal[True]


EvidenceSubmission: TypeAlias = WebSearchExcerpt | EvidenceWithdrawal


StandardizedValue: TypeAlias = (
    ResearcherAuthorStandardized
    | PlaceOfResidenceStandardized
    | RaceEthnicityLanguageCultureStandardized
    | GenderStandardized
    | AgeStandardized
    | EducationStandardized
    | AcademicPositionsStandardized
    | SocialCapitalStandardized
    | ResearcherLinksStandardized
    | NotAvailableOrApplicable
)


class FieldSubmission(StrictModel):
    value: SubmissionText
    standardized_value: StandardizedValue
    web_search_excerpts: list[EvidenceSubmission] = Field(
        min_length=MIN_EXCERPTS_PER_FIELD,
        max_length=MAX_EXCERPTS_PER_FIELD,
    )

    @model_validator(mode="after")
    def validate_evidence_pairs(self) -> Self:
        evidence_pairs = [
            (evidence.excerpt, evidence.url)
            for evidence in self.web_search_excerpts
            if isinstance(evidence, WebSearchExcerpt)
        ]
        if len(set(evidence_pairs)) != len(evidence_pairs):
            raise ValueError(Locale.EXCERPT_PAIRS_UNIQUE)
        return self


class ResearcherAuthorSubmission(FieldSubmission):
    standardized_value: ResearcherAuthorStandardized


class PlaceOfResidenceSubmission(FieldSubmission):
    standardized_value: PlaceOfResidenceStandardized


class RaceEthnicityLanguageCultureSubmission(FieldSubmission):
    standardized_value: RaceEthnicityLanguageCultureStandardized


class GenderSubmission(FieldSubmission):
    standardized_value: GenderStandardized


class AgeFirstPublicationSubmission(FieldSubmission):
    standardized_value: AgeStandardized


class EducationSubmission(FieldSubmission):
    standardized_value: EducationStandardized


class AcademicPositionsSubmission(FieldSubmission):
    standardized_value: AcademicPositionsStandardized


class SocialCapitalSubmission(FieldSubmission):
    standardized_value: SocialCapitalStandardized


class ResearcherLinksSubmission(FieldSubmission):
    standardized_value: ResearcherLinksStandardized


class CommentsSubmission(StrictModel):
    value: SubmissionText


class Submission(StrictModel):
    researcher_author: ResearcherAuthorSubmission = Field(
        alias=KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
        description="researcher/author from public academic sources.",
    )
    place_of_residence: PlaceOfResidenceSubmission = Field(
        alias=KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
        description="place of residence from public academic sources.",
    )
    race_ethnicity_language_culture: RaceEthnicityLanguageCultureSubmission = Field(
        alias=KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
        description="race/ethnicity/language/culture from public academic sources.",
    )
    gender: GenderSubmission = Field(
        alias=KTP_AI_AUGMENT_GENDER_COL,
        description="gender from public academic sources.",
    )
    age_first_publication: AgeFirstPublicationSubmission = Field(
        alias=KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
        description=(
            "current age/date of birth from public academic sources, or year of the first "
            "publication according to OpenAlex profile."
        ),
    )
    education: EducationSubmission = Field(
        alias=KTP_AI_AUGMENT_EDUCATION_COL,
        description="education from public academic sources.",
    )
    academic_positions: AcademicPositionsSubmission = Field(
        alias=KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
        description="academic position(s) from public academic sources.",
    )
    social_capital: SocialCapitalSubmission = Field(
        alias=KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
        description="social capital from public academic sources.",
    )
    links: ResearcherLinksSubmission = Field(
        alias=KTP_AI_AUGMENT_LINKS_COL,
        description="links from public academic sources.",
    )
    comments: CommentsSubmission | None = Field(
        default=None,
        alias=KTP_AI_AUGMENT_COMMENTS_COL,
        description="comments.",
    )

    def evidence_items(self) -> tuple[tuple[str, FieldSubmission], ...]:
        return (
            (KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL, self.researcher_author),
            (KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL, self.place_of_residence),
            (
                KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
                self.race_ethnicity_language_culture,
            ),
            (KTP_AI_AUGMENT_GENDER_COL, self.gender),
            (KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL, self.age_first_publication),
            (KTP_AI_AUGMENT_EDUCATION_COL, self.education),
            (KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL, self.academic_positions),
            (KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL, self.social_capital),
            (KTP_AI_AUGMENT_LINKS_COL, self.links),
        )

    def normalized_values(self) -> dict[str, str]:
        values = {column: field.value for column, field in self.evidence_items()}
        if self.comments is not None:
            values[KTP_AI_AUGMENT_COMMENTS_COL] = self.comments.value
        return values
