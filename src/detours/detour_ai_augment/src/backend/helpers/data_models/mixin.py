from typing import Generic, Protocol, TypeVar

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


class ValueSubmission(Protocol):
    value: str


# to be supplied by `pydantic_to_paste` downstream
TFieldSubmission = TypeVar("TFieldSubmission", bound=ValueSubmission)
TCommentsSubmission = TypeVar("TCommentsSubmission", bound=ValueSubmission)


class SubmissionMixin(Generic[TFieldSubmission, TCommentsSubmission]):
    researcher_author: TFieldSubmission
    place_of_residence: TFieldSubmission
    race_ethnicity_language_culture: TFieldSubmission
    gender: TFieldSubmission
    age_first_publication: TFieldSubmission
    education: TFieldSubmission
    academic_positions: TFieldSubmission
    social_capital: TFieldSubmission
    links: TFieldSubmission
    comments: TCommentsSubmission | None

    def evidence_items(self) -> tuple[tuple[str, "TFieldSubmission"], ...]:
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
