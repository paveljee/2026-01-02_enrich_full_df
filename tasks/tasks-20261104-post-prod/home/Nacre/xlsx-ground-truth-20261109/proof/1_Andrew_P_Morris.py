"""HCR award review for the first-drawn Andrew P Morris NameKey."""

from pathlib import Path

from shared import HcrAwardReview

SCRIPT_PATH = Path(__file__).resolve()

review = HcrAwardReview(
    draw="1",
    namekey=("Andrew P", "Morris"),
    first_award=("2015_HCR.xlsx", 2112),
    script_path=str(SCRIPT_PATH),
)

review.consider_hcr_names(first_starts="Andrew", last="Morris")
review.consider_hcr_names(first="Andrew P", last_starts="Morr")
review.include_awards_named("Andrew P", "Morris")
review.exclude_awards_named("Andrew D", "Morris")

review.expect_hcr_award_years(2015, 2016, 2017, 2018)
review.expect_hcr_fields("Molecular Biology & Genetics")
review.expect_hcr_affiliation("Dundee", in_years=(2015, 2016))
review.expect_hcr_affiliation("Liverpool", in_years=(2017,))
review.expect_distinct_hcr_awards_in_same_years(2017, 2018)

if __name__ == "__main__":
    review.assign_awards_to_first_draw()
