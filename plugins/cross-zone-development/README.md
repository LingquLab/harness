# Cross Zone Development

[中文文档](README_CN.md)

Run checks in a protected green environment while continuing development in blue. The plugin connects the two environments through HAPI, executes bounded commands, and returns results under the cross-zone output policy. It supports service diagnostics, environment checks and candidate validation.

## Get started

Install with `codex plugin add cross-zone-development@lingqulab`. In green, prepare Windows with Python 3.11+, Git for Windows and CodeAgentCLI, and copy the plugin to an approved local location. Copy `config.windows.json` to `config.local.json` and configure the HAPI access key; keep this file private.

From the approved green task workspace, start the Bridge:

```bash
<plugin-dir>/start-bridge.sh
```

Then ask the blue agent to connect and run the required check. Independent explicit-session workers are available when multiple sessions are needed. If the default worker is busy, taking it over requires confirmation because existing work will be interrupted.

The [Chinese user guide](USER_GUIDE_CN.md) covers setup and daily use. See [operation details](OPERATIONS.md) for configuration, timeouts, logs, upgrades and recovery, or the [protocol reference](skills/cross-zone-development/references/protocol.md) for message formats.

## Requirements and effects

The Bridge contacts the configured HAPI Hub and, when output review is enabled, the configured inference endpoint. Commands run in the authorized green workspace and may contact the services selected for the task. Local configuration, execution receipts and logs remain in green. Candidate validation can create isolated checkouts; other file changes depend on the dispatched command. Commands are not automatically replayed after interruption, and uncertain effects require recovery checks.

A local Bridge process is required; no Hooks or MCP server is bundled. The plugin is licensed under MIT.
