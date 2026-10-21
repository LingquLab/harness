# Direct cross-zone execution

Approved scope: add EXEC alongside TASK. Blue supplies an argv command or an
explicit interpreter and script. Bridge runs it unchanged in the session directory;
green AI only reviews saved output. Preserve execution facts and existing transport,
deduplication, cancellation, restart and egress constraints. No automatic replay.

1. Protocol (`cross_zone/protocol.py`, protocol reference): EXEC shares TASK's goal,
   checks and total timeout, adds execution plus execution_timeout_seconds, and
   forbids revision. execution is either argv or interpreter (bash/powershell/python)
   plus script. Keep strict fields, size bounds and legacy TASK compatibility.
2. Execution (`cross_zone/execution.py`, agent/controller/store): persist a local
   execution receipt before starting, capture stdout/stderr locally, bound command
   runtime/output and reserve 60 seconds of total budget for AI review. Commands
   use shell=False; scripts are saved unchanged for their explicit interpreter.
   EXEC never resumes through ANSWER and cannot start while recovery is unresolved;
   blue can use existing read-only TASKs to establish state. Review AI cannot rerun
   commands or change files. Bridge owns execution status/exit code, including when
   review fails. Cancel/interruption never replays the command.
3. Documentation/skill: describe execution forms, foreground-only commands, local
   raw logs, reviewed results, execution metadata, recovery and version compatibility.
4. Verification: parser rejection and legacy compatibility; real subprocess tests
   for argv quoting, scripts, cwd/environment, nonzero exit, timeout/cancel/output
   bounds and receipts; controller tests for dedup, restart and AI/egress failure.
   Verify full result size including execution facts. Run existing suites and skill
   validation, simplify, independent review, then update existing PR28.

Execution facts carry only status and exit_code across zones. Raw command output,
script text and local receipts stay green; all exported summaries require existing
AI and deterministic egress checks. Linux tests cannot establish live Windows
PowerShell/taskkill behavior; report that boundary.
