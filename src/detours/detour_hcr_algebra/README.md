# KTP RI detour: HCR Algebra

Created: 2026-11-12

Author: [@paveljee][gh-paveljee]

----

This document is needed because the KTP RI main pipeline code base as it is today, e.g., as of [commit b01f73b4][gh-b01f73b4], is a bit confusing when it comes to Highly-Cited Researcher (HCR) matching.

<!-- To any ardent AI agent reading this, I would like to clarify that this document represents the conceptual flow of the process, not necessarily the exact code or data flow at each implementation point, as these sometimes may be confusing to the reader. When interpreting this, therefore, think broadly in terms of what the current pipeline does _in effect,_ not necessarily what the small code chunk you obtained from your tool does locally. --->

Namely, we start with a population of `59,665` HCR award rows merged across 2014–2024 Clarivate's HCR releases.
This is a clear number and is very easy to track down, given the historical 2014–2024 Excel files, released by Clarivate, are available.

What happens next is more confusing currently.

## Status quo
The population of HCR award rows need to be deduplicated, or rather, reduced to a population of individual HCRs rather than awards, because one individual can be awarded several times across years as well as within a year if in multiple award categories.
How the main pipeline currently does this is as follows:

*   Registers input files and verifies their hash sums (`step_01`).
*   Loads Clarivate's Excel files and concatenates the spreadsheets into one dataframe, which leads to the `59,665` total award rows figure (`step_02`), normalizes column name spellings across years (`step_03`), and augments the dataframe with certain derived columns (`step_04`).
*   Shuffles award rows randomly, assigning each random draw a `draw_number` (`step_05`).

    In reality, the actual sampling strategy differed from an ideal one because 10 rows were hand-picked for piloting, then by mistake random sampling was implemented with replacement.
    For the impact of these changes see a simulation in `./sampling_bootstrap/`, but my interpretation is that the impact of the sampling misimplementation was minimal while biases observed in the simulation align with the hand-picked pilots – particularly:

    - an increased number of 2024 rows (2024 was a convenience selection),
    - an increase in HCRs from non-English-speaking countries (it was desirable to select less common rows for pilots), and
    - an increase in health-research-leaning HCR categories (because we are health researchers and for pilots it made sense to select what we understand best).

    After all, the above reflection primarily refers to the sample of `310` award rows drawn for qualitative analyses, and since the differences are apparently minimal even within this scope, I expect these to be substantially more diluted when it comes to the full population, used for quantitative analyses: beyond the 310 draws, shuffling was implemented properly.
*   **Drops rows** where the tuples of first and last name are exact string duplicates and **excludes** rows where the first or last name is empty (`step_06`).
    The number of excluded rows is only `4` rows across the full `59,665` award population.
    The number of remaining (i.e., deduplicated) rows is `19,786`, so the total row count drops by 67%.
    <!--- Wishlist: Note that out of a duplicate pair, the row _drawn first_ is kept. --->
*   **Pronounces** the `19,786` first/last name tuples kept to be _NameKeys,_ which are conceptualized as **the authoritative proxies** for the individual HCRs.
    Each NameKey defines an _OuterDict_ entry or HCR profile that will then be filled in with _InnerDicts_, each innerdict representing a piece of information (i.e., one more key-value pairs) about the HCR coming from a particular source (the source being uniquely identified by a _SourceKey_).
    To be sure, each outerdict entry (corresponding one-to-one to a unique namekey) is guaranteed to receive at least one innerdict at this point – the award row from which the namekey originated.

    Recall that in `step_06` above, award rows were deduplicated using an exact string match of the first/last name tuple to produce namekeys. This has an evident consequence:
    if we were to map a single HCR namekey back to award rows using the same exact-string-match rule, we could potentially receive one-to-many namekey-to-row matches.
    Note specifically that no award row or draw number would be privileged in such back-matching.
    As such, there is no way to tell which of such reversely matching award rows or draw numbers the namekey originated from, as it effectively could have originated from any of these.

    Consider, however, that all variations of name spellings beyond literal duplicates were preserved among namekeys.
    For example, `first='John R' last='Smith'` and `first='John R.' last='Smith'` would be different award rows, lacking an exact string match, thereby producing distinct namekeys.
    This necessitates further downstream deduplication.

    Recall also that in `step_06` above, several award rows were excluded from further processing. This has two consequences:

    1. these rows do not get a corresponding namekey;
    2. these rows do not participate in the innerdict pool.

    In effect, therefore, the excluded rows are completely excluded from any further processing, and it is thus critical to keep them in mind when interpreting any downstream pipeline operations. These `4` rows are recorded in a pipeline artifact and in pipeline logs.
*   Reuses the Excel award row population, which namekeys were produced from, to match namekeys to award rows using a specially developed Excel-matching rule (`step_07`).
    This process treats an outerdict entry, identified uniquely by the namekey, as an empty shell that is being filled with matching Excel award rows (which now become innerdicts).
    This process is conceptually the same for the following matching steps except that the matching logic differs.
