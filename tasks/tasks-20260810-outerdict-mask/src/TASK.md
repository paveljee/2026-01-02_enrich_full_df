## human written - ai never touches this
### prerequisites and setup
```bash
([ "$PWD" = "/Volumes/home/aicode/2026-01-02_enrich_full_df" ] || exit 1)
TASK_DIR="tasks/tasks-20260810-outerdict-mask"
```

See prerequisites and setup in
`tasks/tasks-20260519-review-231/SPEC.md`

Use `$TASK_DIR/var/WORK.md` as
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

If `apply_patch` does not work,
use the `env` workaround.

AI only uses git readonly.

### actual task
look, readonly, at:
`./tmp/manual_outerdict_mask.json`.
we need to properly wire this into main pipeline.

the intended behaviour:

- that's a mask so if something is missing there, we don't pick up cancellations; we only pick up signal.
  that is to say, on any innerdict construction (xlsx, docx, ssn, codex etc) we first check the mask registered resource, and look up ktp.namekey:
  if the mask file contains something for *this* pipeline step, use what's supplied from the mask file wholesale, that is, replace anything matched during the step.
  for example, say xlsx step found 11 matches across rows but mask file only specifies one - take up that one from mask file and discard the rest.
  make sure this is properly and in detail recorded in session log(...).
  accordingly, if the step found something for the namekey but in the mask file there is nothing relevant for this step, use what's found at the step.
  for example, in the above example if the mask file only specified one for xlsx but was silent on docx and ssn, happily use docx and ssn findings from step.
- i said "relevant for the step", now how do you figure this? here is how:
  note that the ktp.fragment structure shown in the mask file is now authoritative and must be wired in also;
  hence the ktp.fragment_type col was removed altogether from vars.py because it's no longer used or permitted - value of ktp.fragment must always be serialized json such as `{"type":"xlsx_row","xlsx_row":99}`.
  now that this is clear, it's also clear how relevance for the step is handled:
  we request that every innerdict must contain, as root level keyval pairs, at least a sourcekey, that is:
  a valid ktp.filename
  (that is, the filename must resolve to a registered resource or a set of registered resources) AND
  a valid ktp.fragment
  (that is, is resolves successfully into a Fragment, and
  the fragment type is consistent with this registered resource);
  everything else within an innerdict is optional.
  this rule btw applies to _all_ innerdicts across the repo,
  including pipeline produced ones, not only those that come from the mask file.
  and so for each innerdict all this info is guaranteed and from it we can unmistakably figure out the respective relevant step.
- and then there is this new feature: a new mechanism is now introduced in the code base that can attempt to resolve any given sourcekey to associated data from step.
  we implement this mechanism as a first class thing in the code base.
  but then in practice, this mechanism will only be used for the mask file - if in the mask file the source key is specified but _nothing else is_ (that is, the entire innerdict entry is presented by a valid sourcekey) then attempt to resolve this against step, and note that this will be the same step where we're at - _the_ step that we identified as relevant for this particular sourcekey, and so we already have all the data we need to resolve.
- note that any resolved data must still be within constraints of the step.
  for example, if in principle 10 matching ssn authorids exist but after applying the hit rule only one remains, only one should be used for resolution.
  never resolve to anything beyone the pipeline's scope (e.g., as defined by the --config and overall the pipeline code and db schema).
- simply put, how we have it now is the baseline. and after this implementation, some of the innerdicts will be dropped - i.e., that is in case if
  (1) the corresponding namekey is non-empty in the mask file AND
  (2) the sourcekeys (to be dropped) are _not present_ in the mask file.
  and then those sourcekeys that _are_ present in the mask file for this namekey, these will be expanded to the full innerdict (which will be identical to the corresponding innerdict in the baseline version) and so the overall effect will be just what i said - not-mentioned sourcekeys will be cancelled out.
  just to be sure, let me reiterate a simple truth - a sourcekey is basically a _unique id of an innerdict,_ and that's how it should be implemented throughout the repo actually. that's a design requirement.
  the pipeline assumes that there may _not_ be two innerdicts sharing the same: namekey, filename, and fragment (type and value). that's a provenance story. it's jointly guaranteed by how the pipeline code is written and also how the filename/fragment type is carefully designed for each of the diverse registered resources that get registered by the pipeline.
  whereas, the _namekey_ is obviously the unique id/proxy for a researcher individual, that is, the key in the outerdict - obviously as defined under `src/helpers/data_models/outerdict.py`.
  so this was just to recap and be sure we're on the same page here.
