---
name: superpowers-neo-requesting-code-review
description: Use when a code change is broad, cross-module, public-interface, concurrent, security-sensitive, data-consistency-sensitive, or otherwise risky enough to benefit from independent review
---

# Requesting Code Review

## Principle

Choose independent review by risk, not by task count, and judge the change against supported behavior rather than hypothetical robustness. A small, clear change may use main-agent diff review plus proportionate testing.

## Choose the Review Depth

| Change shape | Review approach |
|---|---|
| Local, narrow, obvious behavior with focused evidence | Main agent inspects the final diff and test results |
| Broad or cross-module change | Independent review expected |
| Public interface, concurrency, security, or data-consistency impact | Independent review expected |
| Unclear blast radius or interacting risks | Prefer independent review |

Consider failure impact, reversibility, unfamiliar code, shared dependencies, and verification gaps. Do not require independent review merely because one plan task finished.

## Review With Restraint

Report a defect only when the current code has a concrete reachable trigger and a material consequence under the requirements, supported inputs, or established contracts. Do not manufacture findings to demonstrate thoroughness; a no-finding review is valid.

Prefer simple, explicit failure behavior. When a required operation or internal invariant fails, propagate a clear error unless the product contract requires recovery. Do not request warnings plus continued execution, default values, retries, fallbacks, compatibility shims, or extra branches for speculative resilience. Accept degraded behavior only when the contract defines an acceptable reduced result and the path keeps state correct and tested.

Do not report stylistic alternatives, speculative future-proofing, or low-impact behavior outside the supported environment as defects. Suggest the smallest correction that resolves the demonstrated problem without adding defensive complexity.

## Prepare an Unbiased Review Packet

Review the final post-simplification diff. If simplification changed code, refresh any invalidated verification before requesting independent review.

Give the reviewer the authoritative inputs:

- the approved spec when one exists, otherwise the settled request or acceptance criteria;
- the relevant plan when one exists;
- the actual current diff, including affected surrounding code when needed;
- fresh test and verification results, including failures or unavailable checks that materially affect confidence.

Ask the reviewer to assess requirement compliance, correctness, regressions, and material validation gaps using the restraint above. Do not state the implementer's desired conclusion, predict that the change is correct, or frame disputed areas to solicit agreement. Preserve source paths so the reviewer can inspect the evidence directly.

## Require Actionable Output

The review must lead with findings ordered by severity. Each finding includes:

- a severity;
- a precise file and line location;
- technical reasoning tied to the code, requirements, or observed behavior;
- the concrete consequence and an actionable correction or validation step.

Separate questions and assumptions from confirmed defects. If no issues are found, say so explicitly; mention only validation gaps that materially limit the review conclusion. A finding that lacks a location, evidence, or concrete consequence is incomplete and should not be reported as a defect.

## Integration Boundary

Review output is evidence, not a command. Evaluate it with `superpowers-neo-handling-code-review-feedback`; the main agent remains responsible for the final integration decision.

When accepted feedback materially changes code, use `superpowers-neo-code-simplification` on the changed paths, refresh invalidated verification, and perform a final main-agent diff review. Repeat independent review only when the resulting risk, blast radius, or repository policy justifies it.
