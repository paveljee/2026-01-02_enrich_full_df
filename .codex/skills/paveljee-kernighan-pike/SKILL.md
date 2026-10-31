---
name: paveljee-kernighan-pike
description: Apply the whole-program lessons of Kernighan and Pike's The Practice of Programming to substantial programming, design, debugging, testing, performance, portability, or automation work.
metadata:
  maintainer: paveljee
---

# The Practice of Programming

Source: Brian W. Kernighan and Rob Pike, *The Practice of Programming*. This skill is an original, practical synthesis of the book's ideas across all nine chapters. It is not a copy of the book and does not depend on having it available. Treat its principles as connected tools for judgment, not as a checklist that overrides the task's actual requirements.

## The recurring standard

Prefer a clear, correct, adequately general program to one that is ingenious but hard to understand. Simplicity is a design result: choose appropriate data, separate concerns, keep interfaces predictable, and test the behavior that matters. Improve a working baseline with evidence. Judge a change by whether another programmer can understand, use, debug, extend, and move it to another environment.

The chapters reinforce one another. Style makes debugging possible; data representation determines algorithms; interfaces determine where errors are detected and handled; tests challenge the design; measurement determines whether optimization is justified; portability changes which assumptions are safe; notation can eliminate repetitive implementation. Do not optimize or abstract one part while ignoring the contract of the whole program.

## 1. Style: expose intent

- Name objects according to their role and scope. A short local loop index can be clear; a long-lived or externally visible name needs more information. Use consistent naming for related concepts, and avoid names that misdescribe the value's meaning or lifecycle.
- Structure expressions and statements so a reader can see evaluation order and control flow. Break apart dense conditions and calculations when intermediate meanings matter. Avoid relying on precedence or side effects that a reader must mentally simulate.
- Use the language's familiar idioms where they make intent obvious, but do not confuse terse syntax with clarity. Keep formatting consistent within the codebase. Make the normal path easy to follow; keep exceptional paths explicit.
- Treat macros, textual substitution, and clever compile-time tricks with suspicion when ordinary functions or language constructs provide safer evaluation and type checking. If a macro is unavoidable, account for repeated argument evaluation, operator precedence, and debugging difficulty.
- Replace an unexplained numeric value with a named expression when the name explains its purpose, units, or relationship to other values. Do not promote every literal to a constant: an unnecessary name can hide rather than clarify.
- Write comments for constraints, intent, units, assumptions, and surprising decisions. Avoid comments that merely translate the next line into prose. Reconcile a comment with the code whenever either changes. Good code should carry most of its explanation in names and structure.

## 2. Algorithms and data structures: fit the operations

- Before selecting a data structure, list the operations, expected size, ordering needs, update pattern, and performance bounds. The cost of lookup, insertion, deletion, traversal, and allocation matters more than the data structure's popularity.
- For small or fixed collections, a simple array or linear search may beat more elaborate machinery in clarity and total cost. For growing arrays, establish capacity and growth rules, account for allocation failure, and avoid repeated one-element reallocations.
- Use sorted data and binary search when stable ordering and logarithmic lookup help; reason about the loop's invariants and the empty and one-element cases. A wrong boundary or midpoint can defeat the algorithm even when its complexity is ideal.
- Prefer trusted sorting and searching libraries when their comparison, stability, and data-ownership contracts fit. Verify the comparator implements a consistent order; do not use arithmetic subtraction when overflow can corrupt ordering.
- Linked structures help when local insertion or deletion is important but pay in pointer management and traversal cost. Trees help with ordered search; balancing determines whether their promised complexity survives adverse inputs. Hash tables trade ordering for expected fast lookup and require a deliberate hash, collision strategy, load policy, and resizing plan.
- Use asymptotic analysis to rule out designs that will scale badly, then measure real constants and memory costs. An asymptotically superior algorithm can be worse for the actual workload. Keep ownership and lifetime clear when nodes, buffers, or references move.

## 3. Design and implementation: let data shape the program

- Start from the information the program receives, must retain, must look up, and must produce. Design a representation that makes the common operation natural. The control flow and algorithm often follow from that representation.
- Work through a small concrete input by hand. Identify boundary states and how they are represented. A sentinel or explicit terminal value may simplify a repeated special case, provided its meaning is documented and cannot be confused with ordinary data.
- Compare plausible representations by the work they make easy and difficult: one record per item, grouped records, indexes, tables, or linked structures. Assess initialization, update, output generation, memory, and cleanup together, not just the main lookup.
- Prototype a simple version and refine it. When expressing the same problem in another language, preserve the data model and behavior while using that language's strengths; literal translation can inherit the weaknesses of both versions.
- Separate genuine generality from speculative machinery. A one-off prototype can omit durability and diagnostics that a reusable component needs, but production design must eventually address malformed input, failures, ownership, reproducibility, and tests.

## 4. Interfaces: make responsibilities explicit

- Design a component around services its caller needs. Specify accepted inputs, returned values, state changes, ownership, lifetime, and errors. Keep related operations coherent and avoid two ways to express the same operation unless they have distinct contracts.
- Hide representation behind the interface. Do not require callers to understand or mutate internal buffers, indexes, or parser states. Avoid surprising changes to caller-owned data; make borrowing versus copying explicit.
- Build small interfaces by using them. Parsing a familiar but irregular data format is an effective test: quoting, separators, empty fields, newlines, malformed input, and record boundaries reveal whether the interface exposes enough meaning without leaking implementation.
- Detect an error close to its source, where detail is still available. Let the layer that owns the policy decide whether to retry, substitute, report, or stop. A library should not unexpectedly print, terminate the program, or silently recover for its caller.
- Distinguish end-of-input, absent data, malformed input, and operational failure. Preserve enough error context to diagnose the problem while avoiding ambiguous return values. Keep initialization and cleanup symmetric; decide who releases each resource even when an operation fails partway through.
- Design a human-facing interface as carefully as a programmatic one. Give the user a comprehensible action or location, consistent terminology, and no irrelevant implementation detail. Documentation, examples, and diagnostics are part of the usable contract.

