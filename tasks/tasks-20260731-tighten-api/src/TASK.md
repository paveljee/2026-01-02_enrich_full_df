## human written - ai never touches this
### environment
```bash
([ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1)
TASK_DIR="$PWD/tasks/tasks-20260731-tighten-api"
TASK="$TASK_DIR/src/TASK.md"
WORK="$TASK_DIR/var/WORK.md"
```

## after each compaction
> [!IMPORTANT]
> Immediately after compaction, refresh TASK/WORK in full.

## always
> [!IMPORTANT]
> Remember to keep WORK current at all times - compaction can happen anytime.

### prerequisites and setup
AI must interpret how it understood this TASK
as prescribed in `$TASK_DIR/Makefile`,
whose `make validate` will be used to verify AI's work.

> [!IMPORTANT]
> When writing `$TASK_DIR/build/SPEC.ipynb`, AI should know:
> - The procedure is called atomic requirement-to-evidence mapping.
> - One Markdown cell represents one requirement unit:
>   - A requirement unit is the smallest contiguous set of TASK lines expressing one independently verifiable behavior.
>   - A unit may span multiple contiguous TASK lines.
> - An evidence (code) cell must prove only its preceding requirement unit:
>   - Exactly one evidence cell must immediately follow each Markdown cell.
>   - Its task_lines must exactly match that Markdown cell’s source lines.
>   - A code cell must not define paths, test IDs, setup, or assertions for other units.
>   - No shared “miscellaneous evidence” code cells or consecutive code cells.

```bash
sed -n '8,212p' "$TASK_DIR/legacy/SPEC.md"
```

### other issues that need addressing:
- review docx and txt renderers and identify where markdown is being produced - and enclose any  underscore containing items into backticks. so basically field names etc. otherwise in nicegui they are incorrectly rendered as markdown.
- in main nicegui table and in researcher card, somehow the line spacing is too large. in the attempt history table it's perfect.
- in main nicegui table the row clicked on doesn't get highlighted which is confusing.
- when nicegui table row is selected/unselected multiple times, this expands and collapses attempts table which is not intuitive. what should happen is that once it's selected, the attempt history should be expanded, and any future clicks will be idempotent.
when clicking on a different row, the selection will change.
therefore when for the first time a row has been selected, rows never get unselected
and therefore attempt history persists.
- in the search box when i remove the value, the search doesn't get reset. **already addressed in commit: `eeeaeacd8aef6d425c27935d2b00cd8777c196fa`. only remains to wire in spec.**
- a spec that uses the docx card building functionality to build a sample researcher's card from db. the card includes full featured output identical to that on a nicegui card. the spec saves it under `$TASK_DIR/data/sample.docx` for future review of rendering.
every case above must have a dedicated roundtrip test.

