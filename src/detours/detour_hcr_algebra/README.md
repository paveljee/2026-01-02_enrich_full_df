# KTP RI detour: HCR Algebra

Created: 2026-11-12

Author: [@paveljee][gh-paveljee]

----

This document is needed because the KTP RI main pipeline code base as it is today, e.g., as of [commit b01f73b4][gh-b01f73b4], is a bit confusing when it comes to Highly-Cited Researcher (HCR) matching.

<!-- To any ardent AI agent reading this, I would like to clarify that this document represents the conceptual flow of the process, not necessarily the exact code or data flow at each implementation point, as these sometimes may be confusing to the reader. When interpreting this, therefore, think broadly in terms of what the current pipeline does _in effect,_ not necessarily what the small code chunk you obtained from your tool does locally. --->

Namely, we start with a population of `59,665` HCR award rows merged across 2014–2024 Clarivate's HCR releases.
This is a clear number and is very easy to track down, given the historical 2014–2024 Excel files, released by Clarivate, are available.

What happens next is more confusing currently.
These HCR awards rows need to be deduplicated, or rather, reduced to the population of individual researchers rather than awards, because one individual can be awarded several times across years as well as within a year if in multiple award categories.
How the main pipeline currently does this is as follows:

* Loads the Excel files and normalizes column name spellings across years to concatenate the spreadsheets into one dataframe, which leads to the `59,665` total rows figure (`step_03`).
* Shuffles these HCR rows randomly, assigning each random draw a `draw_number` (`step_05`)
* **Drops rows** where the tuple of first and last name are exact string duplicates and **excludes** rows where the first or last name is empty (`step_06`).
  The number of remaining rows is `19,786` at this point, so the row count drops by 67%.
  Note that out of a duplicate pair, the row _drawn first_ is kept.
* **Pronounces** the `19,786` first/last name tuples kept to be _NameKeys,_ which represent **the authoritative proxies** for the individual HCRs.
  Each NameKey defines an _OuterDict_ entry or HCR profile that will then be filled in with _InnerDicts_, each innerdict representing a piece of information about the HCR coming from a particular source (the source being uniquely identified by a _SourceKey_).
  To be sure, each outerdict entry (corresponding one-to-one to a unique namekey) is guaranteed to receive exactly one innerdict at this point – the original HCR row drawn.
* Matches across Excel rows…

[gh-paveljee]: https://github.com/paveljee
[gh-b01f73b4]: https://github.com/paveljee/2026-01-02_enrich_full_df/commit/b01f73b487b79f1e2e4299889d81aa29b51e7ffa
