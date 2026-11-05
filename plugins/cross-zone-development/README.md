# Experimental unlimited-output build: 0.7.2-dev.1

This branch is for measuring green-to-HAPI EXEC return capacity, based on 0.7.1.
It removes Bridge ceilings for direct stdout, summary, RESULT JSON, diagnostic
length, EXEC local capture, and review evidence/HTTP response length. The review
request no longer specifies max_tokens. HAPI, proxies, model services, memory,
timeouts and cancellation still determine the actual transport maximum. UTF-8,
control-character, stderr, credential and semantic result checks remain active.
TASK agent local capture retains its existing limit; this experiment targets EXEC.

For a capacity probe use ai_review=false and deterministic synthetic ASCII or
Chinese output, increasing its UTF-8 byte count per terminal iteration. Compare
the received payload's length/hash with the expected payload, not just PASS.
Do not retry an uncertain in-flight request or repeat operations with side effects.
No live green capacity result is claimed by the local test suite.

The normal-release numeric ceilings in the documents below describe 0.7.1 and
are disabled by this experimental build for the channels listed above.

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

## Direct recovery after review failures (0.7.1)

After a terminal review/fallback NEEDS_HUMAN, blue sends a new EXEC with explicit
`ai_review: false` and smaller output. Only read-only or verified repeatable
operations are rerun; operations with side effects use read-only saved-evidence
retrieval. Changing the flag alone does not fix output limits. After two such
failures in the current session, subsequent EXECs stay direct unless the user
requests review again. Identical failing retries, valid negative reviews and
unknown execution effects do not authorize replay. Direct stdout is now limited
to 4000 UTF-8 bytes, summary to 6000 characters and RESULT to 8192 UTF-8 bytes;
credential/content guards remain enforced. Diagnostic detail is capped at 4000
JSON-encoded UTF-8 bytes.
