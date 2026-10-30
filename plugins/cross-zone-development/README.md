# Cross Zone Development

[中文文档](./README_CN.md)

[中文用户指南](./USER_GUIDE_CN.md) covers setup and day-to-day operation.

This Codex and ZCode plugin coordinates blue and green AI agents through HAPI.
A Windows bridge in the green protected-service zone invokes its local Claude
Code-compatible CLI and sends only bounded, reviewed results back to blue. GitHub
Issues and browser automation are not part of the transport.

## Green runtime setup

The plugin ships the Python Bridge in [`cross_zone`](cross_zone), its Git Bash
launcher [`start-bridge.sh`](start-bridge.sh), configuration templates, and
offline runtime tests. On the green Windows host, install Python 3.11+, Git for
Windows, and CodeAgentCLI, then copy this plugin directory to an approved local
location. No third-party Python package is required.

Copy [config.windows.json](config.windows.json) to the ignored
`config.local.json` and set `access_key`. The templates default to
`hub_url=https://su.kurox.cn/hapi/`; change it locally for another Hub. The Windows
template starts CodeAgent with `--effort low`. Start it from the
directory green authorizes as the task workspace:

```bash
<plugin-dir>/start-bridge.sh
# Or specify local configuration:
<plugin-dir>/start-bridge.sh discover [config-file]
```

For automatic restart after a Bridge exit, keep the watchdog running in a separate
Git Bash terminal:

```bash
<plugin-dir>/watch-bridge.sh
```

It restarts default discovery after each exit, waiting 3 seconds between starts
(`BRIDGE_RESTART_DELAY` overrides the delay). Stop the watchdog with `Ctrl+C`.
Update disk code before ending the Bridge process to load the new version on
restart. Existing instance locking still applies. Interrupted tasks are reported as
unknown and never replayed. Queued tasks continue without manual acknowledgement;
the agent first checks saved run receipts, surviving processes and relevant effects.
Until those are established it may only perform read-only diagnostics and report
concrete blockers to blue. Recovery evidence travels locally, not in the wire schema.
Older global recovery pauses are migrated automatically on startup.

Version 0.6.0 adds default single-session discovery initiated by blue OPEN and a
complete Chinese user guide. Explicit-session workers remain available.
It uses CROSS_ZONE and cross-zone/v3. All messages omit `target`;
READY and legacy green OPEN report the running Bridge release in `version`. Legacy target fields are
rejected on the live transport.

