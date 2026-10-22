# Bounded task-state checks

## Define the question before querying

Keep the target task ID and iteration distinct from the current diagnostic task.
A similarly named directory, this agent's process, or its live transcript is not
evidence about the target. Use the current authorized session's state; do not
search other sessions or task histories unless explicitly scoped.

For a record-only check, query only the exact target row in `tasks` and its
`runs/<target-task>/<iteration>/execution/execution.json` receipt. Open SQLite
read-only with a short lock timeout and use bound query parameters. Select only
needed columns, such as task_id, iteration and state; read only required receipt
fields, such as status, exit_code, pid, started and finished. Do not dump tables,
traverse unrelated directories, read lock files or inspect agent transcripts.
Do not create helper files for a read-only task; pass a short script on stdin.

Report absent records as absent in the inspected session. Missing records and
receipts do not prove that no related process exists anywhere. A record-query
PASS is not a server-check PASS, command success, or recovery clearance. Report
receipt state as recorded: STARTING/RUNNING is not completion; EXITED alone does
not validate the requested checks.

## Stop instead of broadening

Blue should give a small diagnostic one bounded action and an explicit stop
condition. Green applies the requested timeout to the tool/subprocess, not just
the outer TASK deadline. For example, a one-shot record query can use a 30-second
command timeout while leaving the protocol's minimum total timeout for agent
startup and result delivery. Instructions alone do not enforce a wall-clock cap.

Return immediately once the scoped question is answered. Missing prerequisites,
unreadable records, command failure or timeout end a one-shot query with BLOCKED
and concise evidence; do not switch tools or extend the search to fill the task
budget. If process recovery is actually needed, scope it separately. Match a
recorded PID with its start time and task identity; exclude the current diagnostic
agent and helper processes. A failed process query is not proof of no processes.
Do not clear recovery without the required process/effect evidence.

Prefer EXEC for a known deterministic diagnostic script and TASK when green AI
judgment is needed, subject to Bridge's existing recovery rules. Use
`ai_review=false` only for deliberately non-sensitive bounded output. A generic
"Malformed cross-zone envelope ignored" warning indicates protocol rejection,
not proof of a particular unsupported field or execution outcome. Diagnose from
specific validation evidence rather than repeatedly dispatching capability probes.

## Windows shell boundaries

Distinguish the AI tool's shell from EXEC's chosen interpreter. On Windows an AI
Bash tool may be Git Bash; it does not make PowerShell the default. EXEC selects
Bash, PowerShell or Python explicitly; argv execution has no implicit shell.

Avoid nested Bash/PowerShell/Python command strings. For Python through Bash, use
a single-quoted heredoc delimiter (`python - <<'PY'`) so Bash does not expand the
script. If Python must invoke PowerShell, pass an argv list with the PowerShell
script as one literal argument and a subprocess timeout. Never place PowerShell
`$_` or `$name` unescaped inside a Bash double-quoted command: Bash expands it
before PowerShell receives it. Prefer structured output and exact fields over
formatted process dumps and loose substring matches. On quoting failure, follow
the handoff's stop condition instead of iterating through nested quoting variants.