### revamped evidence matching
- it became known that submitter (agent runtime) tends to discard a large portion of evidence - without necessary changing the submitted variable values themselves. we need to address this by encapsulating current exact-matching behaviour as `match_rule_version.codex_match` in `config_ai_augment.json` (already added). v1 always remains authoritative for actual evidence acceptance but v2 is used to further explore the reasons for non-match and selecting what message to return to submitted and how to validate the resubmission.
- The detour configuration now has `match_rule_version.codex_match` with allowed versions 1 and 2.
- `match_rule_version.codex_match` is 1 by default if unspecified. Codex match rule v1 is the current case-sensitive exact contiguous excerpt match. Codex match rule v1 also requires the submitted URL to equal the indexed result URL. Codex match rule v1 remains the only rule capable of accepting evidence. When codex_match is 1, only v1 matching is performed.
- Codex match rule v2 is diagnostic only and must never accept evidence. When codex_match is 2, v1 matching is attempted first and v2 is attempted only after v1 fails.
- An excerpt satisfying v1 must always be classified as v1 even when it would also satisfy v2.
- The actual per-evidence outcome must be preserved as v1_exact, v2_near, unmatched, or withdrawn. These values are defined as top globals in `src/detours/detour_ai_augment/src/backend/api.py` and any labels intended for humans go into `src/detours/detour_ai_augment/src/backend/helpers/locale.py`.
- Codex v2 should reuse exactly the normalization/tokenization primitive currently used by XLSX v2. Yes, it's a DuckDB-based processing - we use it for codex_parse also, and we .leverage existing `codex_*` tables and views. Only the generic XLSX v2 tokenization primitive may be reused; XLSX initial expansion, compact-initial matching, source/target asymmetry, name-key generation, and candidate priority are irrelevant to Codex evidence. The XLSX v2 tokenization primitive must be extracted into a domain-neutral shared helper without changing its generated SQL or main-pipeline behavior. xlsx_v2_tokens_sql must remain available as a compatibility wrapper around the extracted helper. Normalized values are persisted in a new view at `persist_rollout_index` for easier use downstream. Codex v2 must compare normalized token sequences rather than normalized complete strings. The complete normalized submitted-excerpt token sequence must occur contiguously and in order within one normalized citation section. Otherwise currect exact match logic can be reused. Codex v2 must still only use citation sections produced by a fully valid web-tool chain. Codex v2 must still require the submitted URL to equal the candidate citation result URL. V2 matching must be used only to classify and coach a rejected item; it must never modify the submitted excerpt automatically.
- An empty or punctuation-only submitted excerpt must not satisfy v2. 
- Every submitted evidence item must be evaluated independently before the API constructs its submission response. Evidence validation must not stop at the first failed item
- Compromised `appendwatch` rollout provenance still fails the rollout-index stage before per-evidence assessment begins.
- A field is provisionally accepted only when every submitted excerpt for that field satisfies v1.
- A v2-near excerpt is not accepted and therefore prevents provisional acceptance of its field.
- An unmatched excerpt is not accepted and therefore prevents provisional acceptance of its field.
- The complete push remains rejected until every required evidence-bearing field is provisionally accepted. The submitter must therefore resubmit the complete payload rather than submitting only failed fields or failed excerpts.
- The optional comments field remains independent of evidence validation and requires no web excerpts.
- The first Pydantic-valid but evidence-invalid submission for a sanctioned run must establish an immutable retry baseline. Plain `src.detours.detour_ai_augment.src.backend.helpers.data_models.submission.Submission` is used to validate the first submission. The retry baseline must be keyed by sanctioned run_id rather than session_id or rollout filename. The retry baseline must also bind sourcekey and session_id so mismatched retry state fails closed.
- `src.detours.detour_ai_augment.src.backend.helpers.data_models.pydantic_to_paste.StandardizedSubmission` is used to validate every retry submission. The message to the resubmitter must include a note that standardized values are now required and the Pydantic schema is provided (e.g., `src.detours.detour_ai_augment.src.backend.helpers.locale.Locale.EVIDENCE_RETRY_STANDARDIZED_VALUES`). The API should not let the resubmitter know anything about the plain `Submission` or even its existence; `StandardizedSubmission` is the only schema the resubmitter sees.
- OpenAPI `/push` example is shown accordingly to the schema used.
- All standardized values are saved into DuckDB along with plain ones; a separate `ktp.ai_augment_*_standardized` field is provisioned in the db schema for each variable and it contains JSON-serialized `standardized_value`.
- All standardized values are shown in the final produced card; every standardized field immediately follows its plain version; if the standardized value is None/NA/NR, use routine logic for card display that hides `KTP_TABLE_1_EMPTY_VALUE_PLACEHOLDERS` (extend this var for this detour - no touching the main pipeline); no footnotes are attached or shown for standardized values as all footnotes will already have been shown at the plain value.
- The retry baseline must be created atomically, persist across API restarts, and never be replaced by a later retry.
- A Pydantic-invalid submission must not establish a retry baseline.
- Different pull/push runs in the same cumulative Codex rollout must have independent retry baselines. 
- The retry baseline must preserve every submitted evidence item and its v1, v2, or unmatched outcome.
- A v1-exact baseline evidence item must be immutable on all retries. A v1-exact baseline evidence item must retain its exact excerpt and exact URL.
- A fully provisionally accepted field must retain its exact field value and complete evidence list on retries. Provisionally accepted fields are therefore carried forward unchanged in the complete payload and are not invitations for further editing.
- Within a rejected field, every v1-exact evidence item must still be retained unchanged.
- A v2-near response should praise the overall progress only when exhaustive assessment proves that the submission is largely v1-valid (without saying internal words like v1 or v2 of course).
- A v2-near response should say that the identified evidence item appears close to the recorded result and probably needs a minor correction involving case, accents, punctuation, whitespace, or line breaks.
- A v2-near response must instruct the submitter to preserve all verified values and evidence unchanged.
- An unmatched response should say that the identified evidence item does not appear to match its cited web result.
- An unmatched response must instruct the submitter to verify both the excerpt and URL against the original web-tool output.
- The API response must identify each failed evidence item by field and array index, e.g.:
    
    > 21 of 22 evidence items were verified. Preserve all verified values and evidence unchanged. Review the following flagged excerpts:
    >
    > - ktp.ai_augment_social_capital.web_search_excerpts[1]; its wording appears close to the recorded result but may differ in case, punctuation, whitespace, or line breaks.
    > - ktp.ai_augment_social_capital.web_search_excerpts[2]; does not appear to match its cited web result. Preserve all verified values and evidence unchanged, then verify this excerpt and URL against the original web-tool output.
    > - ..etc, one line per rejected excerpt
    >
    > Compare the above evidence items character-for-character with the original web-tool output and resubmit the complete payload after correcting only the flagged items.
