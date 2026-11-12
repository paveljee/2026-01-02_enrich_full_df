*URL:* https://claude.ai/chat/8d980fd6-74a5-454a-8590-80bb8c8207e3  
*Created:* 11/12/2026, 3:01:14 PM  
*Updated:* 11/12/2026, 4:01:31 PM  
*Model:* `claude-sonnet-5-5`

# Statistical review request

__________

## 0 - Human  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 3:01:14 PM

as a chief statistician, please check the attached my dear. any.. concerns?

**File:**   
*ID:* `f7969696-5ee3-5659-910d-d3c818b0e142`

__________

## 1 - Claude  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 3:03:28 PM


<details>
<summary>*[Code Execution Claude thinking...]* Checking the claimed sound parts and what the findings rest on.</summary>


</details>

I read it closely but haven't run it, since I don't have the DuckDB file, so everything below comes from reading the code. The mechanics are mostly sound. My concerns are about what the inference is for.

## Main concerns

**1. You're testing a quantity you can write down.** Both designs have exact expectations. For any indicator, E[protocol] − E[fair] = (number of the ten pilots with that attribute) − 10 × (population share). That is deterministic and nonzero for almost everything. So the p-values, Holm adjustment, and bootstrap CIs only measure how noisy 20,000 replicates are. Double `REPS` and more metrics become "discoveries." This also makes the "nominal false positives if all nulls hold" row meaningless, since the nulls are false by construction.

I'd replace the significance machinery with three things:
- The bias, exact where possible.
- The bias in units of the per-sample SD.
- Where the observed sample falls in each design's simulated distribution. Right now the observed column sits beside the means with no reference to spread, which is the comparison readers actually want.

**2. Two departures are confounded.** The "actual protocol" bundles hand-picked pilots with replacement. Expected coincident pairs are about C(310,2)/59,665 ≈ 0.8, so replacement moves distinct counts by under one row. Ten pilots, all from 2024, shift the 2024 count by roughly 10 × (1 − p₂₀₂₄), which is large relative to the per-sample SD. I'd add a third arm: ten pilots plus 300 draws without replacement from the other rows. That arm is also exactly the protocol conditioned on what actually happened (no duplicates, no pilot redraw). Incidentally, a clean run had only about a 45% chance (e^−0.8), so the stored run being clean is unremarkable.

**3. The practical consequence isn't stated.** Pilots have inclusion probability 1, while other rows have roughly 0.5%. Any downstream analysis that treats the 310 as a simple random sample is biased toward pilot attributes by about (10/310) × (pilot share − population share). The simplest fixes are to analyze only the 300 random draws, which are a valid iid sample, or to use inverse-probability weights. That deserves a sentence in the report.

## Smaller issues

- **Completion checks are tautological.** "Distinct award rows per completed run" prints `population_size` rather than a measurement, and the uniqueness assert can't fail by construction. It says nothing about the sampling question.
- **Shared RNG stream.** The completion block consumes `rng` mid-loop, so changing `BATCH` or that block changes later batches' draws. Use `SeedSequence.spawn` for separate streams.
- **Draws versus rows.** Feature means count draws with multiplicity, but the report calls them "row counts," while `distinct_awards` counts distinct rows. The effect is tiny but the labels are inconsistent.
- **Inconsistent null handling.** Income gets a `<missing>` bucket, but null categories and priorities are silently dropped, so those one-hot groups don't sum to 1 and the null share is invisible.
- **Inconsistent blank tests.** NameKey eligibility uses `!= ""`, while the nonblank indicator uses `.strip()`. Whitespace-only names are valid keys in one place and blank in the other. Exact first+last matching also merges homonyms and splits spelling variants, so "distinct NameKeys" is only a proxy for people.
- **Top-ten ranking.** Ranking by absolute row difference favors prevalent categories and is dominated by two mechanical metrics (`pilot_row_occurrences` and 2024, which also appears twice). Rank by standardized difference and drop pilot occurrences.
- **Two discovery procedures.** "CIs excluding zero" uses the percentile bootstrap, while the Holm count uses normal p-values, so the two counts aren't comparable. The bootstrap also just re-derives the Welch SE you already compute, and 1,000 resamples gives coarse tail quantiles. I'd drop it, and the name "bootstrap" in the docstring is a bit misleading.
- **Unverified report text.** The statement that neither duplication nor pilot redraw occurred is hardcoded prose. Add `assert actual[0] == 310 and actual[3] == 10`, so the report can't claim it if the data change.
- **Unit of analysis.** Rows from multi-year awardees recur, so row sampling is size-biased toward researchers with more awards. That's fine if intended, but I'd state it.

## Checked and fine

- The Holm step-down with cumulative max.
- The two-sided `erfc` p-value.
- Column alignment between the SELECT list and the feature construction.
- The distinct-NameKey logic with the −1 sentinel.
- The sort-based distinct counts.
- The 2024 column mapping.
- The normal approximation, which is adequate even for the rarest indicators at 20,000 replicates.

If it helps, I can sketch a revised version with the third arm, exact expectations, and standardized differences, which would also be shorter than the current version.

