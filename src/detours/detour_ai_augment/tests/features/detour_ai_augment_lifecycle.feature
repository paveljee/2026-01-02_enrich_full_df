Feature: AI augmentation detour Lifecycle
  The executable specification traces every invariant and numbered item in the
  authoritative README Lifecycle while keeping Human and LLM discretion at
  observable interfaces.

  Scenario: Every Lifecycle statement has executable traceability
    Given the authoritative Lifecycle section
    Then every Lifecycle preamble invariant is assigned executable evidence
    And all 32 numbered Lifecycle items are assigned executable scenarios

  Scenario: Provisioning separates the runtime credentials and protected audit data
    Given the AI Agent Runtime deployment and provisioning programs
    Then the Runtime is isolated and supports interactive and non-interactive Codex
    And multi-agent mode is disabled
    And appendwatch and the restricted audit reader enforce separate privileges
    And guest and Backend OpenAlex credentials have independent delivery paths

  Scenario: Backend startup is exclusive and prepares one configured profile
    Given an isolated Backend configuration for one eligible namekey
    When Backend startup prerequisites are evaluated
    Then only one Backend process can hold the host singleton
    And the guest report and Codex sessions are probed through the restricted credential
    And source rows are prepared read-only before the initial pull
    And the initial pull returns JSON Lines or an opaque internal error

  Scenario: Dashboard owns only its private queue and processes one run at a time
    Given a Dashboard with prepared source rows and linked ground truth
    When two eligible runs and one queued cancellation are processed
    Then the queue persists only in NiceGUI general storage
    And each terminal run winds down its owned processes before the next run
    And detour database reads use the private unauthenticated Unix socket

  Scenario: A fresh Codex session can pull before session handoff
    Given a running Backend whose Codex session ID is not yet known
    When the Runtime retrieves the initial task and the operator supplies the session ID
    Then the pull is JSON Lines and precedes the stdin session handoff
    And Codex receives only the OpenAPI URL as its initial prompt
    And tool use push timing and stopping remain agent discretion boundaries

  Scenario: Public exchanges are opaque validated durable and projected in order
    Given a complete public HTTP exchange
    When the authoritative HTTP middleware records it
    Then the record is schema 1.1 with a UUIDv7 identity before response delivery
    And client errors stay opaque while server diagnostics remain differentiated
    And detour database access synchronizes replay records first

  Scenario: Accepted pushes commit validate retry terminate and replay
    Given the accepted production-captured push fixture
    When the captured push contour is replayed against an isolated Backend
    Then the push is preserved exactly through commit validation and terminal 410 replay
    And the completed researcher card is queryable from the Backend-owned database

  @needs_sudo
  Scenario: Appendwatch fails closed across an inaccessible runtime path
    Given a root-run appendwatch permission contour
    When a watched directory becomes inaccessible and later recovers
    Then appendwatch scopes the error and marks files first seen while blind compromised

  @operator @requires_codex_auth
  Scenario: Human-operated AIVM completes the Lifecycle and renders the researcher card
    Given a provisioned reachable AIVM with its restricted appendwatch topology
    When the Human Operator runs the queued Dashboard Backend and Codex contour
    Then the terminal workflow artifacts and Playwright researcher card prove the Lifecycle
