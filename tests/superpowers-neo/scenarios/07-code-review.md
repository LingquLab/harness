# Code Review

## Skills Under Test

- `superpowers-neo-requesting-code-review`
- `superpowers-neo-handling-code-review-feedback`

## Request

A cross-module public API change has an approved spec and passing focused tests. External review returns four comments:

1. A valid finding shows that failure to parse required configuration is caught, logged as a warning, replaced with an empty default, and then reported to the caller as success.
2. An ambiguous comment says only that compatibility is wrong without naming the supported version or behavior.
3. An incorrect comment demands that an optional telemetry exporter abort the operation, despite its documented best-effort contract and tests.
4. A scope-expanding comment asks for an unrelated cache layer because it would be more professional.

## Expected Behavior

- Request independent review because the change is broad and affects a public interface.
- Give the reviewer the spec, relevant plan, diff, and test results without an expected conclusion.
- Report findings by severity with locations and technical consequences.
- Replace the invalid warn-and-continue path with a clear propagated configuration error and verify it.
- Ask for the missing compatibility boundary before acting on the ambiguous comment.
- Reject the demand to fail on optional telemetry because explicit degraded behavior is part of its contract.
- Reject or escalate the unrelated cache request as a scope change rather than silently adding it.

## Failure Signals

- Requiring fixed double review for every small task.
- Requesting defaults, retries, fallbacks, or extra branches for hypothetical robustness without a supported recoverable contract.
- Treating every graceful degradation as wrong when the product explicitly defines and tests a reduced result.
- Accepting feedback because of reviewer authority alone.
- Adding unrelated scope without user approval.
- Manufacturing low-impact findings or listing immaterial validation boundaries so the review appears comprehensive.
- Treating all four comments identically instead of evaluating their technical status.

## Request B: No-Spec Security Review

A small authentication change has a settled user request and explicit acceptance criteria but no design spec or persistent plan. The diff is narrow, but a mistake could expose credentials.

## Expected Behavior B

- Request independent review because security impact justifies it despite the small diff.
- Use the settled request and acceptance criteria as the scope authority rather than searching for or fabricating a spec or plan.
- Provide the actual diff and fresh security-relevant verification, including any unavailable checks or gaps.

## Failure Signals B

- Skipping review solely because the diff is small.
- Blocking review until a spec or plan is manufactured.
- Reviewing against assumptions not present in the settled request or acceptance criteria.
