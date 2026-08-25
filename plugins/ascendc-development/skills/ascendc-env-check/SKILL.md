---
name: ascendc-env-check
description: Inspect an Ascend development or runtime host for CANN environment variables, installed version metadata, toolkit and operator paths, diagnostic tools, and NPU visibility. Use for environment checks, npu-smi or asys diagnostics, CANN setup verification, missing-tool investigation, and read-only triage on a local or named remote machine.
---

# Ascend C Environment Check

Keep this skill read-only unless the user separately asks to change the environment.

## Workflow

1. Confirm the target machine. When a remote host is named, run checks on that host rather than assuming local state.
2. Verify identity and scope when permissions matter (`whoami`, `id`, and, only when relevant, `sudo -n true`).
3. Resolve paths relative to this skill directory and run:

```bash
bash '<skill-dir>/scripts/check_env.sh'
bash '<skill-dir>/scripts/npu_info.sh'
```

4. `check_env.sh` invokes the pure-read metadata inspector for a discovered toolkit. For stable JSON, or to correlate an already captured named SoC field with toolkit configuration, run it directly:

```bash
python3 '<skill-dir>/scripts/inspect_cann_state.py' \
  --toolkit-root '<selected-toolkit-root>' --json
python3 '<skill-dir>/scripts/inspect_cann_state.py' \
  --toolkit-root '<selected-toolkit-root>' \
  --npu-capture '<bounded-capture-file>' --json
```

The helper never executes a device command. `--soc` is user-supplied toolkit metadata evidence and `--build-target` is build evidence; neither is detected hardware. A `runtime_soc_correlated` result means an explicit runtime SoC claim exactly matched one installed platform configuration with one `NpuArch` value. It is not a hard-coded product map.

An explicitly supplied capture that is missing, unreadable, not a regular file, over 256 KiB, or deeper than 64 JSON container levels fails with `invalid_npu_capture`. A bounded but unrecognized JSON/text schema remains read-only evidence with `npu_capture.status=unrecognized` and a warning; it produces no inferred hardware claim.

5. If a script is unavailable or its output format is not recognized, fall back to the commands in `references/npu_commands.md` and `references/asys_commands.md`.
6. Correlate environment variables with discovered toolkit roots, tool locations, real paths, component metadata, and requirement fields. A missing `ASCEND_HOME_PATH` means the current shell is not configured; it does not prove that CANN is absent.
7. Interpret `[error]` as an invalid active configuration, `[warn]` as missing or incomplete development evidence, and `[info]` as optional or discovered state. Warnings do not change the script's zero exit status; errors do.
8. Preserve the raw bounded device output from `npu_info.sh`. Do not infer card count, health, or identifier semantics by parsing one assumed table layout.
9. Keep host discovery, metadata correlation, compile proof, and real-hardware runtime proof as separate conclusions.

## Reference Routing

- Environment variables and version metadata: `references/env_config_guide.md`
- NPU commands: `references/npu_commands.md`
- `asys` fallback: `references/asys_commands.md`
- Symptom-based diagnosis: `references/troubleshooting.md`

## Safety

- Do not install packages, source user profiles permanently, modify shell startup files, reset devices, or terminate workloads during an environment check.
- Avoid interactive monitors such as `npu-smi top` in automation; use bounded status commands.
- Do not infer device availability from command presence alone. Capture command exit status and the bounded raw device output.
- Do not infer SoC-to-NpuArch relationships from a fixed product table or substring. Report unknown or ambiguous evidence instead.
- Redact tokens, credentials, and unrelated environment variables.

## Output

State the target host and user, selected or discovered toolkit root, toolkit release claims, per-component version/provenance and requirement fields, driver evidence, SoC/NpuArch evidence state, operator repository evidence, NPU visibility, and the exact failing boundary. Version-text equality is not compatibility proof. Distinguish an installed toolkit from an environment loaded in the current shell. Give the next diagnostic or setup action without performing a mutation unless requested.