## 5. Debugging: explain the first wrong state

- Begin with the observed failure, inputs, program version, environment, and complete code path. Read the code before changing it. A stack trace locates a symptom, not necessarily the original cause.
- Reproduce the problem and reduce it to the smallest case that still fails. Compare failing and succeeding cases. Work backward from the first state that cannot be correct; formulate a hypothesis, run a discriminating experiment, and record the result.
- Use a debugger, trace, log, assertion, or temporary instrumentation to answer a precise question. Put checks near invariants and boundaries; avoid floods of output that bury the first useful clue. When clues are scarce, divide the path, inspect intermediate states, and verify assumptions about inputs and dependencies.
- Check that the test harness, fixture, build, configuration, and executable are the ones believed to be running. A defective test or stale binary can look like a program bug. For intermittent failures, examine timing, initialization, state sharing, concurrency, and environmental changes without assuming nondeterminism is unavoidable.
- Resort to broader or more invasive techniques only after focused approaches fail. If a dependency appears wrong, first construct a small independent demonstration. After a fix, search for the same failure pattern elsewhere and add a regression that fails on the broken behavior.

## 6. Testing: try to break the program

- Test while writing, not only at the end. Derive cases from the specification and data boundaries: empty input, one item, duplicate items, missing fields, maximum sizes, just-over-limit sizes, malformed records, early failure, and cleanup after partial success.
- Know the expected result independently of the code under test. Use literal known answers, invariants, round trips, conservation properties, cross-surface agreement, or a separate simpler implementation. A test that merely repeats the implementation's transformation may confirm the same mistake twice.
- Automate repeatable cases and make failures local and informative. Build small, faithful scaffolds around external systems so a failure can be reproduced without the entire deployment. Test the scaffold's assumptions and do not mistake a mock's invented behavior for production behavior.
- Exercise both internal structure and external contract: white-box cases target branches and invariants; black-box cases target what a caller or user can observe. Stress tests with large, adversarial, or randomized inputs reveal a different class of defects from examples.
- Inspect the tests themselves when a result seems impossible. Check fixture validity, assertion reachability, version of the tested code, and whether cleanup ran. Coverage reports show execution, not correctness. A passing suite does not prove a workflow that the suite never exercised.

## 7. Performance: measure before changing shape

- Establish a correct baseline and a real performance target. Estimate whether the alleged bottleneck could explain the observed cost. Time representative workloads, profile to find where time is spent, and distinguish CPU, allocation, I/O, and waiting.
- Improve the overall algorithm or representation before tuning a small instruction sequence. Reduce unnecessary work, choose a better access pattern, batch appropriately, and consider whether the program is solving more than the user needs.
- Change one performance factor at a time, compare against the baseline, and rerun correctness tests. Caching, buffering, precomputation, and lower-level code can trade memory, staleness, complexity, or portability for speed; measure the trade rather than assume a win.
- Estimate memory as deliberately as runtime. Check sizes of retained records, indexes, copies, and temporary buffers. Keep a simple reference implementation or benchmark so an optimized version has something trustworthy to compare with.
- Stop when the program meets its requirements. An optimization that erodes clarity and has no measured benefit is a regression in maintainability.

## 8. Portability: identify hidden assumptions

- Use defined language and library behavior. Check assumptions about integer widths, overflow, signed characters, evaluation order, pointer behavior, alignment, structure layout, and text versus binary I/O. Test supported environments rather than assuming one development machine represents them.
- Keep operating-system, compiler, path, file-format, and library dependencies isolated. Prefer a common, dependable subset across targets to scattered conditional branches. When a platform-specific operation is necessary, give it a narrow interface and test its contract.
- Specify data exchange formats, encodings, line endings, numeric representation, and byte order. Text can ease inspection and exchange when its grammar is precise; binary can be appropriate when compactness or speed matters, but its layout must be explicit.
- Plan for version upgrades and existing data. Preserve old contracts when compatibility is required; if behavior truly changes, change documentation and perhaps the name rather than silently repurposing an old interface.
- Consider international users and data: character encodings, sorting, dates, numbers, messages, and typography may differ. Keep wording and formatting adjustable instead of baking a single locale's assumptions into the program.

## 9. Notation and automation: express repeated intent once

- When code repeats the same narrow pattern, ask whether a small notation would state the data or rule more clearly. Tables, format strings, regular expressions, and declarative descriptions can separate what varies from the mechanism that interprets it.
- Use regular expressions for patterns they express well, but keep them readable and test their boundary cases. Do not force a complex parser into one opaque expression when a small parser is easier to reason about.
- Compose tools whose input and output contracts are explicit. Generate repetitive code or tests from one source of truth when manual duplication would invite divergence; inspect generated output and make generation reproducible.
- Choose the least elaborate mechanism that serves the task: direct code, data-driven interpreter, generated code, compiler, or virtual machine. A custom language has parsing, errors, documentation, and maintenance costs. Its payoff must exceed those costs.
- Use macros or on-the-fly compilation only where their power is justified and their outputs can be checked. Keep the readable specification available as a reference for generated machinery.

## Putting the lessons together

For a meaningful programming change, understand the current data representation and full path through the interface; state what behavior should be observable; make the smallest coherent change; test against an independent expectation; and measure any claimed performance improvement. If a failure occurs, investigate it rather than layering a workaround over an unexplained state. Preserve useful existing contracts, comments, diagnostics, and tests. Prefer a design another programmer can maintain after the immediate task is done.
