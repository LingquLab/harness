# Cross Zone Development

[中文文档](./README_CN.md)

This Codex and ZCode plugin coordinates blue and green AI agents through HAPI.
A Windows bridge in the green protected-service zone invokes its local Claude
Code-compatible CLI and sends only bounded, reviewed results back to blue. GitHub
Issues and browser automation are not part of the transport.

## Green-initiated collaboration

Use the v0.3 green runtime. Copy [config.windows.json](config.windows.json) to
untracked `config.local.json`, then set the HAPI Hub, access key, and green
repository/profile aliases.

`task_binding` selects the repository and access profile entirely inside green;
blue never supplies or needs these aliases. Session ID, session URL, and state
directory are deliberately absent from configuration. Keep `config.local.json`
inside green and never commit it because it contains the HAPI access key.

From the green Windows runtime directory, run:

```bash
./start-bridge.sh open <session-id>
```

The bridge first validates the local task binding, CLI, and directories. Only
then does it send one green-originated OPEN user message, bind to the session,
and listen for TASK/ANSWER/CANCEL. Blue validates OPEN against the current
authorized conversation. It either sends a formal TASK or explains rejection in
ordinary conversation; it never echoes or injects OPEN.

Blue completes and locally checks each candidate, commits it, and pushes its task
branch to the approved GitHub repository before sending TASK. Green fetches the
exact TASK revision through the `remote` configured in its local repository
binding and tests it in an isolated clean checkout. HAPI carries coordination and
reviewed results, never code. Green does not push diagnostic changes.

For a listener without OPEN, run `./start-bridge.sh run <session-id>`. Each
session automatically uses `.state/<session-id>/` and a session-specific log, so
one local configuration can serve multiple concurrent sessions. See
[config.example.json](config.example.json) for a platform-neutral template.

## Protocol boundaries

TASK/ANSWER/CANCEL and ACK/PROGRESS/QUESTION/RESULT/REJECTED retain their v2
semantics. New TASK messages do not carry repository/profile aliases; v0.3
green runtimes accept legacy alias-bearing TASK messages only within local
authorization. Results bind to the exact task, iteration, target, and immutable
revision. RESULT includes every requested check; PASS requires all checks to pass
on a clean, unmodified baseline. Missing dependencies or permissions are BLOCKED.
Missing information uses QUESTION, capped at three. Green sets
`egress_reviewed=true` only after excluding source, raw logs, credentials,
internal addresses, absolute paths, payloads, and source-bearing artifacts.

The plugin contains original LingquLab material and is licensed under the
repository MIT license.
