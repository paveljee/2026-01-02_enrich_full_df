from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Final

from pydantic import BaseModel, HttpUrl

from ..locale import Locale
from .pydantic_to_paste import (
    AcademicInstitution,
    AcademicPositionsSubmission,
    AgeFirstPublicationSubmission,
    CommentsSubmission,
    CurrentAcademicPosition,
    EducationRecord,
    EducationSubmission,
    FieldSubmission,
    FormerAcademicPosition,
    GenderSubmission,
    ISCEDTertiaryLevel,
    PlaceOfResidenceStandardized,
    PlaceOfResidenceSubmission,
    RaceEthnicityLanguageCultureStandardized,
    RaceEthnicityLanguageCultureSubmission,
    ResearcherAuthorStandardized,
    ResearcherAuthorSubmission,
    ResearcherLink,
    ResearcherLinksSubmission,
    SocialCapitalSubmission,
    StandardizedSubmission,
    WebSearchExcerpt,
)
from .submission import Submission


class SubmissionFixture(BaseModel):
    """One complete pull identity and its Pydantic-valid push submission."""

    identity: tuple[str, str]
    submission: Submission | StandardizedSubmission


EVIDENCE_DEF: Final[Callable[[str], WebSearchExcerpt]] = lambda claim: WebSearchExcerpt(
    excerpt=Locale.EXAMPLE_EXCERPT_TEMPLATE.format(claim=claim),
    url=Locale.EXAMPLE_RESULT_URL,
)