`EXEC` runs a blue-provided argv command or Bash/PowerShell/Python script directly
in the session directory, and starts green AI only with explicit `ai_review=true`.
Bridge preserves exit code and timeout/cancellation facts even if review fails;
commands are never automatically replayed. See the [protocol reference](skills/cross-zone-development/references/protocol.md#direct-commands-and-scripts-exec)
for fields, examples and recovery behavior. Existing `TASK` behavior is unchanged.

Use `run` instead of `open` to resume an existing listener without a new OPEN.
On first use, `run` binds at the current message head and skips historical TASKs;
start it before blue dispatches work.
The explicit-session launcher writes `<plugin-dir>/.cac/bridge-<command>-<session-id>.log`; the agent's bounded
stream output is visible there but remains local to green. Runtime state and
task-owned detached checkouts live under the config directory’s `.state/<session-id>/`.

## Default automatic discovery

One default Bridge waits for blue OPEN in blue's current authorized HAPI session.
Blue sends exactly `{protocol, type, event_id}`, with `protocol: "cross-zone/v3"`
and `type: "OPEN"` or `"CLOSE"`, using CROSS_ZONE framing and a valid event ID.
Blue waits for READY before dispatch; it does not scan other sessions or forge
user messages. Green replies READY, BUSY or CLOSED with exactly `protocol`,
`type`, `event_id`, `request_event_id`, `version`, `session_url` in the receiving
session only. BUSY never discloses the bound session. Connection grants no new
work authority. See the [exact protocol](skills/cross-zone-development/references/protocol.md).

First startup baselines existing heads and ignores old messages. REST scans run
every `poll_seconds` (default 5); bound-session SSE accelerates processing.
Binding, cursors and reply deduplication persist; restart resumes saved execution
state without replay. Competing sessions receive BUSY. CLOSE releases only an
idle binding, with no queued, running, waiting, pending-result or unresolved
recovery work, and green returns CLOSED.

For simultaneous sessions, use independent explicit `open <session-id>` or
`run <session-id>` workers. They retain legacy behavior and do not accept blue
automatic connection envelopes. The watchdog retains its explicit
`watch-bridge.sh <session-id> [config-file]` form as well.

## Legacy green-initiated collaboration

Use the bundled v0.5 green runtime and its untracked `config.local.json`.

Configuration contains no repository path, repository alias, Git remote, or task
binding, profile, allowed-tools list, or custom egress pattern. The launch
directory becomes the workspace. Session ID, session URL, and state
directory are deliberately absent from configuration. Keep `config.local.json`
inside green and never commit it because it contains the HAPI access key.
Removed fields from older configurations are ignored and cannot override the
command-line session or launch workspace.

From the authorized task workspace, run:

```bash
<plugin-dir>/start-bridge.sh open <session-id>
```

The bridge first validates the launch workspace, CLI, and state directory. Only
then does it bind at the current message head, send one green-originated OPEN user message,
and listen for TASK/EXEC/ANSWER/CANCEL. A valid OPEN selects blue without confirmation.
Blue validates OPEN against the current authorized conversation, treats an accepted
OPEN as a fresh connection, and immediately dispatches any clear, authorized
unfinished user request whose next green step is ready. With no such work, blue
replies ready and waits. OPEN alone adds no work authorization, and completed or
still-running actions are not replayed. Rejections use ordinary conversation;
blue never echoes or injects legacy green OPEN. User-requested work defaults to EXEC; TASK is
reserved for local judgment, revision-bound validation or required recovery.
Saved history and recovery safeguards remain in force; `ai_review` defaults
to false; blue opts in when returned information may be restricted.

Blue completes and locally checks each candidate, commits it, and pushes its task
branch to the approved GitHub repository before sending TASK. Green fetches the
exact TASK revision from the launch workspace's existing `origin` and tests it
in an isolated clean checkout. HAPI carries coordination and
reviewed results, including approved short diagnostic snippets. Green does not push diagnostic changes.

Revision is optional. Include it for candidate-code validation as described
above. Omit it for general green-environment work such as querying time, CPU/NPU
state, service health, or other requested diagnostics; those tasks run
in `.state/<session-id>` without Git fetch or checkout.

For a listener without OPEN, run `./start-bridge.sh run <session-id>`. Each
session automatically uses `.state/<session-id>/` and a session-specific log, so
one local configuration can serve multiple concurrent sessions. See
[config.example.json](config.example.json) for a platform-neutral template.

Run the Bridge regression suite from this directory with:

```bash
python -m unittest discover -s tests -v
```

Agent failures use specific safe result reasons. `agent_executable_not_found`
means `agent_command[0]` is missing or not on PATH;
`agent_executable_not_runnable` means the file cannot execute;
`agent_exit_nonzero` reports a nonzero CLI exit; and
`agent_output_protocol_error` means the CLI did not return the required
stream-json structured result. The green-local bridge log includes the exception
type, bounded detail, exit code, and corrective action where applicable.

TASK timeouts must be at least 600 seconds. Use 900 seconds for ordinary code
validation; even small environment checks should receive 600 seconds because the
green CLI may take more than five minutes to initialize and complete.

## Protocol boundaries

TASK/EXEC/ANSWER/CANCEL and ACK/PROGRESS/QUESTION/RESULT/REJECTED use v3
semantics. ACK/PROGRESS use compact task/iteration notifications; immediate
starts omit a pending ACK. Messages use indented JSON code blocks after the
protocol marker; legacy plain JSON and full notifications remain valid.
TASK messages do not carry repository/profile aliases. Results bind
to the exact task, iteration, and HAPI session, and to the
immutable revision when one was supplied. RESULT includes every requested check;
code-validation PASS additionally requires a clean, unmodified baseline.
Agent failures include bounded, redacted diagnostic details for blue.
Missing dependencies or permissions are BLOCKED.
Missing information uses QUESTION, capped at three. Green sets
`egress_reviewed=true` only after excluding credentials, personal or customer
data, request/response bodies, bulk logs, complete source files, diffs, patches,
and code or pseudocode snippets of 10 lines or more. Relevant Markdown fences,
URLs, internal addresses, absolute paths, full stack traces, and shorter code or
pseudocode snippets may cross. The complete structured result is limited to
4096 bytes and `summary` to 3000 characters.

The plugin contains original LingquLab material and is licensed under the
repository MIT license.

### Concurrent execution

`max_concurrent_tasks` defaults to 4 (1–16, green-local); set 1 to restore serial
execution. New EXEC/TASK messages are accepted during running work, and available
slots start independent jobs immediately. Extra jobs queue. Use different task
IDs for independent jobs: another iteration of the same ID waits for its previous
iteration to become terminal before it can be accepted. Cancellation and results
are per task/iteration; result order can differ from submission order. Shutdown
cancels all active jobs, and restart preserves interrupted-job recovery records.

Receipts/captures stay under each task's run directory, and live logs identify the
task. The session cwd and remote resources remain shared; scripts must coordinate
conflicting writes. Candidate Git preparation is serialized, then candidate tests
can overlap. Update local configuration and restart after running work completes.

### EXEC review through an inference API

`ai_review=true` uses one OpenAI-compatible Chat Completions request, without
starting CodeAgent or enabling model tools. Configure `exec_review` in the ignored
`config.local.json`:

```json
"exec_review": {
  "base_url": "http://techdev.hicomputing.huawei.com:18000/v1",
  "model": "Qwen3.8",
  "api_key": "REPLACE_WITH_REVIEW_API_KEY",
  "timeout_seconds": 300
}
```

Review defaults to 300 seconds, bounded by the remaining total task deadline.
Existing local configs with an explicit 60-second timeout keep that value: change
`exec_review.timeout_seconds` to 300 or omit it to use the new default, then restart
the Bridge. For reviewed EXEC, allow the command timeout plus the configured review
budget in the total task timeout.

Replace the placeholder locally; never commit the real key. Existing local configs
need this section before requesting reviewed EXEC. `base_url` is the API prefix;
Bridge appends `/chat/completions`. The specified internal HTTP endpoint is
operator-authorized; keep its deployment inside the authorized network. The API
receives the requested checks, execution facts and the saved receipt/stdout/stderr
contents, not just an already-sanitized summary. Only use an inference endpoint
approved to process that green evidence.

Bridge reads evidence once, with a combined 64 KiB UTF-8 limit, and validates the
model's JSON against the existing result, credential and egress limits. Oversized
or invalid evidence is withheld, never silently truncated. The model cannot run
commands, read other files or change execution facts. A validated internal result
is saved at `runs/<task-id>/<iteration>/execution/review.json`. Logs contain only
review task identity, start/completion and elapsed time, not prompts or responses.

There is one request and no redirects, retries, CLI fallback or command replay.
API failure or invalid/unsafe output produces NEEDS_HUMAN with raw output withheld;
deadline/cancellation retains its terminal status. A request already sent may
finish on the server after cancellation; its late response is discarded and is
never saved or exported. The timeout is bounded by both local configuration and
the remaining task deadline. TASK still uses `agent_command`; direct EXEC
(`ai_review=false`, the default) does not call either reviewer.

### Simple EXEC results without AI review

From 0.5.2, direct EXEC should omit `goal`, `checks` and the redundant default
`ai_review=false`. Retain task binding, execution and both timeout fields. With no
requested checks, RESULT uses `checks: []`; encode required conditions as command
assertions. EXEC rejects goal in both modes; reviewed EXEC requires checks, while
TASK still requires goal/checks. Direct requests can still supply validated checks.
Upgrade green before using this request format.

EXEC defaults to `"ai_review": false`: Bridge returns bounded stdout and exit
status without starting green AI. Blue sets `"ai_review": true` when returned
information may be restricted or needs filtering, especially logs, configuration,
service responses or uncertain output. In direct mode encode all checks as command
assertions. Output/credential limits and recovery rules still apply. See the protocol reference's Optional AI review
contract for exact output limits and failure behavior.

### Chinese console output

Bridge logs and Python subprocess streams use UTF-8, including when redirected
through Git Bash and tee on Windows. Restart Bridge after updating to inherit
these settings. This does not transcode arbitrary native-command output; commands
that use a different encoding must explicitly emit UTF-8. Existing damaged logs
are not repaired by the change.

In an interactive terminal, the launcher colors Bridge log timestamps and levels
cyan. Agent text is green, tool calls/results gray, and Agent stderr yellow;
continuation lines retain their category color. EXEC commands/stdout are gray and
EXEC stderr is red. With `exec_live_log=true` (default), commands are shown at
launch and stdout/stderr are tailed during execution, including partial lines.
Screen refresh and exit-tail display are bounded; dense output shows an omission
marker instead of flooding the terminal or delaying completion. Set it false to
disable EXEC display. Original stdout/stderr remain unchanged in
the execution capture, and only the existing bounded/reviewed result crosses HAPI.
Python child output is unbuffered. Other programs must flush their output; data
captured or redirected inside a script is visible only when that script forwards it.
Log files and redirected output
remain plain text. Task-state PASS is bold green and FAIL bold red.
Set `NO_COLOR=1` to disable color.

### Message history resets

If HAPI resets the message-history epoch/cursor, Bridge automatically rebinds to
the current message head and keeps listening. This also supports deleting local
state while Bridge is stopped and opening again. Rebinding retains existing task
records, receipts, deduplication, recovery state and pending results; active work
is not cancelled and historical commands are not replayed. Instructions not yet
accepted in the reset window may be skipped: the warning asks blue to resend any
unacknowledged instruction. Retrying retains the original task/iteration identity.
Do not delete state while Bridge is running; deleting it removes local execution
history and cannot establish whether an earlier remote action completed.

### Upgrading to 0.6.0 / v3

Upgrade blue and green together. Live v2 envelopes and target fields are no longer
accepted. Legacy green OPEN includes version 0.6.0 and starts a fresh interaction at the current
message head. Blue can dispatch existing authorized work immediately; the Bridge's
retained queue is not automatically resumed. Use run only to
intentionally continue the listener and its queue. EXEC defaults to no AI review;
blue opts in with ai_review=true for possibly restricted output. See the protocol
reference's Upgrading from v2 section for state migration and recovery behavior.
