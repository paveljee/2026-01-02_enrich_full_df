## human written - ai never touches this
### prerequisites and setup
`/tasks/tasks-20260519-review-231/SPEC.md`

### new issue
i am now reviewing partition 1  and
finding that a lot of namekeys are actually
not eligible for subset 1 for
simply this pattern:

{"ktp.source_key_first_name_norm_tok":["jeffrey","s."],"ktp.source_key_last_name_norm":"weber","ktp.first_name_norm_tok":["jeffrey","s"],"ktp.last_name_norm":"weber"}
{"ktp.source_key_first_name_norm_tok":["david","n"],"ktp.source_key_last_name_norm":"spergel","ktp.first_name_norm_tok":["david","n."],"ktp.last_name_norm":"spergel"}
{"ktp.source_key_first_name_norm_tok":["john","rb"],"ktp.source_key_last_name_norm":"perry","ktp.first_name_norm_tok":["john","r.","b."],"ktp.last_name_norm":"perry"}
{"ktp.source_key_first_name_norm_tok":["randy"],"ktp.source_key_last_name_norm":"gascoyne","ktp.first_name_norm_tok":["randy",""],"ktp.last_name_norm":"gascoyne"}
etc.

so basically just dot missing from either side,
including within initials (like with rb <-> r.b.), or
sometimes just a trailing whitespace.

pls review the existing pertinent code base and
give me your reflections/suggestions
where you think this could best be
surgically patched?

note that for back compatibility,
we would need to ensure that the
new implementation makes it possible to
distinguish between these
"new additions" and
older treatment _at_ step 10;
so the idea is that
upstream logic does change but
downstream at step 10
the data we receive allow us to
reimplement subsets 1/2 a bit to
preserve them exactly but
under the new data model;
this way subsets 5 and 6 will
therefore be introduced:
subset/mode 5 will be
new additionts to subset 1
while subset 6 will be
remainder of subset 2
under the new logic.

## how ai understood the spec

### implementation target

The approved prior task remains the contract for legacy subset behavior.
This task adds a second xlsx exactness interpretation for first-name
punctuation/initial formatting, then exposes that interpretation through
new step-10 card subset modes.

Existing modes 0-4 must keep their current behavior. In particular,
modes 1 and 2 must preserve the current subset-1/subset-2 split exactly,
even after the xlsx matching data model is enriched.

New modes are:

| mode | meaning |
|---:|---|
| 5 | namekeys that fail legacy subset 1 but pass subset 1 under the relaxed xlsx exactness rule |
| 6 | all namekeys that still fail subset 1 under the relaxed xlsx exactness rule |

The observed issue is not that step 7 fails to produce xlsx candidate
rows. `src/steps/step_07_match_xlsx.py` already emits candidate rows for
these cases because it joins on normalized last name and the first
token of the first name. The rejection happens in step 10:
`_is_exact_xlsx_match_payload()` in `src/steps/step_10_build_cards.py`
compares stripped token strings literally, so `s.` vs `s`, `n` vs `n.`,
`rb` vs `r. b.`, and trailing empty tokens are treated as non-exact.

### xlsx exactness semantics

Keep two xlsx exactness concepts side by side.

Legacy exactness is the current behavior. Preserve the existing
`ktp.xlsx_match` JSON payload and the current exactness convention:
missing/blank payloads are not themselves non-exact, invalid JSON is
non-exact, and `xlsx_ok` still requires both `xlsx_any` and all present
payloads exact.

Relaxed exactness uses the same `ktp.xlsx_match` payload keys but compares
first-name tokens with punctuation/initial normalization:

- parse the existing `ktp.xlsx_match` JSON payload;
- keep the existing last-name requirement as trimmed normalized equality
  between `ktp.source_key_last_name_norm` and `ktp.last_name_norm`;
- for first-name tokens only, strip whitespace, lowercase, remove
  punctuation/non-alphanumeric separators, and drop empty tokens;
- after that cleanup, `s.` equals `s`, `n` equals `n.`, and a trailing
  blank token has no effect;
- compare the cleaned tokens with the same order-insensitive/deduplicated
  set semantics used by the current legacy helper;
- for non-first tokens that are alphabetic compact initials of length 2
  or 3, expand a token such as `rb` into `r`, `b` for comparison, so
  `john rb` equals `john r. b.`;
- do not expand the first token or full given names, so `randy` is not
  treated as `r a n d y`;
- do not treat a missing initial on one side as exact, so `piotr p.` vs
  `piotr` remains non-exact;
- keep the namekey-level rule strict: a namekey has relaxed `xlsx_ok`
  only when at least one xlsx payload is present and all present xlsx
  payloads pass relaxed exactness. One good candidate row is not enough
  if another candidate row remains non-exact.

This relaxed rule is intentionally narrow. It addresses punctuation,
empty-token, and compact-initial formatting only; it should not broaden
matching to nickname, spelling, missing-initial, or first-name/last-name
structural differences.

### data model and code shape

Add a small shared helper rather than duplicating xlsx payload parsing in
step 7 and step 10. A good location is `src/helpers/xlsx_match.py`, with
functions equivalent to:

- `has_present_xlsx_match_payload(value)`;
- `is_legacy_exact_xlsx_match_payload(value)`;
- `is_relaxed_exact_xlsx_match_payload(value)`.

Keep the existing step-10 helper names as wrappers if tests or detours
currently import them.

Centralize any new column labels in `src/helpers/vars.py`. Recommended
names:

- `KTP_XLSX_MATCH_EXACT_LEGACY_COL = "ktp.xlsx_match_exact_legacy"`
- `KTP_XLSX_MATCH_EXACT_RELAXED_COL = "ktp.xlsx_match_exact_relaxed"`
- `KTP_PARTITION_FLAG_XLSX_RELAXED_NON_EXACT_ANY_COL = "ktp.partition_flag_xlsx_relaxed_non_exact_any"`

Step 7 should preserve `ktp.xlsx_match` unchanged and enrich xlsx
innerdict rows with the two exactness booleans above. The selection path
in step 10 must not depend on `xlsx_output`; it should read these fields
from the outerdict innerdicts when present and fall back to computing the
same booleans from `ktp.xlsx_match` for older DBs/current tests.

Do not replace `ktp.partition_flag_xlsx_non_exact_any`. That existing
flag should continue to mean legacy non-exactness for backward
compatibility and for modes 1/2. Add the relaxed non-exact flag beside it
so mode 6 can be audited without losing the legacy signal.

### step-10 selection logic

Model the two subset-1 predicates explicitly:

```text
xlsx_legacy_ok = xlsx_any and not xlsx_legacy_non_exact_any
xlsx_relaxed_ok = xlsx_any and not xlsx_relaxed_non_exact_any
docx_ok = docx_any and docx_table_1_required_all
sciscinet_ok = sciscinet_count == 1

subset1_legacy_ok = xlsx_legacy_ok and docx_ok and sciscinet_ok
subset1_relaxed_ok = xlsx_relaxed_ok and docx_ok and sciscinet_ok
```

Then extend `_mode_matches()` as follows:

| mode | predicate |
|---:|---|
| 0 | all namekeys, unchanged |
| 1 | `subset1_legacy_ok`, unchanged |
| 2 | `not subset1_legacy_ok`, unchanged |
| 3 | existing legacy xlsx+sciscinet predicate, unchanged |
| 4 | existing legacy complement of mode 3, unchanged |
| 5 | `subset1_relaxed_ok and not subset1_legacy_ok` |
| 6 | `not subset1_relaxed_ok` |

Modes 5 and 6 should be added to `CARD_BUILD_SUBSET_DESCRIPTIONS` in
`src/helpers/vars.py`. Existing descriptions for modes 1-4 should remain
semantically unchanged.

### partition artifacts

Partition artifacts should be emitted for modes 1, 2, 5, and 6. Modes 0,
3, and 4 should keep normal card generation behavior and skip partition
artifact creation.

For modes 1 and 2, partition assignment must use legacy xlsx exactness,
so the prior approved behavior and current mode-2 `31/100/100` queue are
preserved.

For modes 5 and 6, partition assignment must use relaxed xlsx exactness:

```text
active_xlsx_ok = xlsx_relaxed_ok
active_subset1_ok = subset1_relaxed_ok

if active_subset1_ok:
    ktp.partition = NO_RESOLUTION_PARTITION
elif not active_xlsx_ok and docx_ok and sciscinet_ok:
    ktp.partition = XLSX_PARTITION
elif docx_ok and not sciscinet_ok:
    ktp.partition = SCISCINET_PARTITION
else:
    ktp.partition = DOCX_PARTITION
```

For mode 5, selected rows are relaxed subset-1 additions and should get
the no-resolution sentinel. They remain distinguishable by
`card_subset_mode = 5` and by the legacy xlsx non-exact flag still being
visible.

For mode 6, selected rows are the relaxed subset-2 remainder and should
use the same review queue shape from the prior task, but with relaxed
xlsx exactness as the active xlsx condition. The review view should show
both the legacy and relaxed xlsx non-exact flags so humans can see which
rows changed status because of this task.

### current DB impact check

Using the current `data/scisci_process.duckdb` read-only and the relaxed
rule above, the expected current counts are:

| item | count |
|---|---:|
| legacy subset 1 / mode 1 | 76 |
| legacy subset 2 / mode 2 | 231 |
| relaxed subset 1 total | 96 |
| mode 5: new relaxed subset-1 additions | 20 |
| mode 6: relaxed subset-2 remainder | 211 |

Mode-6 queue under relaxed exactness should be:

| ktp.partition meaning | namekeys |
|---|---:|
| xlsx tier | 11 |
| sciscinet tier | 100 |
| docx tier | 100 |
| total mode 6 | 211 |

For audit context, the 20 mode-5 rows are all drawn from the legacy xlsx
tier. The other relaxed xlsx fixes inside legacy sciscinet/docx tiers do
not become subset 1 because those namekeys still fail sciscinet and/or
docx conditions.

### tests to add/update

Add focused tests for the xlsx helper:

- legacy exactness remains false but relaxed exactness is true for
  `jeffrey s.` vs `jeffrey s`, `david n` vs `david n.`, and
  `john rb` vs `john r. b.`;
- relaxed exactness is true for a trailing empty first-name token;
- relaxed exactness remains false for missing initials such as
  `piotr p.` vs `piotr` and for extra initials such as `randy` vs
  `randy d.`;
- invalid JSON remains non-exact;
- blank/missing payload exactness follows the existing convention, while
  `xlsx_any` still controls whether xlsx is present.

Update step-10 tests so modes 1/2 remain unchanged, modes 5/6 select the
new predicates, and partition artifacts are created for modes 1, 2, 5,
and 6 only. Add one test where a mode-5 row has legacy xlsx non-exactness
but relaxed subset-1 success, and one mode-6 row remains in the xlsx tier
because at least one xlsx payload still fails relaxed exactness.