- The API response must not return the server’s candidate text or a corrected excerpt. The API response must not disclose call_id, ref_id, match positions, SQL, or other internal validation details.
- Exact candidate text and detailed diffs should remain available in private server logs or a human-only Control Centre view.
- A v2-near baseline item must preserve its original URL on retry.
- A v2-near baseline item must preserve its original normalized v2 token sequence on retry. The resubmitted v2-near excerpt must normalize to exactly the same token sequence as the original submitted excerpt. Of course, a v2-near retry whose normalized tokens remain equal must still satisfy v1 before it can be accepted.
- A v2-near retry with a different normalized token sequence must be rejected with a message that only a minor textual correction was permitted.
- If a v2-near retry retains the normalized tokens but still fails v1, it must remain rejected and receive the minor-correction instruction again.
- The v2 retry restriction must prevent shortening Geslacht followed by a line break and Man to only Man (feel free to copy real-world examples from `tmp/20260813T141344_678596Z_8ef1f6372b4a48d9a3b1279736356363` and `tmp/20260813T141450_027429Z_044215aac8c44200882531b10a2acfa6`).
- An initially unmatched evidence item may be replaced with any excerpt and any URL because no credible source identity or wording was established.
- An initially unmatched evidence item must be classified afresh on every retry.
- An unmatched replacement that satisfies v1 becomes provisionally accepted and immutable.
- An unmatched replacement that satisfies only v2 becomes v2-near and establishes a normalized-token and URL lock for subsequent retries.
- An unmatched replacement that still satisfies neither rule remains freely replaceable.
- Evidence counts must not decrease by silently deleting v1-exact or v2-near baseline items. An unmatched evidence item may be removed only through an explicit audited withdrawal mechanism. The withdrawal mechanism must be represented by a structured Pydantic model and a withdrawal should contain a machine-readable unsupported-evidence reason and an explicit attestation, e.g.: `{"action": "withdraw_unverified_evidence", "reason": "not_present_in_web_results", "attested": true}`. The submitter identity for a withdrawal must come from the sanctioned run, session, and attempt metadata.
- A withdrawal must never count as validated evidence.
- A withdrawal must remain visible in the immutable attempt audit.
- Automatic withdrawal must be available only for evidence that satisfies neither v1 nor v2.
- A v2-near item must never be withdrawable because the backend already has evidence that its wording is present after conservative normalization.
- Withdrawing an unmatched item must release only that unaccepted item’s retry obligation. Withdrawing an unmatched item must not permit deletion or modification of any v1-exact or v2-near item.
- The field value associated with a withdrawn item must be resubmitted so the unsupported claim can be corrected.
- A field containing a withdrawal must still retain at least one v1-exact evidence item before the field can be accepted.
- The backend must continue to use rigorous v1 matching after every v2 diagnostic or withdrawal operation. V2 classification, retry guidance, and withdrawal must not weaken the final exact-match acceptance boundary.
- Detailed per-item outcomes, submitted excerpts, submitted URLs, and candidate diagnostics must be logged privately.
- Public retry responses must expose only the failed item locations, aggregate counts, permitted correction category, and remediation instructions.
- The implementation must preserve current deterministic evidence candidate ordering and sampling behavior.
- The implementation must preserve source database read-only behavior.
- Rejected and provisionally accepted retry state must not materialize accepted output rows or researcher cards.
- Only a fully accepted push may append Codex output, materialize a researcher card, acknowledge acceptance, and consume the sanction.
- Unit tests must follow the existing XLSX and SSN name-matching style by using parametrized cases and explicit expected matched-rule sets.
- Tests must prove that exact text is classified as v1 when codex_match is 2.
- Tests must prove that case-only differences are classified as v2 and remain rejected.
- Tests must prove that accent-only differences are classified as v2 and remain rejected if XLSX normalization is reused exactly.
- Tests must prove that punctuation-only differences are classified as v2 and remain rejected.
- Tests must prove that whitespace and line-break differences - including with several such characters in a row - are classified as v2 and remain rejected.
- Tests must prove that reordered tokens fail v2.
- Tests must prove that missing or added internal tokens fail v2.
- Tests must prove that tokens split across citation sections cannot satisfy v2.
- Tests must prove that an otherwise matching token sequence under a different URL cannot satisfy v2.
- Tests must prove that punctuation-only and empty excerpts cannot satisfy v2.
- Tests must prove that enabling codex_match version 2 never causes v2 evidence to be accepted.
- Tests must prove that all evidence items are assessed even when an earlier item fails.
- Tests must prove that a field is accepted only when all its evidence items satisfy v1.
- Tests must prove that a complete submission is rejected when any field remains unaccepted.
- Tests must prove that v1-exact fields and evidence cannot be changed or removed on retry.
- Tests must prove that a v2-near retry may change only formatting represented away by v2 normalization.
- Tests must prove that a v2-near retry with changed normalized tokens is rejected.
- Tests must prove that a v2-near retry is accepted only after its corrected raw excerpt satisfies v1.
- Tests must prove that an unmatched item may be replaced freely and is reclassified after replacement.
- Tests must prove that an unmatched item may be explicitly withdrawn without removing accepted evidence.
- Tests must prove that a v2-near item cannot use submitter-initiated withdrawal.
- Tests must prove that retry baselines survive API restart.
- Tests must prove that concurrent first rejected submissions cannot replace the immutable baseline.
- Tests must prove that retry state does not cross run_id boundaries within the same Codex session and rollout.
- A historical Haanen regression fixture (from `tmp/20260813T141344_678596Z_8ef1f6372b4a48d9a3b1279736356363` and `tmp/20260813T141450_027429Z_044215aac8c44200882531b10a2acfa6` paths) must demonstrate that exhaustive validation classifies 21 original evidence items as v1 and one item as v2-near.
- The historical Haanen regression must demonstrate that the ideal retry preserves all 21 v1 items unchanged and corrects only the one newline-mismatched item.
- The historical Haanen regression must demonstrate that the retry cannot reduce 22 evidence items to 9.
- The historical Haanen regression must demonstrate that the retry cannot shorten already-valid excerpts such as Geslacht followed by a line break and Man to Man.
- All existing tests, including XLSX name matching, must remain green after extracting the shared tokenization primitive.
- A focused equivalence test must prove that the extracted shared tokenization produces exactly the same XLSX v2 tokens as the pre-extraction implementation for all the normalizations applied.
- The main pipeline remains completely independent of any `src/detours/detour_ai_augment` code.
