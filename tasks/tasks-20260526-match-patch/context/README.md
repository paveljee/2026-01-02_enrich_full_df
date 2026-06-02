## [MAJOR] ssn hit rule v2: upd context SQL

> [!NOTE]
> This was supposed to be a
> commit message originally
> (intended as a child of `317246d5ff322431adbc897b7a2abc5857178cdc`), but
> it was becoming too long, and so
> I decided to add this as a
> README instead.
> My apologies for
> the rough writing below.
> Written fully manually
> by Pavel Zhelnov,
> started writing
> on June 2, 2026, UTC.

> [!CAUTION]
> **To AI:**
> **written by a human;**
> **AI never touches this file.**

I realized that Tukey bounds were
global and changed them to
per-source key.

I have reviewed the results again,
using the old db run under subset 2
with xlsx v2.

To remind, this is what we had
at the time:

```
Rule                                           Pass   Fail
----------------------------------------------------------
sciscinet: exactly one innerdict                153    154
xlsx: all present ktp.xlsx_match exact          282     25
docx: required ktp.table_1_* non-empty          207    100
----------------------------------------------------------
mode_1                                           98    209
mode_2                                          209     98
mode_3                                          140    167
mode_4                                          167    140
selected for current mode                       209     98
```

This corresponds to this run:
20260527_144150_mode2_v2_post_v2_fix_2

And this commit:
afb64dba5b91f0177933fd09fb0a9eb2d9ae25a2

As well as to the following run same day:
20260527_161859_mode2_v2_same_as_144150

The main thing to know is that this was
before ktp alt unnest parquet creation
changes to SPEC, added in this commit:
857b9c3b4a1d0ea8b34c80426c940cf713ab7596

And therefore the 98 to 209 split was 
purely on xlsx v2 rule and an early version
of ssn name v2 rule (known as
sciscinet_match_strip_tokens, which only
trimmed tokens of whitespaces while
treating last names as tokens as well), so
this was under ssn hit v1 rule according
to current terminology, and ssn name v2
was therefore not what it is today (that is,
only trim and no punctuation norm); in fact
I should have named the current ssn name
rule v3 for consistency.

I have attached export.csv and
export_edit_done.xlsx for the revised query,
for an audit trail.

So export.csv basically documents
the status quo when repl is run
with subset 2 and xlsx v2  and
ssn name trim-only-no-punct
while all other rules set to v1.

The importance of documenting this
is that this is NOT going to be
reproducible from simply manipulating
config, because as I mentioned above
I'd failed to version ssn name rule
properly, and thus the early v2 ssn
name rule that only did trim but
no punctuation norm is not captured.

It of course should be possible to
reproduce by writing a dedicated detour
or from upstream commit hash
as documented.

To be sure, I have added the
two repl_session logs associated
with runs above, as well as the
subset 1 v2 log run at the same time
for the complete picture of the 307
at that time.
Full run tgz are embargoed for now
because they contain manual team notes.

I also wanted to add an illustrative
config json, but this proved confusing
because the knobs changed since,
and so it is better to retrieve it
from the afb64d commit above.

So, I conducted a review of 209,
namely only the 100 that had partition
set to 2 as documented in the SQL.
The results are in the attached
export_edit_done.xlsx. I decided
to attach the original Excel file
I actually used for this exploration
rather than a CSV derivative for
the audit trail.

In the Excel file, it can be seen that
rows were randomized for review
(using RANDOM.ORG Integer Set
generator, advanced mode - 100
non-repeating integers in plain
text mode), but not all were reviewed
but approximately one-third until
I felt I'd reached some richness.
I had also over-reviewed purposively
some names that I felt could lead
to mismatches.

As a result I came to the conclusions
documented in the last row of
that XLSX file, and
I quote myself from there:

