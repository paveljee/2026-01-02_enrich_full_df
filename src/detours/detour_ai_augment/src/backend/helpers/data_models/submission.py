from pydantic import Field

from .mixin import SubmissionMixin
from .pydantic_to_paste import (
    CommentsSubmission,
    FieldSubmission,
    StrictModel,
)
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

class Submission(StrictModel, SubmissionMixin):
    """
    To be used for the first submission only.

    Field descriptions are **not** supplied
    intentionally in order to enable free
    interpretation by the submitter at the
    initial submission.
    
    Note: `class StandardizedFieldSubmission`,
    to be used in resubmissions, is defined in
    `pydantic_to_paste`.

    signed-off: human
    """

    researcher_author: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_RESEARCHER_AUTHOR_COL,
    )
    place_of_residence: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_PLACE_OF_RESIDENCE_COL,
    )
    race_ethnicity_language_culture: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_RACE_ETHNICITY_LANGUAGE_CULTURE_COL,
    )
    gender: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_GENDER_COL,
    )
    age_first_publication: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_AGE_FIRST_PUBLICATION_COL,
    )
    education: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_EDUCATION_COL,
    )
    academic_positions: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_ACADEMIC_POSITIONS_COL,
    )
    social_capital: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_SOCIAL_CAPITAL_COL,
    )
    links: FieldSubmission = Field(
        alias=KTP_AI_AUGMENT_LINKS_COL,
    )
    comments: CommentsSubmission | None = Field(
        default=None,
        alias=KTP_AI_AUGMENT_COMMENTS_COL,
    )
