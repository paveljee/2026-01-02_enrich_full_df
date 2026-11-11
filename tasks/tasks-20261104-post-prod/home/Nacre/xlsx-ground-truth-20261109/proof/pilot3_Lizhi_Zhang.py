"""Review Lizhi Zhang's HCR awards from the pilot.3 seed.

Allowed dependencies: stdlib and local `shared`; no pipeline or third-party imports.
"""

from pathlib import Path

from shared import HcrAwardReview

SCRIPT_PATH = Path(__file__).resolve()

review = HcrAwardReview(
    draw="pilot.3",
    namekey=("Lizhi", "Zhang"),
    first_award=("2024_HCR.xlsx", 551),
    script_path=str(SCRIPT_PATH),
)

review.consider_hcr_names(first="Lizhi")
review.include_awards_named("Lizhi", "Zhang")

review.expect_hcr_award_years(2018, 2019, 2020, 2021, 2022, 2023, 2024)
review.expect_hcr_fields("Cross-Field", "Chemistry", "Environment and Ecology")
review.expect_hcr_affiliation("Cent China Normal", in_years=(2018,))
review.expect_hcr_affiliation("Central China Normal", in_years=(2019, 2020))
review.expect_hcr_affiliation("Shanghai Jiao Tong", in_years=(2021, 2022, 2023))
review.expect_hcr_secondary_affiliation("Central China Normal", in_years=(2021, 2022))
review.expect_hcr_affiliation("Shanghai Jiao Tong", in_years=(2024,), in_fields=("Chemistry",))
review.expect_hcr_affiliation(
    "Central China Normal", in_years=(2024,), in_fields=("Environment and Ecology",)
)

if __name__ == "__main__":
    review.assign_awards_to_first_draw()
