## human written - ai never touches this
### prerequisites and setup
See prerequisites and setup in
`/tasks/tasks-20260519-review-231/SPEC.md`

### actual task
you will need to wire through
several surgical patches
united by a common goal.

The common goal is to
improve match rate
between subset 1 and 2 by addressing
several longstanding issues 
related to name matches
while also improving review data
to enable identifying future
improvement paths.

The surgical patches include:

- at xlsx match step,
  wire through new matching rules:
  - before tokenization,
    any punctuation sequence or
    any whitespace sequence in 
    first name and
    last name is
    replaced with a
    single space.
  - last name is therefore
    now also tokenized, and
    the rule is token sequence
    must be identical
    between source key and target
    (that is,
    same rule as for first name).
  - all tokens from 
    both sides are
    left and right stripped of
    space;
    empty string tokens are
    dropped.
  - if match failed then
    try this additional assertion:
    one side has
    two or more single-letter tokens while
    the other side has a
    single token that is equal to
    the single-letter tokens above joined
    either with a space or
    without a space;
    for example:
    ["john","rb"] on one side and
    ["john","r","b"] on the other side
    should be considered a match
    under this scenario; as well as
    ["john","r b"] on one side and
    ["john","r","b"] on the other side
    should be considered a match
    under this scenario;
    note that the
    exact order and count of
    tokens matters for the match,
    for example
    ["rb", "john"] on one side and
    ["john","r","b"] on the other side
    is NOT a match;
    ["john","rb"] on one side and
    ["john","r","b","james"] on the other side
    is NOT a match;
    this rule applies both for
    first and last name matching.
  - if match failed then
    try this additional assertion:
    one side has
    one or more single-letter tokens while
    the other side has 
    exactly the same number of
    (single or non-single letter) tokens
    that start with these letters
    while all the other tokens are
    matched exactly, and
    the sequence and order of tokens are
    matched exactly; for example,
    ["abdul","latif","m"] on one side and
    ["abdul","l","m"] on the other side
    should be considered a match
    under this rule;
    as counter-examples,
    ["l","abdul",] on one side and
    ["abdul","latif"] on the other side
    is NOT a match,
    ["abdul","latif","merem"] on one side and
    ["abdul","l"] on the other side
    is NOT a match.
- the new rule must be wired
  as a new knob under `config.repl.json`
  which is set to false
  but if set to true
  activates the new rule.
- a unit test must be created
  under `/tests/` that
  tests xlsx matching and
  all of its edge cases for
  both the v1 and v2 rule.
  the unit test must use
  pytest but be straightforward and
  it must use duckdb directly, and
  import the def from `/src/` directly,
  rather than a rewrite
  the naming logic in another way,
  so simply put the exact same
  mechanism must be used in the
  unit test as in the actual pipeline.
- for sciscinet matching step,
  a new knob must be wired through
  in `config.repl.json` in
  the same way as for xlsx above;
  the knob modifies the rule
  the following way:
  - tokens are
    left and right stripped of
    any whitespaces
- a unit test must be created
  for sciscinet matching
  along the same lines as xlsx.
- a unit test must be created
  for docx matching
  along the same lines as xlsx,
  though the rule itself
  remains unchanged.
- in step 10 logic that builds
  `10_build_cards_card_partition_review_df.csv`
  the logic must be changed to show
  ALL values of available innerdicts
  (all of DOCX, XLSX, SciSciNet,
  depending on the column)
  rather than only when one exists;
  they must be merged within cell through
  one new line if no multiline text in either,
  or with '-----'
  if any innerdict value contains multiline text.

## how ai understood the spec