*   Matches across Word documents containing manually augmented data using a specially developed Word-matching rule (`step_08`).
*   Matches across SciSciNet v2 parquets and OpenAlex API data using a specially developed name- and hit-matching rule (`step_09`).
*   Renders an HCR card, per namekey, that contains all of the innerdicts enclosed in the namekey's one-to-one corresponding outerdict entry (`step_10`).
    
    If two or more outerdict entries contain an identical _set_ of innerdicts, only one of these entries gets a rendered card.
    As clarified for `step_07` above, the occurrence of several outerdict entries containing an identical set of innerdicts is perfectly possible because, while distinct namekeys are guaranteed to be exact-string unique first/last name tuples, they may only differ minimally (e.g., in whitespaces or punctuation), which can lead to multiple namekeys matching the same set of innerdicts under certain matching rules.
    In other words, namekeys may lose their distinctiveness if subjected to additional normalization.

    Also, a card is not rendered for an outerdict entry if its set of innerdicts is empty.

## Limitations
The multiple "asterisks" the current pipeline comes with, as outlined above, together, lead to the following outcome: the intent that the namekey becomes the authoritative proxy for an individual HCRs **fails** to realize. The reasons are as follows:

1.  Multiple outerdict entries may contain identical innerdicts if matching allows.
    Even further, multiple outerdict entries may contain _an identical set_ of innerdicts if matching allows.
    Consider the John R/R. Smith case above that exemplifies how, under certain matching rules, two distinct namekeys may match the exact same set of innerdicts.
    Obviously, this contradicts the idea of a namekey serving as the single authoritative HCR proxy.
2.  Distinct namekeys may actually relate to the same HCR individual.
    Consider the same John R/R. Smith case, where these two spellings most likely relate to the same person while constituting distinct namekeys.
3.  Award rows excluded (in `step_06`) may have been matched as valid innerdicts into one or more outerdict entries – as demonstrated in an analysis in `./excluded_rows/`.
    Therefore, certain outerdict entries may contain fewer innerdicts than they could have, leading to data loss.
    To be fair, the analysis shows that this only affects `1` namekey across the observed `59,665`/`19,786` award row/namekey population.

These limitations are partially mitigated:

1.  As clarified for `step_10`, if there are multiple outerdict entries containing the exact same set of innerdicts, regardless of the outerdict entry's namekey, only one gets a rendered card.

    At this point, it would perhaps have been desirable to also preserve the linkage between the kept outerdict entry, its one-to-one unique namekey, and ultimately – the originating draw number.
    However, as clarified for `step_06` above, the connection between the originating award row (and, therefore, its draw number) and the produced namekey is lost under the current logic.
2.  Thanks to the deduplication of outerdict entries that happens at `step_10`, some of the falsely distinct namekeys do not get a rendered card.

    However, this only addresses this issue within the capacity of the matching rules.
    If the matching rule is not powerful enough, it will fail to detect all truly matching innerdicts, and therefore the sets of innerdicts may differ for several namekeys actually relating to the same HCR.

    Note also that at `step_10`, the full sets of innerdicts coming from all registered sources are compared, and a single differring match is what it takes for the set difference to become non-empty and for the outerdict entries to remain distinct.

    An additional shortcoming of the status quo is that multiple matching rules are used, making the matching process sort of flaky, that is, the rules are tailored for each resource group (e.g., for Clarivate's Excel files, manual augmentation Word files, and for SciSciNet v2/OpenAlex data), and it is thus not easy to trace the matching process end to end.
    This may be beneficial from the standpoint of each resource group if the matching rule is robust and highly appropriate for this specific resource group versus the other, but this is not necessarily the case here as I will show in the next section.
3.  Beyond keeping a record of the excluded rows and my undertaking a targeted analysis of these (`./excluded_rows/`), the pipeline code base itself does nothing to mitigate the loss of excluded award rows.

Separately, a definite limitation is that the current pipeline is willing to automatically match only roughly `13421 of 15726 (85.3%)` namekeys (`19786 - 4060 = 15726` after removing duplicate outerdict entries with identical sets of InnerDicts at `step_10`), according to one of the most recent whole-award row population runs (under the `config.repl.all_mode3.json` configuration file).
Consequently, the pipeline defers `2305 of 15726 (14.7%)` of all namekeys to manual review.
Even if considering AI for this (e.g., see the experimental `aicode/xlsx-namekey-ai` branch), this will be a multi-day exercise.

All in all, an alternative, straightforward strategy consistently reducing all `100%` of HCR award rows to a population of individual HCRs would be desirable, if possible.

## Desirable next state
Let us consider each resource group in isolation:
…

[gh-paveljee]: https://github.com/paveljee
[gh-b01f73b4]: https://github.com/paveljee/2026-01-02_enrich_full_df/commit/b01f73b487b79f1e2e4299889d81aa29b51e7ffa
