"""Review Rudolf A. de Boer's HCR awards from the pilot.4 seed.

Allowed dependencies: stdlib and local `shared`; no pipeline or third-party imports.
"""

from pathlib import Path

from shared import HcrAwardReview

SCRIPT_PATH = Path(__file__).resolve()

review = HcrAwardReview(
    draw="pilot.4",
    namekey=("Rudolf A.", "de Boer"),
    first_award=("2024_HCR.xlsx", 657),
    script_path=str(SCRIPT_PATH),
)

review.consider_hcr_names(last="de Boer")
review.include_awards_named("Rudolf A.", "de Boer")
review.exclude_awards_named("Jacob", "de Boer")

review.expect_hcr_award_years(2022, 2023, 2024)
review.expect_hcr_fields("Clinical Medicine")
review.expect_hcr_affiliation("Erasmus MC", in_years=(2022, 2023, 2024))
review.expect_hcr_secondary_affiliation("Groningen", in_years=(2022, 2023, 2024))

if __name__ == "__main__":
    review.assign_awards_to_first_draw()
