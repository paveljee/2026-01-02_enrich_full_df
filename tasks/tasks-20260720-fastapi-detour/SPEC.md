## human written - ai never touches this
### prerequisites and setup
See prerequisites and setup in
`tasks/tasks-20260519-review-231/SPEC.md`

Use `./WORK.md` as
your own workbook for
recording actions you have in mind and
recording in progress and completed, or
any other notes you feel you need.
Write as if for a
busy tech lead and
also to be helpful for the executor, so
lean concise text that 
contains all relevant info inplace but is
focused and very well organized.

### actual task
build a new detour.
review existing ones to see how they work.
the most important bit is that
they are inspired by some components of the main pipeline
yet are completely standalone in operation.

the detour will spin up a fastapi server.
the server is intended for api-only use,
by an executor (AI agent) who will be filling in missing data.

the executor's intended workflow
(that is, equipped with the detour's server endpoints):

**first, the executor will be receiving payloads
for which we do not have any missing data -
that is, subset 1 namekeys. this is for evals.
once the executor is happy with results, it requests
supervisor's review before the executor is
allowed to proceed with any records with missing data.
and so, the eval part goes as follows:**

- request a new payload.
(the payload contains all non-missing fields
for the record, and the list of missing fields;
the record being a single namekey).
- conduct web searches to
fill in all missing data.
- submit work to a structured endpoint
(endpoint is very principled and
will not accept any badly formatted work;
it accepts only a valid json payload).
- endpoint returns ground truth results
for executor's review.
the executor must submit
(on a special endpoint)
confirmation that review of ground truth results is
complete, executor's own assessment of pass/fail, and
takeaways from the review.
the executor must also update their workbook, 
which is limited in size, 
by recording only the most important learnings there.
all changes are made as git commits.
the commit hash is always submitted in the payload.
- the endpoint verifies the submitted json and
the hash, as well the endpoint has direct access
to an automated JSONL rollout of the agent's work
and relevant events are auto verified against it.
- once endpoint is happy, it prompts the executor
whether they would like a new payload or
they would like to submit whole work for supervisor's review.
if not happy, it returns specific feedback to address.

payload production is randomized, seed is set
within the fastapi code as top level env var.

once executor says submit all work for supervisor review,
fastapi collates all tasks into a single report
which must be reviewed by supervisor (i.e., human).
supervisor review is not available via fastapi,
rather it must be supplied separately to the server env.
until it's supplied, server does not return new payloads.
once it's supplied, the server start returning payloads again
but this time with genuinely missing data.
in this iteration, the executor is not obviously offered
ground truth which is nonexistent, but rather is
simply shown its own submitted work and prompted to confirm.
once confirmed and endpoint is happy with validation,
new payload is offered, and this continues until
all missing data are filled.

executor should also be explicitly offered an
endpoint for modifying a previous submission.
the endpoint will operate identically to
namekey submission confirmation operation
for missing-data namekeys:
endpoint returns inputted data and prompts to confirm.
once all missing-data-payloads are processed,
the executor gets a final opportunity to review and
change any previously submitted work before
the executor confirms that all is sent to supervisor.

so, now that the whole workflow is described,
the goal is build a detour that spins up this server.
namekeys for review (i.e., with missing data)
should be partition 4 of subset 2.
records for evals are subset 1.
the amount of information show to exectutor
is same as in the final cards.

submitted results of work are **not** stored in 
the main database which is read.
note that it's  always read as read-only.
instead, a separate db is created for the detour.

## how ai understood the spec
