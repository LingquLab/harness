---
name: ascendc-npu-status
description: Check whether explicitly requested Ascend NPU devices are idle by reading a versioned env_list.json environment inventory and querying per-device process memory locally or over SSH. Use before NPU tests or benchmarks, when selecting free devices across hosts, or when a machine-readable idle, busy, or indeterminate result is required. This is a process-occupancy check, not a device-health diagnosis.
---

# Ascend NPU Status

Keep the check read-only. Treat every failed or unrecognized probe as indeterminate, never as idle.

## Input

Store environment information in an external `env_list.json`; do not embed site-specific hosts in this skill. Use this v1 shape. `defaults.devices` may instead be specified on every environment.

```json
{
  "version": 1,
  "defaults": {
    "user": "root",
    "port": 22,
    "devices": [0, 1, 2, 3, 4, 5, 6, 7],
    "connect_timeout_seconds": 3,
    "probe_timeout_seconds": 10
  },
  "environments": [
    {"name": "primary", "host": "npu-primary.example.com"},
    {"name": "local-subset", "ssh": "local", "devices": [0, 1]},
    {"name": "uri-form", "ssh": "ssh://root@npu-worker.example.com:22", "devices": [4, 5]}
  ]
}
```

For each environment, provide exactly one of `host` or `ssh`. An `ssh` value is either `local` or an `ssh://[user@]host[:port]` URI. Do not put passwords in the JSON. SSH targets use batch authentication, accept a first-seen host key, and reject changed keys. The legacy top-level key `targets` remains accepted as an alias for `environments`.

## Run

Resolve paths relative to this skill directory, then run a one-shot check:

```bash
python '<skill-dir>/scripts/check_npu_status.py' /path/to/env_list.json --pretty
```

The checker starts at most one SSH process per environment and probes the requested devices concurrently inside that environment. It checks up to 16 environments concurrently by default, accepts `--max-workers` values through 64, and preserves input order in the report. On Windows it prefers the system OpenSSH client over Git's bundled client.

Use `-` to read JSON from stdin. Before a test that must wait for resources, poll busy devices every five seconds for at most 120 seconds:

```bash
python '<skill-dir>/scripts/check_npu_status.py' /path/to/env_list.json \
  --wait-timeout 120 --interval 5 --pretty
```

Stop instead of launching the test when the command does not return `0`.

## Interpretation

- Exit `0`: every requested device is `idle`; `safe_to_use` is true.
- Exit `1`: at least one device is `busy`, including a busy wait that timed out.
- Exit `2`: the JSON or command usage is invalid.
- Exit `3`: at least one target or device probe is indeterminate.

The checker preserves environment and device order in its JSON output. It reports process occupancy from `npu-smi info -t proc-mem`; it does not establish NPU health. Use `ascendc-env-check` or `ascendc-runtime-debug` when visibility, health, driver, or runtime evidence is needed.

## Safety

- Query only devices explicitly named in the JSON.
- Do not use an indeterminate device for a workload.
- Do not reset devices, release processes, or terminate workloads as part of this check.
- Keep credentials in SSH configuration or an agent, not in JSON or command output.
