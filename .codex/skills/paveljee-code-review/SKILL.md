---
name: paveljee-code-review
description: Review suspected redundant code before removing it or moving it into the more shared or higher level of abstraction.
---

# Code review

Grep for code that may duplicate an existing relevant shared or higher-level abstraction.

For each suspicious code, read the **entire code unit** containing it (such as the whole function), then the **entire relevant code**, including inherited objects. Only then decide what the code does and whether the relevant shared or higher-level code already covers it. Do not trim isolated lines without reviewing the purpose of the whole code unit.

Remove a code line only when its logic is fully covered by the relevant shared or higher-level code and no logic is lost. For anything still needed, consider whether it belongs in the relevant shared or higher-level code instead of downstream code; move it only if that placement fits. Keep changes surgical.

If coverage, lost logic, or placement is in doubt, stop and ask the [user][paveljee].

[paveljee]: https://github.com/paveljee
