"""HCR award review for the second-drawn Tobin J. Marks NameKey."""

from pathlib import Path

from shared import HcrAwardReview

SCRIPT_PATH = Path(__file__).resolve()

review = HcrAwardReview(
    draw="2",
    namekey=("Tobin J.", "Marks"),
    first_award=("2023_HCR.xlsx", 528),
    script_path=str(SCRIPT_PATH),
)

review.consider_hcr_names(first_contains="Tobin")
review.include_awards_named("Tobin J", "Marks")

review.expect_hcr_award_years(*range(2014, 2025))
review.expect_hcr_fields("Chemistry", "Materials Science")
review.expect_hcr_affiliation("Northwestern", in_years=(2014, 2015, 2016, 2017))

if __name__ == "__main__":
    review.assign_awards_to_first_draw()
