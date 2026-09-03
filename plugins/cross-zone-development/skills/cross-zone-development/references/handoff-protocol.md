# GitHub Handoff Protocol

Use this protocol for both roles. The issue is an append-only audit trail: the original body holds iteration 1, and later iterations are added as comments rather than silently rewriting prior requests or results. Labels are optional; protocol fields determine state.

## Identity and Revision

Generate one opaque, non-sensitive `Handoff-ID` and retain it for the life of the issue. Start `Iteration` at 1 and increment it for each new candidate revision. Identify the repository by its normal GitHub owner/name and bind each iteration to an immutable full commit SHA or artifact digest. A branch may be included for navigation, but never substitute it for the immutable revision.

Do not paste source, a diff, a patch, configuration contents, credentials, or runtime data into the issue. If the candidate is not available to the green zone through an approved repository or artifact channel, report that transfer prerequisite instead of using the issue as a file-transfer mechanism.

## Blue Request Record

Create the issue with a title such as `[Cross-zone handoff] concise target`. The issue body for iteration 1, or a later `BLUE_READY` comment, uses these fields:

```text
Protocol: cross-zone-development/v1
Event: BLUE_READY
Handoff-ID: <opaque id>
Iteration: <positive integer>
Repository: <owner/name>
Revision: <full commit SHA or immutable artifact digest>
Target class: <non-sensitive environment class, not an internal endpoint>

Goal:
<behavior to validate>

Observed in blue:
<non-sensitive symptom, relevant change context, and completed local checks with outcomes>

Prerequisites:
- <required package, feature flag, fixture class, account capability, or service state>

Setup:
1. <bounded preparation step or safe command>

Test cases:
1. <safe case name>
   - Input/fixture: <non-sensitive class or approved fixture reference>
   - Action: <exact operation or safe command>
   - Expected: <observable result, status, or invariant>
   - Evidence requested on failure: <error code, failing step, location, and bounded log type>

Expected behavior:
<overall pass condition and treatment of skipped or not-run cases>

Allowed green actions:
<read-only and isolated test/deploy scope already authorized>

Stop conditions:
<time, attempt, safety, or shared-service boundary>
```

Omit fields that would reveal protected topology or data; do not replace them with secret values. If a missing field prevents safe execution, the green role returns `BLOCKED`.

## Green Result Record

Post one final comment per iteration. Do not stream progress or logs into GitHub.

```text
Protocol: cross-zone-development/v1
Event: GREEN_RESULT
Handoff-ID: <copied id>
Iteration: <copied integer>
Revision tested: <copied immutable revision>
Status: PASS | FAIL | BLOCKED | NEEDS_HUMAN

Checks:
- <safe check label>: <pass, fail, blocked, or not run>; <duration or attempt count when useful>

Finding:
<specific failing case and step, trigger condition, retry behavior, and impact; no code>

Failure details:
- Error/status code: <exact non-sensitive value or none>
- Location: <candidate-relative file/function, relevant stack frame, or test step; no source line>
- Observed vs expected: <concise comparison>
- Related log excerpt: <short redacted excerpt or none>

Evidence summary:
<sanitized interpretation and correlation; literal fragments only within the skill limits>

Suggested blue action:
<conceptual direction or next discriminating experiment; no code>

Egress review:
- No code, diff, patch, configuration, or reconstructive pseudocode
- No bulk logs, full stack traces, full command output, or attachments
- Literal fragments within 10 lines and 1,500 UTF-8 characters
- No secrets, internal endpoints, infrastructure paths, identities, payloads, or business data
- Comment within 4,000 UTF-8 characters
```

Status meanings:

- `PASS`: every requested check ran against the named revision and met the stated pass condition.
- `FAIL`: at least one requested check ran and produced safe, actionable failure details rather than only a generic category.
- `BLOCKED`: the check could not run because a prerequisite, permission, revision, or allowed target was unavailable.
- `NEEDS_HUMAN`: useful detail cannot cross the boundary safely, or continuing requires a protected or disruptive action.

An omitted check is not a pass. A result whose ID, iteration, or revision does not match the latest `BLUE_READY` record is stale or unrelated and must not drive a fix.

## Iteration and Closure

For another test cycle, blue posts a new `BLUE_READY` comment with the same handoff ID, an incremented iteration, and a new immutable revision. Green answers only the latest valid iteration. Blue owns issue closure after it has consumed the final result and recorded a short non-sensitive resolution; green does not close the issue.
