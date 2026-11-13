# Session scripts (Bridge 0.8.0)

Use session scripts for reusable code rather than repeating long inline EXEC scripts.
READY/legacy OPEN advertise `exec.session-script.v1` and `exec.git-session.v1`
in `capabilities`. Send new forms only after the matching capability is present.
The outer EXEC fields, CROSS_ZONE marker, identity, positive integer timeouts,
cancellation, and no-replay rules remain unchanged. Keep `ai_review:false` for
script-management operations; their explicit script feedback does not run AI review.

## Named scripts: create, read, modify, execute

Files live in the bound session's `state_dir/scripts`. No registry, manifest,
installation config or global script names. Use a single filename with .py,
.sh or .ps1; the suffix selects Python, Bash or PowerShell. Names cannot contain
paths. Scripts shared across sessions must be explicitly installed in each.

Each example below is the `execution` object of a normal EXEC:

```json
{"script_update":"check.py","sha256":null,"content":"print('OK')\n"}
```

Null hash creates a missing script only. Success returns `SCRIPT_RESULT` with
name, SHA256 and updated=true. For an existing script, specify its current hash:

```json
{"script_update":"check.py","sha256":"<64 lowercase hex>","replacements":[{"old":"'OK'","new":"'READY'"}]}
```

Use either full `content` or nonempty `replacements`, never both. Replacements
are exact, case-sensitive and applied sequentially; each old string must occur
exactly once. All replacements are checked before the file is atomically replaced.
A replacement failure returns the unchanged full script and hash. No implicit retry.

```json
{"script_read":"check.py"}
```

Read returns `SCRIPT_RESULT` with the complete UTF-8 content and SHA256.
Hashes always cover the exact stored UTF-8 bytes, including line endings.

```json
{"script":"check.py","sha256":"<64 lowercase hex>","args":{"value":"OK"}}
```

Execute checks the hash, snapshots the script, writes args.json, and invokes
`<interpreter> <script> --args-file <absolute args.json>`. Parse that option in
your script. cwd stays the green task workspace; use the script's own location
for resource paths. No parameters are interpolated into shell source.

On hash mismatch, return `REJECTED`, `error_code:SCRIPT_HASH_MISMATCH`, name,
**complete current script content** and actual SHA256. Do not truncate it through
ordinary stdout limits. Blue can read/patch/replace against this current hash.
If absent, return null content/hash and an explicit error. Script content is an
explicitly requested export: never install credentials in these scripts.

Control replies include task_id and iteration; they are terminal for that EXEC.
Use the next iteration/new task for the next operation. Update/read do not execute
the script. A repeated task identity never edits or executes again. Controls are
saved in the execution receipt and delivered through the durable outbox. Cancelling
after an edit does not undo the edit; inspect current content before continuing.

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
by green. Blue changes Git scripts by committing/pushing a new commit. Named-script
update modifies session-local scripts only, never Git history.

The script source identity (entry, SHA256, commit when applicable) is saved as
`script-source.json` beside the execution receipt. Each task has an independent
snapshot. Preparation is inside the task deadline and observes cancellation.
Git errors return `SCRIPT_GIT_FAILED` with the failing stage; no Git stderr or
credentials are exported, and no alternative version is executed.

## Results

Normal script execution uses the existing EXEC RESULT path and direct-output
rules. Return short JSON summaries on stdout, detailed logs in the task directory.
Internal BLOCKED/FAIL must exit nonzero; a JSON status alone does not override an
exit-zero command. Script-management replies use SCRIPT_RESULT for success and
REJECTED for failure, with error_code and script-specific payload. They export
script content only on read or conflict, not arbitrary execution stdout/stderr.

Keep event IDs unique. Do not replay non-idempotent work after unknown effects.
Existing argv and interpreter+script EXEC remain supported.

Direct-output rejection detail reports the observed condition(s): stdout byte count
and limit, nonempty stderr byte count, invalid UTF-8 byte offset, control-character
code point/offset, or capture-read error class/errno. It never substitutes a list
of possible causes or exports raw stderr.
