---
name: superpowers-neo-verification-before-completion
description: Use when work is about to be described as complete, fixed, resolved, passing, or ready, especially after final edits or when validation is incomplete or mixed
---

# Verification Before Completion

## Principle

Completion claims need fresh evidence from the final relevant state. Stale results, inspection, confidence, and inference are not confirmed passing results.

## Build Current Evidence

1. List each claim and the behavior, interfaces, and dependencies it covers.
2. Run focused checks that directly exercise the changed behavior against the final artifact.
3. Broaden to compile, static, integration, end-to-end, or wider regression checks where shared dependencies and blast radius justify them. Do not run a full suite as ritual, but do not stop at a narrow test when the change can affect wider consumers.
4. Inspect the final diff and outputs. If a later edit could invalidate a check, rerun that check before relying on it.

Use exact command output and exit status. A check from before the final relevant edit is stale; a similar test is not evidence for one never run.

Treat installing common packages missing from the system Python, such as `pytest` or `PyYAML`, as pre-authorized when needed for validation.

## Classify Every Gap

| Result | Required handling |
|---|---|
| Passing current check | State the command and the boundary it confirms. |
| Current-change failure | Diagnose and fix it, then rerun the affected checks. Do not claim completion while it remains. |
| Baseline failure | Establish that it predates or is independent of the change using an unchanged baseline, trusted prior result, or other concrete comparison. Record it without fixing unrelated scope unless the user asks. |
| Unavailable validation | State the blocked check, the environment, hardware, permission, credential, or external-system reason, any substitute evidence, the untested boundary, and residual risk. |
| Unexplained failure | Investigate it; do not label it baseline or claim the affected surface passes. |

Do not call a failure "pre-existing" merely because it looks unrelated. If a clean baseline comparison is unsafe or unavailable, report that attribution as unresolved.

## Report Without Overstatement

Report separately:

- confirmed checks and what they prove;
- failures caused by the current change, if any;
- established baseline failures;
- checks not run and why;
- residual risks and the resulting bounded completion status.

Focused tests may pass while a full suite has a confirmed baseline failure and hardware validation is unavailable. Report that the focused behavior passed, the full suite did not pass cleanly for a documented baseline reason, and runtime behavior remains unverified. Never compress this into "all tests pass" or "runtime is good."

## Red Flags

- "It should pass" or "the diff looks correct."
- Reusing results invalidated by later edits.
- Stopping at focused tests despite a shared-interface change.
- Expanding scope to repair an unrelated baseline failure.
- Treating unavailable hardware or external services as successful validation.
- Claiming all checks pass when any check failed or was not run.
