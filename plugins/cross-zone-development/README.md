# Cross Zone Development

[中文文档](./README_CN.md)

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
`config.local.json` and set `hub_url` and `access_key`. Start it from the
directory green authorizes as the task workspace:

```bash
<plugin-dir>/start-bridge.sh doctor <session-id>
<plugin-dir>/start-bridge.sh open <session-id>
```

Use `run` instead of `open` to resume an existing listener without a new OPEN.
On first use, `run` binds at the current message head and skips historical TASKs;
start it before blue dispatches work.
The launcher writes `<plugin-dir>/.cac/bridge-<command>-<session-id>.log`; the agent's bounded
stream output is visible there but remains local to green. Runtime state and
task-owned detached checkouts live under the config directory’s `.state/<session-id>/`.

## Green-initiated collaboration

Use the bundled v0.4 green runtime and its untracked `config.local.json`.

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
and listen for TASK/ANSWER/CANCEL. A valid OPEN selects blue without confirmation.
Blue validates OPEN against the current authorized conversation. It either sends a formal TASK or explains rejection in
ordinary conversation; it never echoes or injects OPEN.

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

TASK/ANSWER/CANCEL and ACK/PROGRESS/QUESTION/RESULT/REJECTED retain their v2
semantics. ACK/PROGRESS use compact task/iteration notifications; immediate
starts omit a pending ACK. Messages use indented JSON code blocks after the
protocol marker; legacy plain JSON and full notifications remain valid.
TASK messages do not carry repository/profile aliases. Results bind
to the exact task, iteration, and target, and to the
immutable revision when one was supplied. RESULT includes every requested check;
code-validation PASS additionally requires a clean, unmodified baseline.
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
