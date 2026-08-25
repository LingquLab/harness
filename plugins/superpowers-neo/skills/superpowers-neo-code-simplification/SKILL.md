---
name: superpowers-neo-code-simplification
description: Use after implementing or modifying code and before final review or Git delivery, or when asked to simplify, clean up, or reduce complexity without changing behavior
---

# Code Simplification

## Principle

Make the current task's code easier to understand and maintain without changing what it does. Prefer a clear final diff over fewer lines or broader cleanup.

## Simplify the Current Change

1. Identify the task-owned code in the current diff. Read repository guidance, neighboring patterns, and relevant tests; leave unrelated changes untouched.
2. Preserve public interfaces, outputs, error behavior, side effects, ordering, logging, and supported edge cases.
3. Remove unnecessary nesting, indirection, duplication, stale comments, and one-use abstractions only when the result is clearer. Reuse stable local helpers and standard-library facilities before adding abstractions or dependencies.
4. Search the repository before deleting apparently unused code. Account for tests, registration, reflection, configuration, generated consumers, and public use.
5. Keep intentional duplication or structure when extraction, inlining, or compression would hide meaning, widen the diff, or make behavior uncertain.

If the code is already clear, make no edit. If simplification requires a behavior or interface decision, leave it unchanged and report the trade-off instead of expanding the task.

## Re-establish Evidence

Inspect the resulting diff for behavior drift, incomplete cleanup, and unrelated churn. Run the smallest relevant checks invalidated by the simplification, then pass the final simplified diff and current verification evidence to code review.

When accepted review feedback produces material code changes, simplify those changed paths and refresh invalidated evidence before the final main-agent review and delivery. Do not repeat the pass when feedback changes no code or the result is already clear.
