"""Historical name-context audit of pilot.2 Beatriz Roldan Cuenya.

Allowed dependencies: stdlib and the local shared module only.
"""

from shared import (
    FULL_NAME_TOKENS_REVIEW_KEY,
    HCR_CATEGORY_COL,
    HCR_INSTITUTIONAL_PROFILE_COL,
    HCR_LINKEDIN_COL,
    HCR_ORCID_COL,
    HCR_RESEARCHER_ID_COL,
    HCR_TWITTER_COL,
    HCR_UNNAMED_6_COL,
    HCR_UNNAMED_7_COL,
    HCR_UNNAMED_8_COL,
    KTP_ECONOMIES_COL,
    KTP_ECONOMIES_INCOME_GROUP_COL,
    KTP_ECONOMY_MATCH_COL,
    KTP_FIRST_NAME_COL,
    KTP_HCR_PRIMARY_AFFILIATIONS_COL,
    KTP_HCR_SECONDARY_AFFILIATIONS_COL,
    KTP_LAST_NAME_COL,
    NAME_PAIR_REVIEW_KEY,
    HcrAwardReview,
    assert_printed_read_events_in_rollout,
    same_hcr_value,
)

SEED_RECOLLECTION = (
    "From model weights I tentatively associate Beatriz Roldan Cuenya with "
    "heterogeneous catalysis and nanoscale catalysts, perhaps at the Fritz "
    "Haber Institute of the Max Planck Society. This is compatible with the "
    "2024 Chemistry seed at Ruhr University Bochum, but I cannot verify from "
    "memory the Ruhr appointment, HCR award chronology, exact first/last "
    "partition, or stable ID. The recollection is unverified and may be "
    "contaminated by the source row just read."
)
NO_LINK_OR_ID = (
    "Neither Beatriz Roldan Cuenya award records this field; the absence "
    "neither confirms one identity nor separates the two name forms."
)
COMPARISON_ASSESSMENTS = {
    KTP_FIRST_NAME_COL: {
        "different": (
            "The seed places Roldan in the first-name field while the older "
            "award does not; the full token sequence is unchanged, so this "
            "need not be another person."
        )
    },
    KTP_LAST_NAME_COL: {
        "different": (
            "The older award places Roldan with Cuenya in the last-name field; "
            "that boundary shift does not by itself distinguish people."
        )
    },
    NAME_PAIR_REVIEW_KEY: {
        "different": (
            "The first/last pair differs only in where Roldan is split; the "
            "same full name could be one person or a namesake."
        )
    },
    FULL_NAME_TOKENS_REVIEW_KEY: {
        "equal": (
            "Beatriz Roldan Cuenya has the same three tokens in order; a "
            "namesake remains possible, but this particular sequence makes "
            "coincidence less plausible."
        )
    },
    KTP_HCR_PRIMARY_AFFILIATIONS_COL: {
        "different": (
            "Ruhr University Bochum and Max Planck Society are different "
            "organizations; a move or multiple affiliations is possible, so "
            "this does not establish different people."
        )
    },
    KTP_HCR_SECONDARY_AFFILIATIONS_COL: {
        "both_absent": (
            "Neither award supplies a secondary organization that could "
            "connect Ruhr and Max Planck."
        )
    },
    KTP_ECONOMY_MATCH_COL: {
        "different": (
            "The economy-match mapping names each different organization; "
            "the mapping difference is not an individual identifier."
        )
    },
    KTP_ECONOMIES_COL: {
        "equal": (
            "Both organizations normalize to Germany, but many different "
            "researchers share that country."
        )
    },
    KTP_ECONOMIES_INCOME_GROUP_COL: {
        "equal": (
            "Both German affiliations yield the same broad income group; "
            "this is not independent identity evidence."
        )
    },
    HCR_CATEGORY_COL: {
        "different": (
            "Chemistry versus Cross-Field is compatible with one "
            "multidisciplinary HCR and does not by itself require distinct people."
        )
    },
    HCR_RESEARCHER_ID_COL: {"both_absent": NO_LINK_OR_ID},
    HCR_UNNAMED_6_COL: {"both_absent": NO_LINK_OR_ID},
    HCR_UNNAMED_7_COL: {"both_absent": NO_LINK_OR_ID},
    HCR_UNNAMED_8_COL: {"both_absent": NO_LINK_OR_ID},
    HCR_INSTITUTIONAL_PROFILE_COL: {"both_absent": NO_LINK_OR_ID},
    HCR_LINKEDIN_COL: {"both_absent": NO_LINK_OR_ID},
    HCR_ORCID_COL: {"both_absent": NO_LINK_OR_ID},
    HCR_TWITTER_COL: {"both_absent": NO_LINK_OR_ID},
}

review = HcrAwardReview(
    draw="pilot.2",
    namekey=("Beatriz Roldan", "Cuenya"),
    first_award=("2024_HCR.xlsx", 383),
    script_path=__file__,
)

ROLLOUT_EVENT_IDS = (
    "exec-18c02972-6bc3-444a-8f6b-e8a62c65a255",
    "exec-13288c3e-9b7e-4901-bf62-e2cb2f374afa",
    "exec-fffe5221-a18b-457b-b778-5a5882d2d8ee",
    "exec-d81feb3e-b1cb-4283-91c7-e763aff8a7f7",
    "exec-f38d0d61-7f0b-4ff3-9347-39f7d792589c",
    "exec-80a99e7e-659f-43ed-82f1-f0115275acae",
    "exec-299af1c7-20b8-427e-a425-059467be8052",
)

assert_printed_read_events_in_rollout(ROLLOUT_EVENT_IDS)
review.attest_name_context(
    observed_spellings=(("Beatriz Roldan", "Cuenya"), ("Beatriz", "Roldan Cuenya")),
    rollout_event_ids=ROLLOUT_EVENT_IDS,
    inference="I observed Beatriz/Roldan Cuenya as a plausible name-boundary variant.",
)
review.find_exact_hcr_awards()
review.attest_seed_recollection(SEED_RECOLLECTION)
seed = review.seed_hcr_award

candidate = review.hcr_award(("2021_HCR.xlsx", 3079))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2021 Max Planck Cross-Field award has the same ordered full name as "
        "the Ruhr Chemistry seed, with Roldan placed on the other side of the "
        "first/last boundary. That is a plausible recording difference; a later "
        "institutional move and multidisciplinary recognition are plausible, "
        "but no stable ID proves the link."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(
            FULL_NAME_TOKENS_REVIEW_KEY, seed.full_name_tokens, candidate.full_name_tokens
        ),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2022_HCR.xlsx", 3470))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2022 Max Planck Cross-Field row repeats the 2021 full name, "
        "name-field partition, institution, and category, making a continuing "
        "HCR record plausible. Its full name also matches the 2024 Ruhr seed; "
        "the Max Planck-to-Ruhr bridge remains unverified by an identifier."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(
            FULL_NAME_TOKENS_REVIEW_KEY, seed.full_name_tokens, candidate.full_name_tokens
        ),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2023_HCR.xlsx", 3497))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2023 Max Planck Cross-Field row extends a three-year run under "
        "the same full name and organization immediately before the 2024 Ruhr "
        "Chemistry seed. The chronology and unchanged full-name tokens favor "
        "one researcher, while the affiliation change is still not proven."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(
            FULL_NAME_TOKENS_REVIEW_KEY, seed.full_name_tokens, candidate.full_name_tokens
        ),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

review.assign_attested_awards_to_first_draw()
