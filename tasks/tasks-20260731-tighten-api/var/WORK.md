# README Workflow patch

## Scope

Patch only the agreed durable workflow in
`src/detours/detour_ai_augment/README.md`. Do not condense or reorganize
provisioning, startup, queue, or other unrelated prose.

## Status

The user's currently staged README text through line 126 is the wording
baseline and was not changed. Lines 127 onward were reviewed and revised in the
working tree for user review. The revision restores still-valid original
clauses, adds only the agreed commit/projection/outcome semantics, and updates
the directly contradictory Implementation constraints. No source or test code
was changed.

## Agreed contract

1. Every public pull and push is assigned a Backend UUIDv7, validated as
   `HttpRequestLogRecord(schema_version=2)`, and appended/fsynced through one
   shared writer before its response is returned.
2. After an admitted push is logged, the Backend copies the session rollout to
   CAS and reads the exact appendwatch report bytes.
3. The Backend prepares but does not send `POST http://invalid/commit`.
4. The commit request has an empty query and null response. Its body links the
   current pull UUID and push UUID to rollout SHA/size/line count and base64
   appendwatch bytes. Its Structured Field headers carry rollout SourceKey and
   NameKey.
5. Appending/fsyncing the commit request completes commit. No domain validation
   precedes it.
6. Validation is invoked after commit. It synchronizes DuckDB from JSONL,
   resolves the pull/push/CAS/report inputs, verifies appendwatch, selects the
   initial or follow-up Submission model from the referenced pull, and validates
   the referenced push.
7. Validation controls the next public pull: expected rejection returns
   resubmission instructions; internal/integrity failure returns opaque `500`;
   success returns terminal `410 Gone` NDJSON containing the accepted innerdict
   and optional ground truth.
8. Every such pull is itself persisted before response. Its terminal body can
   rebuild the final per-session DuckDB innerdict and provenance linkage.

## Files

- Authorized edit: `src/detours/detour_ai_augment/README.md`
- Tracking report: this file
- No source or test changes authorized in this pass.