# Note: originally generated via chatgpt.com
# on 2026-07-27 UTC, using GPT-5.6-Sol-High
# with tools (context lost); edited manually.
PRINCETON = AcademicInstitution.model_construct(
    organization_name="Princeton University",
    openalex_id=HttpUrl("https://openalex.org/I20089843"),
    ror=HttpUrl("https://ror.org/00hx57361"),
)
CALTECH = AcademicInstitution.model_construct(
    organization_name="California Institute of Technology",
    openalex_id=HttpUrl("https://openalex.org/I122411786"),
    ror=HttpUrl("https://ror.org/05dxps055"),
)
STANFORD = AcademicInstitution.model_construct(
    organization_name="Stanford University",
    openalex_id=HttpUrl("https://openalex.org/I97018004"),
    ror=HttpUrl("https://ror.org/00f54p054"),
)
GOOGLE = AcademicInstitution.model_construct(
    organization_name="Google (United States)",
    openalex_id=HttpUrl("https://openalex.org/I1291425158"),
    ror=HttpUrl("https://ror.org/00njsd438"),
)
# perhaps not really academic but ok
WORLD_LABS = AcademicInstitution.model_construct(
    organization_name="World Labs",
    openalex_id="NR",
    ror="NR",
)
L_FEI_FEI_INITIAL_FIXTURE: Final = SubmissionFixture(
    identity=("L.", "Fei-Fei"),
    submission=Submission.model_construct(
        researcher_author=FieldSubmission(
            value="Fei-Fei Li; publishes as L. Fei-Fei.",
            web_search_excerpts=[EVIDENCE_DEF("the name")],
        ),
        place_of_residence=FieldSubmission(
            value="Stanford campus, Stanford, California.",
            web_search_excerpts=[EVIDENCE_DEF("the value")],
        ),
        race_ethnicity_language_culture=FieldSubmission(
            # Note: This variable was not in the original GPT's generation;
            # partially generative and partially manual from later.
            value="Works primarily in English; Stanford Curriculum Vitae PDF also reports Mandarin. Race, ethnicity, and culture not collected.",
            web_search_excerpts=[
                EVIDENCE_DEF("English as a target web search language"),
                EVIDENCE_DEF("Mandarin as a target web search language"),
            ],
        ),
        gender=FieldSubmission(
            value="Female.",
            web_search_excerpts=[EVIDENCE_DEF("the value")],
        ),
        age_first_publication=FieldSubmission(
            value=(
                "28–29; born in 1976, with the earliest visible work on the OpenAlex "
                "profile dated 2005."
            ),
            web_search_excerpts=[
                EVIDENCE_DEF("the age/year of birth"),
                EVIDENCE_DEF("the earliest visible publication date"),
            ],
        ),
        education=FieldSubmission(
            value=(
                "B.A. Physics, Princeton University, 1999; M.S. Electrical "
                "Engineering, Caltech, 2001; Ph.D. Electrical Engineering, "
                "Caltech, 2005."
            ),
            web_search_excerpts=[
                EVIDENCE_DEF("the bachelor degree place and year"),
                EVIDENCE_DEF("the master's degree place and year"),
                EVIDENCE_DEF("the PhD degree place and year"),
            ],
        ),
        academic_positions=FieldSubmission(
            value=(
                "Sequoia Capital Professor of Computer Science, Stanford; Senior "
                "Fellow, Stanford HAI; Professor by courtesy, Stanford Graduate "
                "School of Business; former Director, Stanford AI Lab, 2013–2018; "
                "former Vice President and Chief Scientist of AI/ML, Google Cloud, "
                "2017–2018; Co-founder and CEO, World Labs."
            ),
            web_search_excerpts=[
                EVIDENCE_DEF("the current academic position at Standford University"),
                EVIDENCE_DEF("the current academic position at Stanford HAI"),
                EVIDENCE_DEF(
                    "the current academic position at Stanford Graduate School of Business"
                ),
                EVIDENCE_DEF("the former academic position at Stanford AI Lab and the years"),
                EVIDENCE_DEF("the former academic position at Google Cloud and the years"),
                EVIDENCE_DEF("the current academic position at World Labs"),
            ],
        ),
        social_capital=FieldSubmission(
            value=(
                "Founding Co-Director, Stanford HAI; Co-founder and Chair, AI4ALL; "
                "member of the National Academy of Engineering, National Academy "
                "of Medicine, American Academy of Arts and Sciences, and Council "
                "on Foreign Relations; ACM Fellow; UN special adviser."
            ),
            web_search_excerpts=[
                EVIDENCE_DEF("the professional membership/honours at Stanford HAI"),
                EVIDENCE_DEF("the professional membership/honours at AI4ALL"),
                EVIDENCE_DEF(
                    "the professional membership/honours at the National Academy of Engineering"
                ),
                EVIDENCE_DEF(
                    "the professional membership/honours at the National Academy of Medicine"
                ),
                EVIDENCE_DEF(
                    "the professional membership/honours at the American Academy of Arts and Sciences"
                ),
                EVIDENCE_DEF(
                    "the professional membership/honours at the Council on Foreign Relations"
                ),
                EVIDENCE_DEF("the professional membership/honours at ACM"),
                EVIDENCE_DEF("the professional membership/honours at UN"),
            ],
        ),
        links=FieldSubmission(
            value=(
                "Stanford profile: https://profiles.stanford.edu/fei-fei-li; "
                "OpenAlex: https://openalex.org/A5100450462; "
                "AI4ALL: https://ai-4-all.org/our-people/fei-fei-li/"
            ),
            web_search_excerpts=[
                EVIDENCE_DEF("the Stanford profile link/identifier"),
                EVIDENCE_DEF("the OpenAlex link/identifier"),
                EVIDENCE_DEF("the AI4ALL link/identifier"),
            ],
        ),
        comments=CommentsSubmission(
            value=(
                "OpenAlex appears to conflate this author with unrelated researchers "
                "and institutions; age at first publication is therefore provisional."
            )
        ),
    ),
)
# first initialize from initial, then will mutate below
L_FEI_FEI_RETRY_FIXTURE: Final = SubmissionFixture(
    identity=deepcopy(L_FEI_FEI_INITIAL_FIXTURE.identity),
    submission=StandardizedSubmission.model_construct(
        researcher_author=ResearcherAuthorSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.researcher_author))
        ),
        place_of_residence=PlaceOfResidenceSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.place_of_residence))
        ),
        race_ethnicity_language_culture=RaceEthnicityLanguageCultureSubmission.model_construct(
            **deepcopy(
                vars(
                    L_FEI_FEI_INITIAL_FIXTURE
                    .submission
                    .race_ethnicity_language_culture
                )
            )
        ),
        gender=GenderSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.gender))
        ),
        age_first_publication=AgeFirstPublicationSubmission.model_construct(
            **deepcopy(
                vars(L_FEI_FEI_INITIAL_FIXTURE.submission.age_first_publication)
            )
        ),
        education=EducationSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.education))
        ),
        academic_positions=AcademicPositionsSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.academic_positions))
        ),
        social_capital=SocialCapitalSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.social_capital))
        ),
        links=ResearcherLinksSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.links))
        ),
        comments=CommentsSubmission.model_construct(
            **deepcopy(vars(L_FEI_FEI_INITIAL_FIXTURE.submission.comments))
        ),
    ),
)
L_FEI_FEI_RETRY_FIXTURE.submission.researcher_author.value += (
    " ORCID 0000-0002-7481-0810; OpenAlex ID A5100450462."
)
L_FEI_FEI_RETRY_FIXTURE.submission.researcher_author.web_search_excerpts.extend([
    EVIDENCE_DEF("the ORCID"),
    EVIDENCE_DEF("the OpenAlex ID"),
])
L_FEI_FEI_RETRY_FIXTURE.submission.researcher_author.standardized_value = ResearcherAuthorStandardized(
    first_name="Fei-Fei",
    last_name="Li",
    orcid="https://orcid.org/0000-0002-7481-0810",
    openalex_id="https://openalex.org/A5100450462",
)
L_FEI_FEI_RETRY_FIXTURE.submission.place_of_residence.standardized_value = PlaceOfResidenceStandardized(
    place="Stanford campus, Stanford, California",
    location="US",
)
L_FEI_FEI_RETRY_FIXTURE.submission.race_ethnicity_language_culture.standardized_value = RaceEthnicityLanguageCultureStandardized(
    race="NA",
    ethnicity="NA",
    language=["eng","cmn"],
    culture="NA",
)
L_FEI_FEI_RETRY_FIXTURE.submission.gender.standardized_value = "Woman"
L_FEI_FEI_RETRY_FIXTURE.submission.age_first_publication.standardized_value = 1976
L_FEI_FEI_RETRY_FIXTURE.submission.education.standardized_value = [
    EducationRecord.model_construct(
        degree_conferred="B.A. Physics",
        isced_level=ISCEDTertiaryLevel.LEVEL_6,
        place_conferred=PRINCETON,
        year_conferred=1999,
    ),
    EducationRecord.model_construct(
        degree_conferred="M.S. Electrical Engineering",
        isced_level=ISCEDTertiaryLevel.LEVEL_7,
        place_conferred=CALTECH,
        year_conferred=2001,
    ),
    EducationRecord.model_construct(
        degree_conferred="Ph.D. Electrical Engineering",
        isced_level=ISCEDTertiaryLevel.LEVEL_8,
        place_conferred=CALTECH,
        year_conferred=2005,
    ),
]
L_FEI_FEI_RETRY_FIXTURE.submission.academic_positions.standardized_value = [
    CurrentAcademicPosition.model_construct(
        academic_position="Sequoia Capital Professor of Computer Science",
        academic_institution=STANFORD,
    ),
    CurrentAcademicPosition.model_construct(
        academic_position="Senior Fellow at Stanford HAI",
        academic_institution=STANFORD,
    ),
    CurrentAcademicPosition.model_construct(
        academic_position="Professor by courtesy at the Graduate School of Business",
        academic_institution=STANFORD,
    ),
    FormerAcademicPosition.model_construct(
        academic_position="Director of the AI Lab",
        academic_institution=STANFORD,
        start=2013,
        end=2018,
    ),
    FormerAcademicPosition.model_construct(
        academic_position="Vice President and Chief Scientist of AI/ML at Google Cloud",
        academic_institution=GOOGLE,
        start=2017,
        end=2018,
    ),
    CurrentAcademicPosition.model_construct(
        academic_position="Co-founder and CEO",
        academic_institution=WORLD_LABS,
    ),
]
L_FEI_FEI_RETRY_FIXTURE.submission.social_capital.standardized_value = [
    "Founding Co-Director, Stanford HAI",
    "Co-founder and Chair, AI4ALL",
    "Member, National Academy of Engineering",
    "Member, National Academy of Medicine",
    "Member, American Academy of Arts and Sciences",
    "Member, Council on Foreign Relations",
    "ACM Fellow",
    "United Nations special adviser",
]
L_FEI_FEI_RETRY_FIXTURE.submission.links.standardized_value = [
    ResearcherLink(
        url="https://profiles.stanford.edu/fei-fei-li",
        verified_with_orcid=False,
    ),
    ResearcherLink(
        url="https://openalex.org/A5100450462",
        verified_with_orcid=False,
    ),
    ResearcherLink(
        url="https://ai-4-all.org/our-people/fei-fei-li/",
        verified_with_orcid=False,
    ),
]