__________

## 2 - Human  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 3:10:44 PM

ehh i wonder if you actually read the prose comments/printed messages in the report builder in the script. did you?

__________

## 3 - Claude  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 3:11:47 PM


<details>
<summary>*[Code Execution Claude thinking...]* Checking the newest critique points against the report's wording.</summary>


</details>

Yes, I read it, but rereading it now, I weighted the code over the prose and got some things wrong.

**An error.** I said 2024 "appears twice" in the top-ten ranking. The prose says the 2024 core count "duplicates the year:2024 count and is tested once", and the code does that by leaving column 2 out of `test_columns`. It appears once. My point about absolute row differences favoring prevalent categories still stands.

**Things the prose already says that I criticized as if it didn't:**
- The report says twice (in the inference section and the closing method note) that the CIs and p-values measure Monte Carlo precision of the design-mean contrast, not sample-to-sample variation. So I overstated the risk that readers misread the machinery. What survives is a narrower tension: that disclaimer sits beside "tests whether the means differ", a Holm count, and a "nominal false positives if all nulls hold" row. Those treat the nulls as live when the expected differences are known analytically.
- Bundling pilots with replacement is deliberate, since the report defines the "actual protocol" as exactly that. "Confounded" was the wrong word, and the third arm would aid attribution rather than fix a flaw. There is still a prose-level problem: the intro foregrounds "unintentionally used replacement," but replacement moves distinct counts by under one row, while the pilots drive the large differences. A reader will likely blame the wrong departure.
- The docstring says the completion block doesn't alter the first-310 statistics, and the completion section documents that. Fair enough. The table still presents constants as results, and the claim holds in distribution but not bit for bit, because that block consumes the shared `rng`.

**Things I missed:**
- The docstring says 128 MiB, but the code sets `'128MB'`. As I recall, DuckDB treats MB as decimal and MiB as binary, so that's about 122 MiB. It's tiny, but worth verifying.
- The data-lineage steps (hash checks, header normalization, string coercion, World Bank matching) describe code that isn't in this file. I can only confirm that the join keys (filename plus Excel row) match what step 2 describes. I can't vouch for the rest.

From the prose, I did catch the hardcoded "neither duplication nor pilot redraw occurred" claim, the "row counts" versus draws wording, the "bootstrap" label, and the nominal-false-positives row. The rounding description matches `format_number`.

Was there something specific in the prose you had in mind?

__________

## 4 - Human  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 3:15:40 PM

to clarify, my dear CHIEF statistician, what this exercise is for: we executed some sampling strategy ("actual procotol") which ended up being messy. it's irrelevant what the observed metrics are - well, for the purpose of this exercise. the only thing that matters is _our_ sampling strategy _departed_ from an ideal ("fair") one we could have used: fair coin. two departures: 1) we handpicked 10 rows manually ; 2) we , by error, sampled with replacement for 300 draws. this is supposed, by simulating multiple draws from the _actual_ population, to test how our strategy performs against the fair one. is that clearer? what concerns remain?

__________

## 5 - Claude  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 3:17:00 PM


<details>
<summary>*[Code Execution Claude thinking...]* Reviewing the remaining issues and what the simulation should report.</summary>


</details>

Yes, that's clearer, and it changes my picture. This is a design-comparison simulation, not inference on the observed sample, so two of my earlier suggestions drop out: placing the observed sample inside each design's distribution, and the downstream-analysis point about inclusion probabilities. The "Observed" columns are just context.

Here is what remains, in order of importance.

## 1. The hypothesis-testing layer answers the wrong question

With the purpose now clear, I'd soften my earlier "meaningless" to "not what you need," but the problem stands. For any indicator, the true design difference is exactly 10 × (pilot share − population share) rows per sample, and it is nonzero for nearly every attribute. The p-values, Holm count, "nominal false positives if all nulls hold" row, and bootstrap CIs therefore don't describe the strategy. They describe how finely 20,000 replicates resolve a known number. Double `REPS` and the Holm count grows.

What does measure how the strategy performs against the fair design:
- **Bias in rows**, with the analytic value alongside the simulated one. That doubles as a correctness check on the simulation.
- **Bias in SD units** of the fair design (equivalently, the bias in an estimated proportion as a multiple of its standard error).
- **Actual coverage** of a nominal 95% interval for the population proportion. This is the most direct "how does it perform" number. As an illustration, if 2024 is about 9% of rows, the pilots bias the 2024 share by about 1.8 SEs, and nominal 95% coverage would fall to roughly 55%. A p-value of `<0.0001` conveys none of that.

The Monte Carlo SE of each difference is worth printing as precision, and then the p-values, Holm, and bootstrap can go (the bootstrap just re-derives the Welch SE you already compute).

## 2. Two departures, but only one comparison

The report compares the combined protocol to fair, so it can't say which departure causes what. A 2×2 would:

| | Without replacement | With replacement |
|---|---|---|
| **No pilots** | fair | 310 draws with replacement |
| **10 pilots** | 10 pilots + 300 without replacement from the other rows | actual protocol |

