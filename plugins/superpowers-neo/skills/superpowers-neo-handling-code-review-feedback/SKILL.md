---
name: superpowers-neo-handling-code-review-feedback
description: Use when evaluating or implementing code review feedback, including comments that appear straightforward, ambiguous, disputed, technically significant, potentially incorrect, or scope-expanding
---

# Handling Code Review Feedback

## Principle

Treat every review comment as a technical claim to verify, not an instruction to obey. Reviewer confidence, status, or tone is not evidence; the main agent owns the final integration decision.

## Establish the Facts

Before responding or editing:

1. Read the cited lines and enough surrounding code to understand the real path.
2. Compare the claim with the governing spec when one exists, otherwise the settled request or acceptance criteria, plus any relevant plan, repository guidance, and current diff.
3. Check actual behavior with focused tests, reproduction, documentation, or other direct evidence when useful.
4. Separate correctness, preference, risk, and requested scope. Ask for a precise location or consequence when the feedback does not provide one.

Do not implement first and investigate later. Agreement language such as "good catch" does not replace technical verification.

Treat requests for warnings, defaults, retries, fallbacks, or compatibility paths as behavior changes, not automatic hardening. Accept them only when a supported failure is recoverable under the product contract; otherwise preserve or restore the simpler explicit failure.

## Classify and Act

| Classification | Response |
|---|---|
| Correct | State the verified issue, implement the smallest in-scope correction, and re-run checks covering the correction and affected regressions. |
| Ambiguous | Explain the competing interpretations and ask a targeted clarification before making a consequential edit. Continue only with safe fact-finding. |
| Incorrect | Decline the change and cite the code, requirement, or behavior that disproves the claim. Add a focused check if it usefully makes the evidence durable. |
| Scope-expanding | Do not implement it under the current approval. Show how it exceeds the spec or acceptance criteria, state whether it may be useful separately, and request a scope decision if needed. |

A technically valid observation can still request out-of-scope work. Acknowledge the risk without silently broadening the task; fix only the in-scope part or obtain approval for the expansion.

## Close the Loop

For each finding, record the classification, evidence, action, and verification result. For unresolved ambiguity, state exactly what decision is needed. For rejected feedback, remain factual and give the evidence rather than performing agreement or disagreement.

After accepted changes, inspect the resulting diff and rerun any checks invalidated by the edit. Do not call feedback resolved from the edit alone.

## Red Flags

- Accepting a comment because the reviewer sounds authoritative.
- Editing before locating or reproducing the claimed problem.
- Guessing what ambiguous feedback means.
- Adding unrelated architecture "for professionalism" without approval.
- Saying a finding is fixed without fresh verification.
