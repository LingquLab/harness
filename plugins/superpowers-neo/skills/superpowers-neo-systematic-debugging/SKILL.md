---
name: superpowers-neo-systematic-debugging
description: Use when a bug, test failure, build issue, performance problem, or unexpected behavior has an uncertain cause, conflicting evidence, or a failed attempted fix.
---

# Neo Systematic Debugging

## Principle

Base fixes on evidence that explains the symptom. Scale the investigation to the ambiguity and impact of the problem instead of imposing a fixed ceremony.

## Evidence Loop

1. Establish the symptom through a reproduction or trustworthy logs, traces, metrics, or state. Distinguish expected from actual behavior and note the affected scope.
2. Inspect the most relevant evidence: complete errors, recent changes, inputs and outputs, configuration, environment state, and component boundaries. Trace values across boundaries when the failing layer is unclear.
3. State a falsifiable hypothesis: "X causes the symptom because Y; if true, check Z will produce result R."
4. Run the smallest useful check that can confirm or reject the hypothesis. Change one relevant variable when possible so the result remains attributable.
5. Once evidence is sufficient, fix the identified cause directly and keep unrelated changes out of the attempt.
6. Verify the original symptom and relevant regression surface. Use `superpowers-neo-validation-strategy` to choose automated tests or alternative validation.

Fix the implementation or environment boundary responsible for a failure. Do not hardcode fixture values, introduce test-only production branches, or replace a behavioral check with a source-text assertion to obtain a pass. Change a test's expected behavior or acceptance criteria only when evidence shows the expected contract is wrong; keep implementation and test aligned. Fixture repairs, setup fixes and added coverage may preserve the existing contract.

## After a Failed Fix

Treat failure as evidence that the hypothesis was incomplete or wrong. Do not stack another speculative change on top. Separate the failed attempt from the next check, revisit the observations and boundaries, then form a revised hypothesis with a new falsifying test. Repeated failures are a reason to broaden the investigation or question an architectural assumption, not to keep guessing.

## Keep Simple Failures Simple

When a direct error, diff, or state check already proves the cause, briefly confirm the evidence, apply the focused fix, and rerun the relevant check. Do not manufacture extra phases, instrumentation, or exhaustive analysis merely to make the process look systematic.

When the symptom cannot be reproduced, gather the strongest available evidence and state the uncertainty. Add targeted diagnostics only where they can distinguish competing explanations.

## Avoid

- proposing a cause without evidence that could disprove it;
- changing several plausible causes at once;
- treating a passing unrelated check as proof of the fix;
- continuing after a failed fix without renewing the investigation;
- hiding unverified boundaries or residual uncertainty.
