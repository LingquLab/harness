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

## Direct recovery after review failures

After a terminal review/fallback NEEDS_HUMAN, blue sends a new EXEC with explicit
`ai_review: false` and smaller output. Only read-only or verified repeatable
operations are rerun; operations with side effects use read-only saved-evidence
retrieval. Changing the flag alone does not fix output limits. After two such
failures in the current session, subsequent EXECs stay direct unless the user
requests review again. Identical failing retries, valid negative reviews and
unknown execution effects do not authorize replay. Output ceilings follow the 64 KiB policy below; credential/content guards remain enforced.

## 64 KiB return policy (0.7.2)

Direct EXEC stdout is capped at 65536 UTF-8 bytes (64 KiB). A complete RESULT
has a 73728-byte (72 KiB) serialized JSON ceiling to reserve transport metadata;
summary is capped at 65664 characters to include the direct/fallback labels. JSON
escaping or multibyte text can reach the envelope limit sooner; summarize or
split output rather than repeatedly resending oversized results. Diagnostic
detail stays at 4000 JSON-encoded UTF-8 bytes. Credential/content checks, local
capture/review limits and HAPI client behavior remain unchanged.

Green testing received 8 KiB and 64 KiB synthetic payloads. The 256 KiB RESULT
was rejected with HTTP 403; its exact cause was not established. This release
uses the observed 64 KiB level rather than continuing the unlimited experiment.
