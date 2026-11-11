"""Historical name-context audit of pilot.1 Bin Gao.

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
    "From model weights I tentatively associate a researcher named Bin Gao with "
    "environmental engineering, biochar, and contaminant sorption, and perhaps "
    "University of Florida. Those recollections are uncertain and may be "
    "contaminated by the HCR rows just read. I do not reliably recall a Rice "
    "University appointment, as written in this 2024 Cross-Field seed row, "
    "or a stable identifier that would confirm a Florida-to-Rice career move."
)
NO_LINK_OR_ID = (
    "Neither Bin Gao award records this field; its absence cannot establish "
    "a shared identity or distinguish two namesakes."
)
COMPARISON_ASSESSMENTS = {
    KTP_FIRST_NAME_COL: {
        "equal": "Bin is the same, but a shared given name can readily be coincidental."
    },
    KTP_LAST_NAME_COL: {
        "equal": "Gao is the same, but a shared family name is not an identity identifier."
    },
    NAME_PAIR_REVIEW_KEY: {
        "equal": (
            "Bin Gao is identical in both awards, yet Rice versus Florida "
            "leaves a namesake possibility."
        )
    },
    FULL_NAME_TOKENS_REVIEW_KEY: {
        "equal": (
            "The token sequence repeats the exact name; it is not independent "
            "evidence against a namesake."
        )
    },
    KTP_HCR_PRIMARY_AFFILIATIONS_COL: {
        "different": (
            "Rice and Florida are different organizations; a move is possible, "
            "but so is a distinct Bin Gao."
        )
    },
    KTP_HCR_SECONDARY_AFFILIATIONS_COL: {
        "both_absent": (
            "Neither award lists a secondary organization that could bridge Rice and Florida."
        )
    },
    KTP_ECONOMY_MATCH_COL: {
        "different": (
            "The affiliation-to-economy mapping changes with the organization; "
            "it does not identify the person."
        )
    },
    KTP_ECONOMIES_COL: {
        "equal": (
            "Both normalize to the United States, a country shared by many "
            "HCRs and possible namesakes."
        )
    },
    KTP_ECONOMIES_INCOME_GROUP_COL: {
        "equal": (
            "Both have the same broad income group because both affiliations "
            "are in the United States; this may coincide."
        )
    },
    HCR_CATEGORY_COL: {
        "equal": (
            "A shared Cross-Field category may be coincidental; it does not "
            "bridge the organizations."
        ),
        "different": (
            "Different HCR categories can be awarded to one multidisciplinary "
            "researcher, so the difference alone does not prove distinct people."
        ),
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
    draw="pilot.1",
    namekey=("Bin", "Gao"),
    first_award=("2024_HCR.xlsx", 1890),
    script_path=__file__,
)

ROLLOUT_EVENT_IDS = (
    "exec-192d583a-a682-4ff9-86ae-9b4257e10a0f",
    "exec-065a9e91-09aa-448e-a776-5b8157a76a85",
    "exec-eba38335-20a8-4944-aed1-5d24529f84b3",
    "exec-6c61447c-8142-4e77-bb74-08785ea797c9",
    "exec-56e1c95a-75a0-4ca8-b1c1-d0c775c5f618",
    "exec-47f69fb3-3429-4867-83b9-b3342c59273e",
    "exec-782bed56-e663-4645-b259-86cc2f73fbfc",
)

assert_printed_read_events_in_rollout(ROLLOUT_EVENT_IDS)
review.attest_name_context(
    observed_spellings=(("Bin", "Gao"),),
    rollout_event_ids=ROLLOUT_EVENT_IDS,
    inference="I observed no plausible alternative spelling beyond Bin/Gao.",
)
review.find_exact_hcr_awards()
review.attest_seed_recollection(SEED_RECOLLECTION)
seed = review.seed_hcr_award

candidate = review.hcr_award(("2018_HCR.xlsx", 1818))
review.attest_candidate(
    candidate,
    reflection=(
        "The exact Bin Gao name and Cross-Field category agree with the Rice seed. "
        "The 2018 'Univ Florida' affiliation differs, but fits the Florida cluster "
        "in later HCR rows; a move before 2024 is plausible. No ID rules out a namesake."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
        same_hcr_value(HCR_CATEGORY_COL, seed.category, candidate.category),
    ),
)

candidate = review.hcr_award(("2019_HCR.xlsx", 3780))
review.attest_candidate(
    candidate,
    reflection=(
        "This Florida Engineering award has the exact Bin Gao name and the same "
        "United States economy as the Rice seed. Engineering fits an environmental "
        "research career, but the affiliation change remains unverified; accept "
        "provisionally rather than treating the name as a unique identifier."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2019_HCR.xlsx", 3987))
review.attest_candidate(
    candidate,
    reflection=(
        "The Florida Environment and Ecology award occurs in the same year as "
        "this name's Florida Engineering award, making a multidisciplinary HCR "
        "cluster plausible. Its exact name matches the Rice seed, while the "
        "Florida-to-Rice link remains unverified and namesakes remain possible."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2020_HCR.xlsx", 3832))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2020 Florida Engineering row repeats the prior Florida Engineering "
        "name, organization, and category pattern. This continuity makes the "
        "same-person reading plausible despite the 2024 Rice affiliation, "
        "which no stable identifier here confirms."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2020_HCR.xlsx", 4041))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2020 Florida Environment and Ecology row repeats the 2019 Florida "
        "category and affiliation under the exact Bin Gao name. The parallel "
        "Engineering listing is plausible for one HCR; it still does not prove "
        "that the later Rice seed is the same individual."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2021_HCR.xlsx", 4075))
review.attest_candidate(
    candidate,
    reflection=(
        "The Florida Engineering category recurs for Bin Gao in 2019, 2020, "
        "and this 2021 row. That sequence looks like continuing recognition of "
        "one researcher, with a possible later move to Rice; a namesake with "
        "the same spelling cannot be excluded from these rows alone."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2021_HCR.xlsx", 4272))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2021 Florida Environment and Ecology entry continues the 2019-2020 "
        "Florida pattern and shares the seed's exact name. In combination with "
        "the Engineering rows, one multidisciplinary HCR is plausible, but "
        "the subsequent Rice affiliation is not independently verified."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2022_HCR.xlsx", 196))
review.attest_candidate(
    candidate,
    reflection=(
        "Biology and Biochemistry is broader than the earlier Florida Engineering "
        "and Environment and Ecology categories, but an environmental scientist "
        "could span them. The exact name and Florida affiliation support the "
        "cluster; there is still no stable ID bridging it to Rice."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2022_HCR.xlsx", 4653))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2022 Florida Environment and Ecology listing continues the same "
        "name, institution, and category seen from 2019 through 2021. That "
        "continuity supports acceptance with the Florida cluster and a possible "
        "later Rice move, not a verified identity bridge."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

candidate = review.hcr_award(("2022_HCR.xlsx", 4835))
review.attest_candidate(
    candidate,
    reflection=(
        "The 2022 Florida Engineering listing likewise continues the 2019-2021 "
        "Engineering sequence under the exact Bin Gao name. The sequence and "
        "the Rice seed's Cross-Field category make one HCR plausible; without "
        "an identifier, the Florida-to-Rice link remains provisional."
    ),
    decision="accept",
    assessments=COMPARISON_ASSESSMENTS,
    comparisons=(
        same_hcr_value(NAME_PAIR_REVIEW_KEY, seed.name, candidate.name),
        same_hcr_value(
            KTP_ECONOMIES_COL, seed.value(KTP_ECONOMIES_COL), candidate.value(KTP_ECONOMIES_COL)
        ),
    ),
)

review.assign_attested_awards_to_first_draw()
