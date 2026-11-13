# Session scripts (Bridge 0.8.0)

Use session scripts for reusable code rather than repeating long inline EXEC scripts.
READY/legacy OPEN advertise `exec.git-session.v1`
in `capabilities`. Send new forms only after the matching capability is present.
The outer EXEC fields, CROSS_ZONE marker, identity, positive integer execution timeout,
cancellation, and no-replay rules remain unchanged. Git EXEC uses the same optional ai_review setting as inline EXEC.
Only inline commands and Git scripts are supported; local named-script management is removed.

## Git scripts: session branch, pinned commit

Repository is fixed: https://github.com/LingquLab/CrossZoneScript.
For any operation in `LingquLab/CrossZoneScript` (including creating/editing
scripts, checks, Git commits/pushes and recovery), do not load or invoke any
superpowers-neo/superpower-neo skills. Use this workflow directly. Still run
appropriate syntax/content checks before delivery; do not add a separate skill
reading or approval sequence for these repository operations.

Before the first commit in every clone or temporary repository, configure the
Codex automation identity locally, without waiting for a missing-author error:

```bash
git config --local user.name "Codex"
git config --local user.email "codex@openai.com"
```

Run these commands in the CrossZoneScript repository. Do not change global Git
identity or other repositories. The identity is commit authorship metadata;
continue using the environment's existing GitHub authentication for pushes.

Branch name is exactly the bound HAPI session UUID. Blue commits and pushes
changes there, then sends:

```json
{"git":"session","commit":"<40 lowercase hex>","entry":"ubx/packet_fixture_repair.py","args":{"packet_lanes":3}}
```

There is no repository URL or branch selector in EXEC. Green fetches its session
branch, verifies commit reachability, and executes a snapshot of that exact commit,
not the moving branch head. Entry is a relative .py/.sh/.ps1 script path; no
manifest required. Other regular files are included for imports/resources. Symlinks
and submodules are rejected. No automatic dependency install or shell expansion.
Split nested remote scripts into separate files to avoid repeated string escaping.
No push, local-source modification or cross-session branch lookup is performed
by green. Blue changes Git scripts by committing/pushing a new commit.

The script source identity (entry, SHA256, commit when applicable) is saved as
`script-source.json` beside the execution receipt. Each task has an independent
snapshot. Preparation observes cancellation; Git fetch has a 120-second timeout. Command and review budgets start independently.
Git errors return `SCRIPT_GIT_FAILED` with the failing stage; no Git stderr or
credentials are exported, and no alternative version is executed.

## Results

Normal script execution uses the existing EXEC RESULT path and direct-output
rules. Return short JSON summaries on stdout, detailed logs in the task directory.
Internal BLOCKED/FAIL must exit nonzero; a JSON status alone does not override an
exit-zero command. Git preparation failures return REJECTED with an explicit error_code and detail.

Keep event IDs unique. Do not replay non-idempotent work after unknown effects.
Existing argv and interpreter+script EXEC remain supported.

Direct-output rejection detail reports the observed condition(s): stdout byte count
and limit, nonempty stderr byte count, invalid UTF-8 byte offset, control-character
code point/offset, or capture-read error class/errno. It never substitutes a list
of possible causes or exports raw stderr.
