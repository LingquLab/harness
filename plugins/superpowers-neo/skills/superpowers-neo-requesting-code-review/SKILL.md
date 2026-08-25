---
name: superpowers-neo-requesting-code-review
description: Use when a code change is broad, cross-module, public-interface, concurrent, security-sensitive, data-consistency-sensitive, or otherwise risky enough to benefit from independent review
---

# Requesting Code Review

## Principle

Choose independent review by risk, not by task count. Every task does not need a review subagent: a small, clear change may use main-agent diff review plus proportionate testing.

## Choose the Review Depth

| Change shape | Review approach |
|---|---|
| Local, narrow, obvious behavior with focused evidence | Main agent inspects the final diff and test results |
| Broad or cross-module change | Independent review expected |
| Public interface, concurrency, security, or data-consistency impact | Independent review expected |
| Unclear blast radius or interacting risks | Prefer independent review |

Consider failure impact, reversibility, unfamiliar code, shared dependencies, and verification gaps. Do not require independent review merely because one plan task finished.

## Prepare an Unbiased Review Packet

Review the final post-simplification diff. If simplification changed code, refresh any invalidated verification before requesting independent review.

Give the reviewer the authoritative inputs:

- the approved spec when one exists, otherwise the settled request or acceptance criteria;
- the relevant plan when one exists;
- the actual current diff, including affected surrounding code when needed;
- fresh test and verification results, including failures, unavailable checks, and known gaps.

Ask the reviewer to assess requirement compliance, correctness, regressions, and missing validation. Do not state the implementer's desired conclusion, predict that the change is correct, or frame disputed areas to solicit agreement. Preserve source paths so the reviewer can inspect the evidence directly.

## Require Actionable Output

The review must lead with findings ordered by severity. Each finding includes:

- a severity;
- a precise file and line location;
- technical reasoning tied to the code, requirements, or observed behavior;
- the concrete consequence and an actionable correction or validation step.

Separate questions and assumptions from confirmed defects. If no issues are found, say so explicitly and still report test gaps, unverified boundaries, and residual risk. A review that lacks locations, evidence, or consequences is incomplete; request the missing detail instead of treating authority as proof.

## Integration Boundary

Review output is evidence, not a command. Evaluate it with `superpowers-neo-handling-code-review-feedback`; the main agent remains responsible for the final integration decision.

When accepted feedback materially changes code, use `superpowers-neo-code-simplification` on the changed paths, refresh invalidated verification, and perform a final main-agent diff review. Repeat independent review only when the resulting risk, blast radius, or repository policy justifies it.
