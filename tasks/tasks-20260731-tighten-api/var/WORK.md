# Tighten API: complete

## Objective and disposition

Aligned `src/detours/detour_ai_augment/src` and its tests with the latest
authoritative README. The post-pull re-audit reopened TASK because Backend did
not synchronize replay before every detour-DuckDB access and Dashboard DB reads
used a hidden token-authenticated FastAPI route instead of the required
host-private Flask/Unix-socket IPC. Both gaps are resolved.

## Completed implementation

- Backend owns one persistent detour-DuckDB connection. Startup, replay append,
  projected-outcome reads and Dashboard reads all pass through one locked
  synchronization boundary that projects every unprojected replay record in
  append order. Synchronization/recording failures fail Backend loudly.
- Removed hidden `GET /_control/pull`, its bearer-style token and Backend-owned
  Dashboard event models. Public FastAPI exposes only `/pull` and `/push`.
- Added a separate Flask query application served on a mode-0600 Unix-domain
  socket. Query failure calls `os._exit(1)`; startup/shutdown clean up the
  server, socket, persistent DB connection and replay lock.
- Dashboard uses an unauthenticated AF_UNIX HTTP client for Backend-owned
  SELECT results. Backend readiness now proves both public pull and private
  database IPC. Dashboard queue/run events remain NiceGUI-storage-only models.
- Added Flask 3.1.2 to the detour feature and refreshed `pixi.lock` (Flask,
  Werkzeug and Blinker present; `pixi lock --check` passes).
- Kept the default web-search-language factory inline, with an explicit
  `cast(list[TargetWebSearchQueryLanguage], ...)` to satisfy invariant-list
  typing without an extra named helper.
- The operator contour uses a per-run socket and asserts socket type, 0600 mode
  and shutdown cleanup on the production host.
- Corrected the Control Centre repository-root parent index so its supervised
  Backend starts from the repository and can import the `src` package on the
  production macOS contour.
- Operator AIVM reachability, guest-key and appendwatch probes now have
  ten-second bounds and streamed preflight status. The full-workflow contour
  emits step/heartbeat/record-count progress and fails immediately when the
  Control Centre records a failed run.
- Operator teardown isolates the Control Centre from the terminal's Ctrl+C,
  then stops it explicitly, reaps surviving local descendants, verifies both
  service ports were released, and closes Playwright in a `finally` block.
- Registered `needs_sudo` in the detour conftest and applied it only to the
  three real appendwatch EACCES tests. The existing root task runs every test
  carrying that marker from the whole detour test directory; a sibling task
  runs the remaining aggregate suite and real-API contour unprivileged.
- Rechecked the full synthetic commit contract. `coerce_schema_v1` is an input
  migration flag and is always excluded from serialization after validation,
  exactly matching README; schema 1 (`1` and `"1"`) and explicit v1 coercion
  remain intact.
- Schema 1.1 now permits nullable `response_headers` and `duration_usec`. The
  unsent synthetic commit serializes both as null, completed public exchanges
  still require both values, and schema 1 preserves its non-null contract.
- Rechecked outcome classification: Pydantic and evidence-against-rollout
  failures produce Markdown retry; rollout-index/integrity and appendwatch
  failures remain opaque 500s.
- Preserved human-signed comments and user staging. No stage/unstage command
  was used; no main-pipeline behavior outside the HTTP schema contract changed.

## Added regression coverage

- Persistent connection identity and synchronization of newly appended replay
  before every Dashboard SELECT.
- Absence of Dashboard query and `/_control` from public FastAPI.
- Unauthenticated AF_UNIX Dashboard request.
- Separate Flask app response, fatal query failure, real UDS round trip/mode/
  cleanup, and refusal to overwrite a non-socket path.
- Exact synthetic commit JSON contour and schema-1.1 serialization.
- Explicit no-flag v1/v1.1 round trips and consumed coercion-flag round trip.
- Native v1.1 null response-metadata round trips and v1 rejection for both
  legacy schema-version spellings, with and without requested coercion.
- Evidence Markdown versus rollout-index/appendwatch 500 classification.
- Operator production-host Unix-socket assertions.
- Exact three-test `needs_sudo` selection and unprivileged aggregate-suite
  exclusion.
- Dashboard repository-root resolution and failed-run log emission used by the
  operator fail-fast contour.

## Verification

- `pixi run -e detour-ai-augment lint`: passed (Ruff; mypy over 95 files).
- Flask IPC module: **3 passed, 1 skipped**. Only the real bind round trip is
  skipped because this managed Linux sandbox denies AF_UNIX `bind(2)` with
  `EPERM`; Flask behavior and failure handling pass hermetically, while the
  operator test retains the real production-host round trip/assertions.
- Complete non-root detour suite excluding `needs_sudo`: **116 passed, 47
  skipped, 3 deselected**; the isolated marker contour selected exactly three
  tests and skipped them without root.
- Explicit detour real-API test: skipped because `OPENALEX_API_KEY` is absent.
- `pixi lock --check`: passed.
- `git diff --check`: passed.
- Final schema refinements: HTTP schema tests **28 passed**; Backend API tests
  **47 passed, 36 skipped**; complete detour suite **116 passed, 50 skipped**;
  lint passed again.
- Sudo-task split: `pixi lock --check`, Pixi task-graph dry run, Ruff and mypy
  over 95 files all passed.
- Operator hardening: complete non-root detour task **118 passed, 47 skipped,
  3 deselected**; its explicit real-API follow-up skipped because the key is
  absent. Repo-wide Ruff and mypy passed. In the managed Linux environment,
  the operator entry point reported missing `limactl` during preflight before
  entering the first test; the full production contour remains host-only.

The official `pixi run -e detour-ai-augment pre-commit` was invoked but Pixi
still cannot resolve cross-feature task `test-detour-mode0-econ-stats` from the
AI-augment environment. Its contour was therefore executed manually:

- repo lint: passed;
- main tests: **100 passed, 4 skipped, 34 failed**; failures require unavailable
  network/`splink_udfs`, except one host-only `/Volumes/...` fixture;
- main real-API contour: **1 skipped, 137 deselected** (API key absent);
- mode-3 detour: **6 passed**;
- step-4 detour: **4 failed, 1 skipped**, all from unavailable `splink_udfs`;
- mode-0 detour: **2 passed, 2 failed**, both because managed sandboxing blocks
  Kaleido/Chromium `shutdown(2)`;
- the root marker contour cannot enter `sudo` under the container's
  no-new-privileges flag; its exact three-test selection is verified, and the
  remaining aggregate suite passed unprivileged as above.

These are task-graph/execution-environment limitations, not failures in the
AI-augment implementation. TASK is complete pending the normal human-operated
operator E2E on its provisioned macOS/AIVM environment.
