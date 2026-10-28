# Bounded diagnostics

## Define the question and evidence

Identify the exact subject of the check and distinguish it from the diagnostic
agent, its helpers and related work. State the question, authorized scope,
relevant evidence sources and what would answer it. Start with the smallest
authoritative observation; expand only when needed and permitted by the handoff.
Prefer targeted queries and structured fields over broad dumps or exploratory
history searches. Do not let similar names substitute for verified identity.

Keep conclusions proportional to evidence. Missing data means it was not found
in the inspected source; a failed query does not establish absence. A successful
diagnostic command does not by itself prove the underlying operation succeeded.
Separate observed state, interpretation and unresolved uncertainty. For example,
finding no task receipt does not prove that no process exists elsewhere.

## Bound work and stop deliberately

Default to EXEC with an exact bounded command or script; use TASK when green-local
judgment or required recovery cannot be expressed through EXEC. An OPEN alone
does not authorize a diagnostic. Existing recovery rules still apply. Scope the handoff to the decisions needed
next, with a time budget and explicit stopping conditions. Enforce command and
subprocess timeouts with execution tools; an outer agent deadline or prose alone
does not bound individual actions.

Return when the question is answered. If evidence or prerequisites are unavailable,
report the limitation and the appropriate non-PASS status. Recover from a local
error only within the authorized scope and budget; do not turn repeated failed
attempts into an open-ended investigation or silently broaden the task. Respect
one-shot checks that explicitly prohibit retries. Recovery clearance requires its
own evidence about unfinished effects; it cannot be inferred from a narrower
status lookup. Preserve read-only scope and avoid unnecessary helper artifacts.

## Make execution boundaries explicit

Determine which shell or interpreter actually runs each command; the host OS does
not determine the AI tool's shell. Prefer structured argv or an explicit script
interpreter over nested command strings. Account for every parser boundary so
variables and quoting reach the intended interpreter unchanged. For example,
Bash expands PowerShell `$_` inside double quotes; a quoted heredoc or direct
interpreter invocation avoids that extra expansion. Use bounded, structured
output rather than parsing formatted dumps when possible.

## Return only supported conclusions

Generic warnings and timeouts identify symptoms, not their root cause. Use specific
validation or execution evidence before attributing failure to a version, field,
permission or remote service. Distinguish receipt, launch, completion and validated
outcome. EXEC defaults to no AI review; blue sets `ai_review=true` for possibly restricted output;
all existing egress, execution and recovery rules still apply.
