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

If `apply_patch` does not work,
use the `env` workaround.

AI only uses git readonly.

### actual task
go to and review contents of `src/detours/detour_ai_augment/`.
There we have everything almost ready for production.
Some things need to be wired in:

- deploy/provision scripts must provision appendwatch from a root-only dir that cannot even be traversed into by a non-sudo user. we can use the already mounted macos dir to host it which is properly protected from nonsudoers, and this also gives easy access to these files for the host backend. we use systemd for persistence, and we also must ensure that the non-sudoer must have absolutely zero ways to view the python source code.
- api validator currently does not make use of appendwatch. how it should work: api must not accept pushes until human operator manually sets the path to the codex rollout associated with the chat. how it should be seen on agent runtime's end: there should be some generic error that says that api not properly configured and human operator must be contacted. then runtime will flag this to the user. the runtime does not need to know what the error is. but backend api logs should be informative, human operator goes to check them and sees that this var is not set in .env file for api, so operator checks what the rollout path is and sets it there, restarts api and goes back to runtime. now, backend knows what file to compare against. backend can scp the rollout file from vm (using provisioned ssh key from deploy.sh), then create a versioned copy of the appendwatch log from mounted protected dir, and only then  check if status is ok (i.e., not compromised) in that copy of the log. so copying of rollout should precede copying the log, and copying the log should precede checking the log - in this case if log is ok then we're certain that our copy of rollout is still ok. then backend can finally pydantic validate the submission. i think to be able to do this, we're going to have to extend /push contract and require agent runtime to provide a full list of exact excerpt(s) from its web search results that justify its response - per json key in the push payload. what the pydantic validation does it attempts to find an exact match in the rollout (there is some example rollouts for you to review how web searches and responses are structured under "src/detours/detour_ai_augment/data/sample_run/.codex/sessions") and if found, validates that it truly comes from an eligible tool output (like websearch and click, open - those web tools), then shows the matching piece plus a bit of context like some chars before and some chars after, plus the json lines event in which this is located, plus the original call with which this id is associated, plus etc. (see below for details). for rendering the report we should include all these fields as specified below. all in all we should reuse step 10 rendering logic and include everything as if it was a proper researcher card, again docx and txt must be supported and read from --config config.json passed to this detour. so essentially what the human reviewer will see is a familiar card, but there will be a new section (between xlsx and docx) one per each jsonl rollout-line count pair (see below). the human reviewer will then see not only ai output but also validated result from web search. if fails to validate, the api should fail to accept submission and briefly, without details advise that this did not pass validation and they are encouraged to verify all the details of the submission.
- implement a ui that draws from duckdb, as guided by "chats/chats-20260731-tighten-api/chatgpt.md". rough skeleton is already in "src/detours/detour_ai_augment/src/control_centre/ui.py". the shape should be as in "tmp/sheikh.jsonl" but of course with no ground truth and with all ktp ai augment columns nullified. so basically it's a sanctioned source key from codex/docx innerdicts tables. the workflow then is this: the ui sanctions a particular source key from among 196 eligible source keys having ground truth data (i.e., dataset for in-context learning) or from among 78 eligible source keys with missing ground truth (i.e., dataset for augmentation); the ui controls this, and api.py only needs to wire this in as "chats/chats-20260731-tighten-api/chatgpt.md" describes (including allowing /pull or /push only once sanctioned and getting rollout path and source key from ui control endpoint now rather than .env - which still remains as an override option still for isolated unit testing of backend api; so surgical changes). the AI runtime (codex client of our FastAPI) will be building a workbook of learnings, and then it will use its learnings to annotate the ones with missing data - but ultimately human operator controls which source keys are run (and how many times) through ui.py. note that chatgpt.md fails to mention the workbook and the fact it will persist across codex exec (must be copied away via ssh by api together with rollout - and copied back to aivm at backend api initialization), and that it must be passed in full to each codex exec as part of the user prompt (so, the workbook is available in full to codex at init and also same content in workdir as file). human operator is therefore able to edit host copy of workbook in between runs. below is info on how we came to the 196 and 78 counts - and how to figure out which source keys (this is ui.py's work):
    * so far, we've shipped 200 of 307 sampled researchers (i.e., source keys), of which 2 are Kanatzidis and so effectively we shipped only 199 (explained below), and of these 3 are ineligible (explained below) and so only 196 are eligible for whatever we're doing here. explained below.
        * note that 310 sampled excel rows are listed in config.repl.json including the 10 pilot rows, but the explanation for this is that 8 draw numbers from the 310 became 5 source keys in the subsets due to contraction of 95, 107 draw numbers into "Carol M. Mangione" (Subset 1); 40, 87 into "Tom Beeckman" (Subset 1); and 155, 77 into "Zhiqun Lin" (Subset 2).
        * so, for all purposes, this explains why we have 307 available source keys after sampling 310 excel rows.
        * note also, however, that among 200 shipped there are also 125 "Mercouri Kanatzidis" and 253 "Mercouri G. Kanatzidis" that are contracted, but the thing is that the pipeline still produces two files for them (because they were both sampled and therefore produced distinct source keys!), and for this reason they also have two manual extractions, one for Mercouri and one for Mercouri G., and so accordingly 253 only has "RI_sample_7_2025NOV04_DR (n=40).docx" while 125 _also_ has "RI_sample_4_2025OCT14_DR (n=40).docx" and so for all purposes source key `{"ktp.first_name": "Mercouri", "ktp.last_name": "Kanatzidis"}` should be used as authoritative while source key `{"ktp.first_name": "Mercouri G.", "ktp.last_name": "Kanatzidis"}` should be ignored.
    * what "shipped" means is that they have already been taken up by team for downstream analyses. what "shipped" also means is that means one of: 1) they had qualified under subset 1 (or "mode" 1, synonyms) - see full definition of that in CARD_BUILD_SUBSET_DESCRIPTIONS in vars.py, but basically this means that there are no duplicates of this across xlsx/docx/ssn; 2) they were assigned to subset 2 but then _manually_ reviewed afterwards and confirmed ok and basically functionally equivalent to subset 1 entries (with the exception of Mercouri Kanatzidis, who has two source keys one of which should be discarded as noted above, but the non-discarded one is subset-1-equivalent); 3) were manually reviewed and some sections were _manually discarded and edited directly in the card file before shipping_ - see more on that below. the shipment happened across several consecutive ktp.release_batch as noted in "tmp/map_subset0_to_batch.csv": subset 1 (the original one, smaller than current one subset 1, but for the purpose of release_batch it bears the same name so pls don't conflate), subset 6, subset 7, and subset 8. now, release_batch subsets 1 through 7 were as noted, mode-subset-1 equivalents. subset 8, comprising only 3 draw numbers/source keys (45, 172, and 256 as noted in the map file), is not a mode-subset-1 equivalent because some entries were discarded per source key. so let's please keep these out here. this explains 197 count - /subset [1567]/ regular expression for the "tmp/map_subset0_to_batch.csv" file. minus 1 more ineligible/duplicated `{"ktp.first_name": "Mercouri G.", "ktp.last_name": "Kanatzidis"}` as explained above, this leaves us with 196 eligible shipped keys and 4 ineligible shipped keys.
    * the 107 unshipped ones these are all in current subset 2, partition 4, or alternatively, in the "tmp/map_subset0_to_batch.csv" file they all bear "subset X/staging" notation. these 107 fall into two categories: 1) would-be mode-subset-1 functional equivalents _iff_ missing docx fields were filled in (that is to say, ktp_ai_augment_* fields were filled in in their stead as explained in more details below); these can be easily detected by checking which ones have "KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL == False" AND "KTP_PARTITION_FLAG_SSN_COUNT_COL == 1", should be 78 source keys; 2) require discard of some sections (like release_batch subset 8); this includes all the remaining 29 source keys: 7 that remain from partition 2 (they bear "subset X/staging/partition 2 augment"), plus 6 from partition 4 ("subset X/staging/partition 4 augment") that have "KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL == True" (all of them also have "KTP_PARTITION_FLAG_SSN_COUNT_COL == 1"), plus 16 from partition 4 ("subset X/staging/partition 4 augment") that have "KTP_PARTITION_FLAG_XLSX_NON_EXACT_ANY_COL == False" but "KTP_PARTITION_FLAG_SSN_COUNT_COL > 1". this sums back correctly to 16+6+7+78 = 107. so of the unshipped, only the 78 are eligible for anything here. we keep the 29 unshipped out of scope.
    * so to summarize: 310 sampled excel rows = 310 draw numbers; minus 3 draw numbers that got contracted into same source key = 307 source keys. these are separated into shipped and unshipped. shipped = 200 source keys, of which 1 was duplicated and made ineligible (Kanatzidis) so effectively 199 source keys for use here, and 3 ineligible (release_batch subset 8), so 196 source keys left for use here. out of unshipped: 107 total, of these 78 are kept for use here and 16+6+7=29 are ineligible for various reasons.
    * **so we have 196 eligible source keys with ground truth from docx available (sometimes more than one docx innerdict!) and 78 eligible source keys that lack ground truth and need to be AI-augmented in this detour.** this makes 274 total eligible source keys for this detours. to confirm, in total 4 keys with ground truth are ineligible for this detour and 29 keys without ground truth are ineligible for the detour, in total 33 source keys ineligible. 274+33=307 total source keys which aligns with numbers above.
    

