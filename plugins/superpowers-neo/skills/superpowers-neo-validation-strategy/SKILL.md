---
name: superpowers-neo-validation-strategy
description: Use when deciding what tests or other evidence a code, configuration, or documentation change needs, especially for bug fixes, risky behavior, unavailable hardware, or costly automation.
---

# Neo Validation Strategy

## Principle

Choose validation by failure risk, affected boundaries, and available environments. Test order is a tool, not a quality gate; completion still requires credible evidence that the intended behavior works and important regressions were not introduced.

## Choose the Approach

1. Define the behavior being changed, likely failure modes, impact, and regression surface.
2. Prefer TDD (test-first development) when behavior is clear, regression risk is high, or a stable bug reproduction can demonstrate the failure before the fix.
3. Explore or implement first when uncertainty, prototyping, legacy structure, or setup cost makes that more effective. Add useful tests during or after implementation. Never discard valid implementation solely because tests were not written first.
4. Select evidence proportional to risk:
   - Narrow, low-risk changes may need focused tests, a parser or linter, compile checks, or direct inspection.
   - Behavioral logic usually merits targeted unit or component tests.
   - Cross-component changes merit integration or end-to-end checks at the affected boundaries.
   - High-impact changes merit broader regression coverage and realistic failure-path checks.

## Keep Test Work Proportional

Use the existing test facilities and the smallest evidence needed for the requested behavior. Do not build an extra test framework, file-locking layer, protection system, or general-purpose harness for hypothetical risks. If an unrequested testing capability is necessary, describe it and obtain explicit user approval before implementing it.

Exercise externally meaningful inputs, outputs and real failure boundaries. Use mocks for relevant external dependencies, not to freeze every private helper call or execution order. A green test must still exercise the behavior the user relies on.

For floating-point or ML/GPU checks, use the contract's tolerances and relevant reproducibility settings. Investigate differences that exceed them or affect acceptance; do not demand byte identity without a requirement or loosen tolerances merely to pass.

Validation performed during development and tests retained in the repository are separate decisions. A successful experiment does not automatically belong in the deliverable.

## Retain Only Key Tests

- Commit only tests protecting core requested behavior, an essential public contract, or a concrete significant regression. Prefer a small set of meaningful cases over exhaustive speculative coverage or tests that mirror implementation.
- Before staging, delete task-created non-core test code: one-off probes, debug scripts, disposable reproductions, temporary harnesses and their generated artifacts. Keep verification results in the delivery summary; do not commit these files merely because they were useful during development.
- Preserve pre-existing tests and user-owned files. This cleanup applies only to disposable artifacts created for the current task; it does not authorize broad test deletion. A test framework or test code explicitly requested as a deliverable stays in scope.

## Bug Fixes

When the cause is uncertain, use `superpowers-neo-systematic-debugging` first.

Add a practical regression test when the symptom is stable and the existing framework can express it without disproportionate setup. Make the test cover the reported failure, not incidental implementation details. When practical, confirm it detects the uncorrected behavior using a safe reproduction or prior revision; do not recreate the implementation merely to satisfy test ordering.

If automation depends on unavailable hardware, external services, timing, credentials, or excessive setup, use the strongest feasible alternative: a minimal reproduction, captured logs, compile or static checks, a focused integration check, or documented manual validation.

Once the acceptance conditions and necessary checks are satisfied, stop. Additional diagnostics, coverage or infrastructure require a remaining concrete question, not a desire to make the workflow look more thorough.

## Completion Evidence

Record:

- the checks run and their results;
- the behavior and boundaries they establish;
- why an automated regression test was omitted, when applicable;
- any untested boundary and its residual risk.

An explanation for missing automation is not itself validation. Pair it with concrete alternative evidence, and never claim more coverage than the evidence supports.