The contrasts then separate hand-picking, replacement, and their interaction. I expect replacement to be nearly null, since there are about 0.8 expected collisions per sample and about 0.05 expected pilot redraws, while the pilots drive almost everything. The prose currently leads with "unintentionally used replacement," so readers will likely blame the wrong departure.

## 3. Scope statements the report should make

- **The hand-pick effect belongs to these 10 rows.** The simulation conditions on the actual pilots, so a different hand-pick would give a different bias. That's legitimate, but the wording should say "this hand-pick," not "hand-picking."
- **Size-bias cancels.** Row-uniform sampling favors researchers with multiple awards, but it's common to both arms and drops out of the contrast. That's worth one line.

## 4. Smaller items

- **Top-ten table:** rank by standardized difference, not absolute rows. As written it's dominated by two mechanical metrics, 2024 and pilot-row occurrences, which equal the pilots' composition by construction.
- **Null categories and priorities are silently dropped,** while income gets a `<missing>` bucket. The one-hot groups don't sum to 1, and a pilot-driven shift in the null share would be invisible.
- **Completion checks are tautological.** They print `population_size` and assert uniqueness that holds by construction, and they consume the shared `rng` mid-loop. Use `SeedSequence.spawn` for separate streams so later batches don't depend on that block.
- **Hardcoded claim:** "neither duplication nor pilot redraw occurred" should be backed by `assert actual[0] == 310 and actual[3] == 10`.
- **Wording:** "row counts" for what are draw counts with multiplicity.
- **Blank tests:** `!= ""` for NameKeys versus `.strip()` for the nonblank indicators.
- **Memory limit:** the docstring says 128 MiB but the code sets `'128MB'`, which DuckDB reads as decimal.

I can sketch the revised version with the 2×2 arms, analytic bias checks, SD-unit bias, and coverage, and it should come out shorter than the current script.

__________

## 6 - Human  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 3:59:11 PM

how about now?

**File:**   
*ID:* `1464d66f-1b8f-5af6-9d83-620109c3293e`

__________

## 7 - Claude  
*Branch:* 1 | Main  
*Created:* 11/12/2026, 4:01:31 PM


<details>
<summary>*[Code Execution Claude thinking...]* Checking how the coverage measure would behave.</summary>


</details>

This is much better, and I read the prose as well as the code this time. I haven't run it, since I don't have the DuckDB file, so this is from reading.

Almost everything from my last round is addressed:
- The significance layer is gone, replaced by exact expectations, Δ in SD units and 95% ranges.
- The simulation now checks the formulas.
- RNG streams are spawned separately.
- The tautological completion block and the hardcoded "no duplicates" claim are removed.
- Nulls get a `<missing>` bucket with sum-to-one asserts.
- The blank tests agree, and the wording is now "draw occurrences".
- The memory-limit note is fixed, and the report states that it conditions on these pilots.

I also checked the exact formulas: the product-form inclusion probability, the hypergeometric versus binomial SDs, the pilot-key handling, and the distinct-awards expectation. They're right.

What remains, in priority order:

1. **The report still can't say which departure does what.** For indicators, the Measures paragraph's own formulas show that replacement doesn't enter the expected count at all (actual = H + 300·K/N, so Δ = H − 10·K/N). Every indicator Δ is the pilots. The intro leads with "unintentionally… with replacement," so I'd add one sentence saying this. For the distinct counts both departures matter, and by my arithmetic the distinct-awards Δ of about −0.8 is entirely replacement. A third arm (10 pilots plus 300 draws without replacement from the other N−10 rows) would separate them. Your `inclusion_probability` helper already handles it, using `population_size - len(pilots)` and `replacement=False` for the non-pilot keys.

2. **The exact SDs are never validated.** `fair_sd[2:]` and `actual_sd[2:]` overwrite the simulated values, and the assertion block only checks means. Yet `Δ / fair SD`, the report's headline column, rests on those formulas. I'd add an assert comparing simulated and exact SD, with a looser tolerance, or only for indicators with expected count ≥ 5, since rare indicators are skewed.

3. **The RMSE-ratio column is redundant for indicators.** The variance ratio is (300/310)·(N−1)/(N−310) ≈ 0.973 for every indicator, so the RMSE ratio is just √(0.973 + (Δ/SD)²). It adds no information beyond Δ/SD. If you want a column that translates bias into consequence, use closed-form coverage of a nominal 95% interval: Φ((1.96−z)/ρ) − Φ((−1.96−z)/ρ), with z = Δ/fair SD and ρ ≈ 0.986. That's computable with `erf`, though the normal approximation is poor for rare indicators.

4. **Top-ten ranking.** It ranks by absolute count, which favors prevalent categories. A rare category that a pilot happens to hit has a tiny count Δ but a large Δ/SD. The two rankings answer different questions. Either is fine as long as the title says which, and the title currently does.

5. **The lineage prose is hardcoded** and describes code outside this file (hash checks, header normalization, World Bank matching). I can't verify it from here, and nothing in the script would flag it going stale.

I'd fix 1 and 2 before sharing; the rest is polish.