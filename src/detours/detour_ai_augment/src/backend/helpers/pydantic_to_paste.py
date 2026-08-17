from __future__ import annotations

# --- pyproject.toml ---
# [project]
# requires-python = ">=3.14.2,<3.15"
# dependencies = [
#     "pydantic==2.13.4",
#     "httpx==0.28.1",
#     "pydantic-extra-types==2.11.1",
#     "pycountry==24.6.1",
# ]

import httpx

from datetime import date
from enum import StrEnum
from typing import (
    Annotated,
    Generic,
    Literal,
    Self,
    TypeAlias,
    TypeVar,
)

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

AI_AUGMENT_COLUMN_PREFIX = "ktp.ai_augment_"
KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL = f"{AI_AUGMENT_COLUMN_PREFIX}researcher_author"
KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL = f"{AI_AUGMENT_COLUMN_PREFIX}place_of_residence"
KTP_AI_AUGMENT_GENDER_COL = f"{AI_AUGMENT_COLUMN_PREFIX}gender"
KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL = (
    f"{AI_AUGMENT_COLUMN_PREFIX}age_first_publication_according_to_openalex_profile"
)
KTP_AI_AUGMENT_EDUCATION_COL = f"{AI_AUGMENT_COLUMN_PREFIX}education"
KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}academic_position_s_"
KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL = f"{AI_AUGMENT_COLUMN_PREFIX}social_capital"
KTP_AI_AUGMENT_LINKS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}links_"
KTP_AI_AUGMENT_COMMENTS_COL = f"{AI_AUGMENT_COLUMN_PREFIX}comments"
AI_AUGMENT_EVIDENCE_COLUMNS = (
    KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    KTP_AI_AUGMENT_GENDER_COL,
    KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    KTP_AI_AUGMENT_EDUCATION_COL,
    KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    KTP_AI_AUGMENT_LINKS_COL,
)
AI_AUGMENT_COLUMNS = AI_AUGMENT_EVIDENCE_COLUMNS + (KTP_AI_AUGMENT_COMMENTS_COL,)

SUBMISSION_VALUE_KEY = "value"
SUBMISSION_STANDARDIZED_VALUE_KEY = "standardized_value"
SUBMISSION_EVIDENCE_KEY = "web_search_excerpts"
SUBMISSION_EXCERPT_KEY = "excerpt"
SUBMISSION_URL_KEY = "url"
EVIDENCE_WITHDRAWAL_ACTION_KEY = "action"
EVIDENCE_WITHDRAWAL_REASON_KEY = "reason"
EVIDENCE_WITHDRAWAL_ATTESTED_KEY = "attested"
EVIDENCE_WITHDRAWAL_ACTION = "withdraw_unverified_evidence"
EVIDENCE_WITHDRAWAL_REASON = "not_present_in_web_results"

MAX_PUSH_BODY_BYTES = 2 * 1024 * 1024
MAX_VALUE_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_EXCERPT_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_URL_CHARACTERS = MAX_PUSH_BODY_BYTES
MAX_EXCERPTS_PER_FIELD = MAX_PUSH_BODY_BYTES
EARLIEST_YEAR = 1900
LATEST_BIRTH_YEAR = 2010  # 2026 minus 16
EXCERPT_URL_NONBLANK = "excerpt and url must be non-blank"
VALUE_NONBLANK = "value must be non-blank"
EXCERPT_PAIRS_UNIQUE = "web_search_excerpts must not contain duplicate pairs"


T = TypeVar("T")

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

SubmissionText: TypeAlias = Annotated[
    StrictStr,
    StringConstraints(min_length=1, max_length=MAX_VALUE_CHARACTERS),
    AfterValidator(
        lambda value: value
        if value.strip()
        else (_ for _ in ()).throw(ValueError(VALUE_NONBLANK))
    ),
]

NotReported: TypeAlias = Literal["NR"]
NotAvailableOrApplicable: TypeAlias = Literal["NA"]
SubmissionValue: TypeAlias = T | NotReported | NotAvailableOrApplicable


# KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL
class ResearcherAuthorStandardized(StrictModel):
    first_name: SubmissionValue[SubmissionText]
    last_name: SubmissionValue[SubmissionText]


# KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL
class PlaceOfResidenceStandardized(StrictModel):
    place: SubmissionValue[SubmissionText]
    location: SubmissionValue[CountryAlpha2]


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
    CurrentAge |
    YearOfBirth |
    DateOfBirth |
    YearOfFirstPublication |
    DateOfFirstPublication
]


# KTP_AI_AUGMENT_EDUCATION_COL
class AcademicInstitution(StrictModel):
    organization_name: SubmissionValue[SubmissionText]
    openalex_id: SubmissionValue[SubmissionText]
    ror: SubmissionValue[SubmissionText]

    @model_validator(mode="after")
    def validate_institution(self) -> Self:
        # OpenAlex
        if self.openalex_id not in {"NR", "NA"}:
            r = httpx.get(
                f"https://api.openalex.org/institutions/{self.openalex_id}",
                timeout=5,
            )
            if r.status_code == 404:
                raise ValueError(f"unknown OpenAlex institution: {self.openalex_id}")
            r.raise_for_status()

            oa = r.json()

            if (
                self.organization_name not in {"NR", "NA"}
                and oa["display_name"] != self.organization_name
            ):
                raise ValueError(
                    f"OpenAlex name is {oa['display_name']!r}, "
                    f"not {self.organization_name!r}"
                )

            if self.ror not in {"NR", "NA"} and oa.get("ror") != self.ror:
                raise ValueError(
                    f"OpenAlex ROR is {oa.get('ror')!r}, not {self.ror!r}"
                )

        # ROR
        if self.ror not in {"NR", "NA"}:
            ror_id = self.ror.removeprefix("https://ror.org/")
            r = httpx.get(
                f"https://api.ror.org/v2/organizations/{ror_id}",
                timeout=5,
            )
            if r.status_code == 404:
                raise ValueError(f"unknown ROR institution: {self.ror}")
            r.raise_for_status()

            ror = r.json()
            ror_name = next(
                n["value"]
                for n in ror["names"]
                if "ror_display" in n["types"]
            )

            if (
                self.organization_name not in {"NR", "NA"}
                and ror_name != self.organization_name
            ):
                raise ValueError(
                    f"ROR name is {ror_name!r}, not {self.organization_name!r}"
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
    Field(min_length=1),
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
    Field(min_length=1),
]]


# KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL
SocialCapitalStandardized: TypeAlias = SubmissionValue[Annotated[
    list[SubmissionText],
    Field(min_length=1),
]]


# KTP_AI_AUGMENT_LINKS_COL
class ResearcherLink(StrictModel):
    url: SubmissionValue[HttpUrl]
    verified_with_orcid: SubmissionValue[bool]

ResearcherLinksStandardized: TypeAlias = SubmissionValue[Annotated[
    list[ResearcherLink],
    Field(min_length=1),
]]

# KTP_AI_AUGMENT_COMMENTS_COL
# no standardized value

class WebSearchExcerpt(StrictModel):
    excerpt: StrictStr = Field(
        description="Exact contiguous excerpt copied verbatim from the cited web-tool result.",
        min_length=1,
        max_length=MAX_EXCERPT_CHARACTERS,
        pattern=r"\S",
    )
    url: StrictStr = Field(
        description="Exact URL associated with that web-tool result.",
        min_length=1,
        max_length=MAX_URL_CHARACTERS,
        pattern=r"\S",
    )

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if not self.excerpt.strip() or not self.url.strip():
            raise ValueError(EXCERPT_URL_NONBLANK)
        return self


class EvidenceWithdrawal(StrictModel):
    action: Literal["withdraw_unverified_evidence"]
    reason: Literal["not_present_in_web_results"]
    attested: Literal[True]


EvidenceSubmission: TypeAlias = WebSearchExcerpt | EvidenceWithdrawal


StandardizedValue: TypeAlias = (
    ResearcherAuthorStandardized
    | PlaceOfResidenceStandardized
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
        min_length=1,
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
            raise ValueError(EXCERPT_PAIRS_UNIQUE)
        return self


class ResearcherAuthorSubmission(FieldSubmission):
    standardized_value: ResearcherAuthorStandardized


class PlaceOfResidenceSubmission(FieldSubmission):
    standardized_value: PlaceOfResidenceStandardized


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