So to recap, the sequence of validation is:

* pre-index appendwatch-accepted jsonl which linenumbers are eligible for matching
    * that only includes only lines like,

      ```
      {
        "timestamp": "2026-07-27T16:11:06.607Z",
        "type": "response_item",
        "payload": {
          "type": "function_call_output",
          "id": "fco_019fa458-1fef-7a43-9f53-7d987861ad64",
          "call_id": "call_JrCO9EEdFFwnncEyo0Tky0N3",
          "output": [
            {
              "type": "input_text",
              "text": "a single text value containing citeturn0search0 symbolics; be sure to use valid unicode chars for delimiting these and put these chars as globals on top of api.py"
              }
          ],
          ...
        }
      }
      ```

      from this line we capture timestamp (as the canonical timestamp for evidence piece - because it's the last timestamp when actually this was received), also fco id, call id, and actual single-text-value output text (which we parse by ref_id like citeturn0search0 within).

      then, by looking up corresponding call_id event_msg/web_search_end line (must be unique - if not, raise error), we establish:

      ```
      {
        ...
        "type": "event_msg",
        "payload": {
          "type": "web_search_end",
          "call_id": "call_C9nCCxE2YU5zrv9kI6ewtswG",
          ...
          "results": [
            {
              "type": "text_result",
              "domain": "www.research.ed.ac.uk",
              "ref_id": "turn1search7",
              "snippet": "Image: No photo of Aziz Sheikh ... Professor ... & Sheikh, A., 21 May 2026, In: npj Primary Care Respiratory Medicine. 36, 3 p., 33.",
              "title": "Aziz Sheikh - University of Edinburgh Research Explorer",
              "url": "https://www.research.ed.ac.uk/en/persons/aziz-sheikh-2/"
            },
            ...
          ]
        }
      }
      ```

      from which we link domain, url, title, and snippet to each ref_id.

      and then finally, by same call_id we look up the originating query (must be unique, if not - raise):

      ```
      {
        ...
        "type": "response_item",
        "payload": {
          "type": "function_call",
          "id": "fc_03938c1e0667a7cc016a67831c12b08195ae364f3f129f750c",
          "name": "run",
          "namespace": "web",
          "arguments": "{\"search_query\":[{\"q\":\"\\\"Aziz Sheikh\\\" \\\"MBBS\\\" \\\"MSc\\\" \\\"MD\\\" biography education\"},{\"q\":\"\\\"Aziz Sheikh\\\" born 1968 professor medicine\"},{\"q\":\"\\\"Professor Aziz Sheikh\\\" education University College London MBBS\"},{\"q\":\"site:acmedsci.ac.uk \\\"Aziz Sheikh\\\" biography\"}],\"response_length\":\"long\"}",
          "call_id": "call_C9nCCxE2YU5zrv9kI6ewtswG",
          ...
        }
      }
      ```

      from this, we get fc_id and argument object which must be parsed as json and captured as the full dict.

      that is, it must have:

      - a valid timestamp (from fco),
      - valid call_id, which sets the scope for all further validation
      - all the other shape is as is shown above
      - the single text value is parsed by citeturn0search0 symbolics
      - fco id is the unique id for this function call output, use it to uniquely identify the source of this excerpt
      - we also store unique value of and fc id for each query.

    * and so, this dependency graph is preindexed, i think is even better to dump it into a duckdb table and use as the canonical representation of this rollout
* now we don't need to search in the jsonl - we can search in duckdb.
    * so the duckdb schema for as follows:
        * codex_fc table, 6 cols: pkey, codex.fc_timestamp (from fc json line), codex.fc_id, codex.fc_name (will always be "run" in this setup but no worries, just put the text value here - but always verify it's truly this in the rollout), codex.fc_namespace (same, will always be "web" - but need to verify in rollout) codex.fc_arguments which is a duckdb json object (put all these labels and table names as globals on top of api.py; don't touch vars.py and schema.py because this is a detour)
        * codex_fco table, 3 cols: pkey, codex.fco_timestamp (from fco jsonline), codex.fco_id
        * codex_calls table, 5 cols: pkey, codex.call_id, codex.fc_id, codex.fco_id, codex.rollout_filename (_original_ codex jsonl rollout filename including extension; can be reconstructed from session_id and timestamp from session_meta in the jsonl)
        * codex_turn_ref table, 9 cols: pkey, codex.ref_id (from event_msg corresponding turn-search), codex.call_id (establishes linkage to both fc and fco through codex_calls), codex.ref_domain, codex.ref_snippet, codex.ref_thumbnail_url, codex.ref_title, codex.ref_url (all from event_msg), codex.cite_text (raw text value from fco jsonline for parsed out related ref id)
        * finally, there is a codex_innerdicts table that follows same strict procedures as currently xlsx, docx, and ssn an serializes everything there properly with all proper columns and contract. this innerdicts table will be authoritative downstream.
    * also, in duckdb we establish a view (note that step 08 is overall closest in workflow, try to follow it as close as possible) where:
        * every row is a unique KTP_SOURCE_KEY_COL
        * KTP_FRAGMENT (see vars.py) here is the total number of lines as in `nl -ba`  in the _archived under attempts_ copy of codex. you should modify api.py so that in addition to size and sha256 it also calculated nl -ba. this is helpful because archived attempts are by our design always append only and so this will differ necessarily for different attemtps, and therefore it's a nice file-based identifier for an attempt allowing the overarching approach in this repo where unique data identification is based on filename and fragment within it. this line number will always be usable regardless of what archived copy we deal with. it's of fragment type LINE_NUMBER.  also, notably it's always possible to trim the original codex jsonl at this line number properly, recalc hash and this should match hash inside attempt json. 
        * the KTP_FILENAME_COL for each row will be corresponding codex.rollout_filename
        * now, how do other columns get filled in? other columns include ALL as in ktp.table_1_* but are called ktp.ai_augment_* instead. the list is currently in api.py as COLUMNS but you must rename this to DOCX_COLUMNS and create new one with codex prefixes and fill out these (including in api).
            * the value of these codex-prefixed fields comes obviously from the /push submission. just raw text values.
            * in addition to those, we will construct KTP_AI_AUGMENT_FOOTNOTES_COL (this label must be in globals at top of api.py; note that this is a detour and so main repl pipeline should never be affected or edited). this will be assempled from values of new codex tables above and how exactly this will look like - is shown in an output sample below. just like we have docx_parse we will also create (within detour) codex_parse module helper where we will follow that parser and implement the textual values that will go into footnotes. no need to drag machine readable stuff there - just follow the looks of sample output below and overall of docx_parse architecture. note that footnote numbers at end of each ktp.ai_augment_* value are added programmatically.
            * value of KTP_SOURCE_KEY_COL and ktp draw number is taken from  existing data based on what ktp first and last name was given in the /pull payload.
    * so that view is precreated from an appendwatch-accepted jsonl and further used for look up.
* then look up is simple - see if any row contains an exact match within their codex.cite_text, and if yes grab the necessary data. if multiple rows, select any random one (seed comes from config sample_seed). <!---unused: if multiple rows, fail this and say in error status code to /push client that this particular excerpt (cite it as as submitted) matched multiple entries on validation and they are encouraged to resubmit ensuring that each value is supported by a distinct excerpt unique across searched web pages.--->
* let's extend the /push contract where together with each excerpt submitted must provide exact url as retrieved from search results. upon validation verify that both excerpt must be within codex.cite_text and also that submitted url must match corresponding codex.ref_url, otherwise fail submission.
* note that this is purely all implemented in duckdb queries, pls consult step 08 for inspiration.

here is what the output should look like:


```
#### ktp.filename: rollout-2026-07-27T12-10-36-019fa457-aac5-7652-8669-9d571206e7cb.jsonl
**ktp.fragment**: 416

**ktp.fragment_type**: line_number

**ktp.draw_number**: 146

**ktp.first_name**: A.

**ktp.last_name**: Sheikh

**ktp.ai_augment_attempt_id**: 20260804T203221_866237Z_6074203f9b8a453f9a2dac2b822bb62b

**ktp.ai_augment_session_metadata**: {"originator":"codex_vscode","source":"vscode","cli_version":"0.146.0-alpha.3.1","model_provider":"openai","model":"gpt-5.6-sol","reasoning_effort":"xhigh","session_id":"019fa457-aac5-7652-8669-9d571206e7cb","timestamp":"2026-07-27T16:10:36.764Z"}

**ktp.ai_augment_researcher_author**: **AI-generated text**: "Professor Sir Aziz Sheikh OBE; publishes as Aziz Sheikh and A. Sheikh; ORCID 0000-0001-7022-3056."^1,2^

**ktp.ai_augment_place_of_residence**: **AI-generated text**: "Scotland, United Kingdom (Companies House country of residence); professionally based at the University of Oxford, England."^3^

**ktp.ai_augment_gender**: **AI-generated text**: "Male."^4,5^

**ktp.ai_augment_age_first_publication_according_to_openalex_profile**: **AI-generated text**: "28-29; born in December 1968, with the earliest credible work on the OpenAlex profile dated 13 December 1997. Earlier records on the profile are identity-conflation errors."^6^

**ktp.ai_augment_education**: **AI-generated text**: "BSc Physiology and MBBS, University College London; MSc, London School of Hygiene and Tropical Medicine; MD, Imperial College London."^7^

**ktp.ai_augment_academic_position_s_**: **AI-generated text**: "University of Oxford: Pro-Vice-Chancellor, Head of the Nuffield Department of Primary Care Health Sciences, and Nuffield Professor of Primary Care Health Sciences. Previously Chair of Primary Care Research and Development, Director of the Usher Institute, and Dean of Data at the University of Edinburgh."^8^

**ktp.ai_augment_social_capital**: **AI-generated text**: "Officer of the Order of the British Empire (2014) and Knight Bachelor (2022); adviser to governments, the World Bank, World Health Organization, and World Innovation Summit for Health; committee service for the Academy of Medical Sciences and Royal Society."^7^

**ktp.ai_augment_links_**: **AI-generated text**: "Oxford profile: https://www.phc.ox.ac.uk/team/aziz-sheikh; ORCID: https://orcid.org/0000-0001-7022-3056; OpenAlex: https://openalex.org/A5026215303."^8^

**ktp.ai_augment_footnotes**: 

1. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 1** in the list submitted with this value for ktp.ai_augment_researcher_author at /pull, where the raw submitted web search excerpt is boldened within the context...", retrieved from web run tool using arguments^1^ on "fco timestamp", url://from-codex.ref_url
2. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 2** in the list submitted with this value for ktp.ai_augment_researcher_author at /pull, where the raw submitted web search excerpt is boldened within the context...", retrieved from web run tool using arguments^2^ on "fco timestamp", url://from-codex.ref_url
3. "...excerpt from codex.cite_text with some chars before and some chars after **web_search_excerpt number 1** in the list submitted with this value for ktp.ai_augment_place_of_residence at /pull, where the raw submitted web search excerpt is boldened within the context...", retrieved from web run tool using arguments^3^ on "fco timestamp", url://from-codex.ref_url
4. ..etc

**ktp.ai_augment_footnote_arguments**: 

1. raw codex.fc_arguments value corresponding to fco from footnote 1 above
2. raw codex.fc_arguments value corresponding to fco from footnote 2 above
3. raw codex.fc_arguments value corresponding to fco from footnote 3 above
4. ..etc

**ktp.ai_augment_comments**:

- **AI-generated text**: "OpenAlex author A5026215303 appears conflated: it includes a 1962 A. Sheikh paper that predates Aziz Sheikh's documented December 1968 birth. Treat the literal earliest-work age and profile bibliometrics as unreliable; ORCID and the verified 1997 BMJ publication are safer identity anchors." (2026-08-04T20:32:21Z)
```

**importantly:**

> [!ATTENTION]
> **and I cannot stress that enough!**

**all** implementation must be done _surgically_.
the code is only added when necessary and
existing code is not touched unless truly necessary
(e.g., no purposelessly stripping comments etc.).