- also after this implementation, some new innerdicts will obviously appear in the pipeline db, and this will be in case if
  (1) the corresponding namekey is non-empty in the mask file AND
  (2) the sourcekeys present in the mask file actually _don't fall under any of the steps._
  because as clarified above, if they _were_ under the step's scope and yet _weren't a subset_ of the actual matched entities, this would not work.  because as mentioned above, "resolved data must still be within constraints of the step".
  so the only really possible way is the source key doesn't really resolve to any of the valid innerdicts. consider this simulated example: `"{\"ktp.first_name\": \"Jane\", \"ktp.last_name\": \"Doe\"}": [{"ktp.filename": "some_registered_filename", "ktp.fragment": {"type":"line_number","line_number":42}}]}` where `some_registered_filename` _does_ resolve to a valid registered resource
  (i.e., a non-duplicate registered resource is found with this filename - any duplicate filenames among registered resources **must** raise an error **at resource registration** at pipeline init and therefore pipeline fails to init)
  yet this registered resource is not used in any of the steps - at least not in any innerdict-producing way.
  for example consider `OGHIST_2025_07_01.xlsx` which is a registered resource _at baseline already_ yet it's not used to generate any innerdicts.
  and so if such an entry was found in the mask file, this would be taken up verbatim from the mask file and just appended to the namekey as an innerdict; use the corresponding separate table MISC_INNERDICT_TABLE and view MISC_OUTPUT_VIEW to handle those that are already provided in schema.py;
  do all handling of misc within step 4! that may look counterintuitive, but really I just don't want to introduce new steps and so let's use the docx step for this that already is kind of incorporating manual info, and so this fits well here. don't rename step or anything, just consider it _the_ place for this.
- **note therefore that no sourcekey resolution is done or attempted in cases when a non-step-innerdict-producing registered resource is taken up from the mask file. only the verbatim value is taken from the mask file in case of this.**
  be sure though to _not hardcode_ the list of {docx,xlsx,ssn} as the eligible steps; make sure you implement this in a generalizable enough way so that if, say, we were in the future to introduce new innerdict-producing behaviours into the main pipeline, these would be taken up seamlessly by the sourcekey resolution logic.
- all of this above must be meticolously documented in the session log(...). the reviewer of logs must be able to see all events that happened while the pipeline reasons through the mask file, at every exact point where the mask file is consulted.
- if sourcekey resolution was warranted (i.e., step-relevant), attempted, and failed - fail loudly and exit the pipeline. we still won't allow the use of non-registered resources and/or use of fragment type unsupported by the registered resource.
- if the mask file contains _any_ invalid namekeys
  (that is, any namekeys **invalid within the given pipeline scope!**),
  then fail loudly. we won't allow introduction of arbitrary namekeys from the mask file - it's not intended for this.
  for example, even if the namekey _would_ be constructible at step 6 from some of the data but _didn't actually end up in `OUTERDICT_STUB_TABLE`_ then any such namekey is not acceptable from the mask file.
  for speed we run this quick check at step 6 immediately after building `OUTERDICT_STUB_TABLE` and fail the mask file loudly at the earliest opportunity therefore.
- just to be sure, if the mask file contains an entry like this, `"\"ktp.first_name\": \"Jane\", \"ktp.last_name\": \"Doe\"}": []`, that means no action is to be taken and Jane Doe here will simply be processed normally by the pipeline.
- to be sure, if the entire contents of the mask file is this, for example, `{"\"ktp.first_name\": \"Jane\", \"ktp.last_name\": \"Doe\"}": []}`, then still the result is the same - no action is to be taken and it doesn't matter how many namekeys there are in the mask file, so the number of namekeys in the mask file is not regulated.

**importantly:**

> [!ATTENTION]
> **and I cannot stress that enough!**

**all** implementation must be done _surgically_.
the code is only added when necessary and
existing code is not touched unless truly necessary
(e.g., no purposelessly stripping comments etc.).