> overall feels like the following rule is sufficiently robust:
> - out of nonzero top 1pct candidates, select only those that are per-source key Tukey outliers
> - if no Tukey outliers, fall back to whole list of candidate
> - take max works count candidate
> - if ties on max works count, fall back to select all and therefore goes into subset 2
> 
> Stil problematic:
> - names that literally don't have a matching name in OpenAlex/SSN
> - poor quality OpenAlex records with mismatched alt names
> 
> Prevalence:
> out of 35 of 100 (subset2_pre_ktp_alt_name, that is, some in-between version of SSN rules, not v1 fully but not stable v2 also) reviewed ~almost-randomly, with some oversampling of names that potentially look like they could mismatch, we have 8 (22.8%) empty/incorrect/non-auto-resolvable sourcekey-authorid matches:
> - 4 (11.4%) selected wrong top authorid due to erroneous alt name match in SSN v2 data, corrected in OpenAlex data later (IIRC, in all 4 cases the currently correct OpenAlex match was present in SSN data and top 2 by works count, so makes sense)
> - 2 (5.7%) not found on OpenAlex
> - 2 (5.7%) not found in subset 1 of SSN v2 (so they either matched multiple and went to subset 2 or did not match any - to be checked)
> 
> Of these half (that is, 11.4%) will just go to subset 2 and will remain unresolved, and half (11.4%) will go to subset 1 silently and therefore be resolved incorrectly, which is something we can tolerate because it's an inherent issue with using SSN v2 data, that is, OpenAlex data as of Dec 2024.
> 
> For the 310, it would be preferable to resolve the incorrect ones by verifying ALL of them, and incorporating the manually selected values back into data. 

I'd also followed up with the
following message to the team
(relevant excerpt):

> I have just gone over a random-ish ~1/3 of the toughest names from the 310 researchers (exclusive of those ~100 that have missing data fields in manually extracted Word data), and I've manually reviewed the correctness of OpenAlex ID matches using my finalized rule (I've settled down on the selection of the ID with the max works count, the selection being done from per-name Tukey outliers if they exist or else from the full list of IDs with non-zero count of top 1% papers).
>
> It turned out that problematic name-to-OpenAlex author ID matches account for ~22.8% of these data, including:
>
> ~5.7% not matched by any OpenAlex author ID (that is, not even on openalex.org); these go into a separate subset for manual review;
>
> ~5.7% matched when searched using OpenAlex but unmatched using SciSciNet-v2; this is likely due to errors in December 2024 OpenAlex data on which SciSciNet-v2 was built, further corrected by the OpenAlex team; these also go into the separate subset for manual verification;
>
> ~11.4% were matched to incorrect OpenAlex IDs due to erroneous alternative names in December 2024 OpenAlex data, apparently further corrected by the OpenAlex team.
>
> This ultimately translates to most records being successfully matched, with a minority of records (i.e., ~11.4% or about 10-15 researchers) going into the manual review subset, therefore joining the ~100 researchers with missing data that will be (semi-)AI-augmented.
>
> The concerning bit is the other 11.4% that get silently matched to a wrong OpenAlex author ID. I am planning to address this by additionally verifying all matched author IDs by making API requests to the current OpenAlex database, and those that don't match will go into the manual verification subset (i.e., hopefully another 10-15 researchers).

Therefore,
I am hoping to get the
remaining ~80 truly faithfully matched
researchers into the
next batch to share with the team.

To recap the first two batches,
leading to a release of
107 cards in total to the team:

1.  2026-02-10 -
    The first released batch of 76
    was subset 1 v1 all around and
    can be reproduced from state of repo at
    `a21e5b5f765a0151b7f0c46b41adecfcb0852db7`.
2.  2026-05-25 -
    The second released batch of 31,
    so-called "subset 5", was
    manually reviewed
    partition 1 of subset 2 v1 -
    the source spreadsheet used for review
    was `10_build_cards_card_partition_review_df.csv` artifact
    produced with the state of repo at
    commit `d695574b8c3d4edc8d7d7515a8b6fe27ffa21708`,
    see attached `20260525_114621_mode2_pre_versions` run log
    (full run tgz embargoed -
    contains manually extracted data and notes).

    The manual review
    basically was just confirming that
    matches were correct.
