#!/usr/bin/env python3
"""Read-only, JSON-driven Ascend NPU process occupancy check."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import datetime as dt
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from typing import Any


SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 1_048_576
MAX_TARGETS = 256
MAX_DEVICES_PER_TARGET = 64
MAX_TOTAL_DEVICES = 1024
MAX_ERROR_CHARS = 1000
DEFAULT_MAX_WORKERS = 16
DEFAULT_CONNECT_TIMEOUT = 3
DEFAULT_PROBE_TIMEOUT = 10.0

REMOTE_PROBE = r'''set -u

probe_dir=$(mktemp -d "${TMPDIR:-/tmp}/ascend-npu-status.XXXXXX") || exit 70
cleanup_probe() {
    rm -f -- "${probe_dir}"/* 2>/dev/null || true
    rmdir -- "${probe_dir}" 2>/dev/null || true
}
trap cleanup_probe EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! command -v npu-smi >/dev/null 2>&1; then
    printf '__probe_error__\tnpu_smi_not_found\n'
    for device in "$@"; do
        printf '%s\t?\n' "${device}"
    done
    exit 0
fi
if ! command -v timeout >/dev/null 2>&1; then
    printf '__probe_error__\ttimeout_not_found\n'
    for device in "$@"; do
        printf '%s\t?\n' "${device}"
    done
    exit 0
fi

pids=()
for device in "$@"; do
    LC_ALL=C timeout 5 npu-smi info -t proc-mem -i "${device}" \
        >"${probe_dir}/${device}.out" 2>/dev/null &
    pids[device]=$!
done

for device in "$@"; do
    state='?'
    if wait "${pids[device]}"; then
        if grep -q 'Process id[[:space:]]*:' "${probe_dir}/${device}.out"; then
            state='1'
        elif grep -Eq "NPU ID[[:space:]]*:[[:space:]]*${device}([[:space:]]|$)" \
                "${probe_dir}/${device}.out"; then
            state='0'
        fi
    fi
    printf '%s\t%s\n' "${device}" "${state}"
done
'''


class ConfigError(ValueError):
    """Raised when the input JSON does not satisfy the v1 schema."""


@dataclasses.dataclass(frozen=True)
class Target:
    name: str
    host: str | None
    user: str | None
    port: int | None
    devices: tuple[int, ...]
    connect_timeout: int
    probe_timeout: float

    @property
    def is_local(self) -> bool:
        return self.host is None

    @property
    def endpoint(self) -> str:
        if self.is_local:
            return "local"
        host = f"[{self.host}]" if ":" in self.host else self.host
        authority = f"{self.user}@" if self.user else ""
        return f"ssh://{authority}{host}:{self.port}"


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be an object")
    return value


def _reject_unknown_keys(value: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ConfigError(f"{path} contains unknown field(s): {', '.join(unknown)}")


def _integer(value: Any, path: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path} must be an integer")
    if not minimum <= value <= maximum:
        raise ConfigError(f"{path} must be between {minimum} and {maximum}")
    return value


def _number(value: Any, path: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ConfigError(f"{path} must be between {minimum:g} and {maximum:g}")
    return result


def _devices(value: Any, path: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"{path} must be a non-empty array")
    if len(value) > MAX_DEVICES_PER_TARGET:
        raise ConfigError(f"{path} exceeds {MAX_DEVICES_PER_TARGET} devices")
    devices = tuple(
        _integer(device, f"{path}[{index}]", 0, 255)
        for index, device in enumerate(value)
    )
    if len(set(devices)) != len(devices):
        raise ConfigError(f"{path} contains duplicate device IDs")
    return devices


def _user(value: Any, path: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ConfigError(f"{path} is not a valid SSH user")
    return value


def _host(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", value)
        or value.endswith(":")
    ):
        raise ConfigError(f"{path} is not a valid host name or address")
    return value


def _name(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 128
        or any(ord(character) < 32 for character in value)
    ):
        raise ConfigError(f"{path} must be a non-empty label of at most 128 characters")
    return value


def _parse_ssh_uri(value: Any, path: str) -> tuple[str | None, str | None, int | None]:
    if value == "local":
        return None, None, None
    if not isinstance(value, str):
        raise ConfigError(f"{path} must be 'local' or an ssh:// URI")
    try:
        parsed = urllib.parse.urlsplit(value)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
        port = parsed.port
    except ValueError as error:
        raise ConfigError(f"{path} is not a valid SSH URI") from error
    if (
        parsed.scheme != "ssh"
        or not hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
        or password is not None
    ):
        raise ConfigError(f"{path} must be an ssh://[user@]host[:port] URI without a password")
    return (
        _host(hostname, f"{path} host"),
        _user(username, f"{path} user") if username else None,
        _integer(port, f"{path} port", 1, 65535) if port is not None else None,
    )


def parse_config_data(data: Any) -> list[Target]:
    root = _require_object(data, "input")
    _reject_unknown_keys(root, {"version", "defaults", "environments", "targets"}, "input")
    _integer(root.get("version"), "input.version", SCHEMA_VERSION, SCHEMA_VERSION)

    defaults = _require_object(root.get("defaults", {}), "input.defaults")
    _reject_unknown_keys(
        defaults,
        {"user", "port", "devices", "connect_timeout_seconds", "probe_timeout_seconds"},
        "input.defaults",
    )
    default_user = _user(defaults["user"], "input.defaults.user") if "user" in defaults else None
    default_port = _integer(defaults.get("port", 22), "input.defaults.port", 1, 65535)
    default_devices = (
        _devices(defaults["devices"], "input.defaults.devices")
        if "devices" in defaults
        else None
    )
    default_connect_timeout = _integer(
        defaults.get("connect_timeout_seconds", DEFAULT_CONNECT_TIMEOUT),
        "input.defaults.connect_timeout_seconds",
        1,
        60,
    )
    default_probe_timeout = _number(
        defaults.get("probe_timeout_seconds", DEFAULT_PROBE_TIMEOUT),
        "input.defaults.probe_timeout_seconds",
        1,
        120,
    )

    collection_names = [name for name in ("environments", "targets") if name in root]
    if len(collection_names) != 1:
        raise ConfigError("input must contain exactly one of environments or targets")
    collection_name = collection_names[0]
    target_values = root[collection_name]
    if not isinstance(target_values, list) or not target_values:
        raise ConfigError(f"input.{collection_name} must be a non-empty array")
    if len(target_values) > MAX_TARGETS:
        raise ConfigError(f"input.{collection_name} exceeds {MAX_TARGETS} environments")

    targets: list[Target] = []
    seen_names: set[str] = set()
    allowed = {
        "name",
        "ssh",
        "host",
        "user",
        "port",
        "devices",
        "connect_timeout_seconds",
        "probe_timeout_seconds",
    }
    for index, raw_target in enumerate(target_values):
        path = f"input.{collection_name}[{index}]"
        target = _require_object(raw_target, path)
        _reject_unknown_keys(target, allowed, path)
        if ("ssh" in target) == ("host" in target):
            raise ConfigError(f"{path} must contain exactly one of ssh or host")

        if "ssh" in target:
            host, uri_user, uri_port = _parse_ssh_uri(target["ssh"], f"{path}.ssh")
            if host is None and any(key in target for key in ("user", "port")):
                raise ConfigError(f"{path} cannot set user or port for a local target")
            if host is not None and "user" in target and uri_user is not None:
                raise ConfigError(f"{path} cannot set user both in ssh and as a field")
            if host is not None and "port" in target and uri_port is not None:
                raise ConfigError(f"{path} cannot set port both in ssh and as a field")
            if host is None:
                user = None
                port = None
            else:
                user = (
                    _user(target["user"], f"{path}.user")
                    if "user" in target
                    else uri_user or default_user
                )
                port = (
                    _integer(target["port"], f"{path}.port", 1, 65535)
                    if "port" in target
                    else uri_port or default_port
                )
        else:
            host = _host(target["host"], f"{path}.host")
            user = _user(target["user"], f"{path}.user") if "user" in target else default_user
            port = (
                _integer(target["port"], f"{path}.port", 1, 65535)
                if "port" in target
                else default_port
            )

        devices = (
            _devices(target["devices"], f"{path}.devices")
            if "devices" in target
            else default_devices
        )
        if devices is None:
            raise ConfigError(f"{path}.devices is required when input.defaults.devices is absent")
        label_default = "local" if host is None else host
        name = _name(target.get("name", label_default), f"{path}.name")
        if name in seen_names:
            raise ConfigError(f"{path}.name duplicates another target: {name}")
        seen_names.add(name)

        targets.append(
            Target(
                name=name,
                host=host,
                user=user,
                port=port,
                devices=devices,
                connect_timeout=_integer(
                    target.get("connect_timeout_seconds", default_connect_timeout),
                    f"{path}.connect_timeout_seconds",
                    1,
                    60,
                ),
                probe_timeout=_number(
                    target.get("probe_timeout_seconds", default_probe_timeout),
                    f"{path}.probe_timeout_seconds",
                    1,
                    120,
                ),
            )
        )
    total_devices = sum(len(target.devices) for target in targets)
    if total_devices > MAX_TOTAL_DEVICES:
        raise ConfigError(f"input requests {total_devices} devices; maximum is {MAX_TOTAL_DEVICES}")
    return targets


def load_config(source: str) -> list[Target]:
    try:
        if source == "-":
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        else:
            path = pathlib.Path(source)
            if not path.is_file():
                raise ConfigError(f"input file is missing or not a regular file: {source}")
            if path.stat().st_size > MAX_INPUT_BYTES:
                raise ConfigError(f"input exceeds {MAX_INPUT_BYTES} bytes")
            raw = path.read_bytes()
    except OSError as error:
        raise ConfigError(f"cannot read input: {error}") from error
    if len(raw) > MAX_INPUT_BYTES:
        raise ConfigError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    try:
        return parse_config_data(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConfigError(f"input is not valid UTF-8 JSON: {error}") from error


def _one_line(value: str) -> str:
    return " ".join(value.split())[:MAX_ERROR_CHARS]


def _resolve_ssh_path() -> str:
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        if system_root:
            system_ssh = pathlib.Path(system_root) / "System32" / "OpenSSH" / "ssh.exe"
            if system_ssh.is_file():
                return str(system_ssh)
    return shutil.which("ssh") or "ssh"


def _unknown_devices(
    target: Target, reason: str = "target_probe_failed"
) -> list[dict[str, Any]]:
    return [
        {"id": device, "state": "unknown", "reason": reason}
        for device in target.devices
    ]


def _parse_probe_output(
    output: str, target: Target
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    states: dict[int, str] = {}
    protocol_error: dict[str, str] | None = None
    requested = set(target.devices)
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) != 2:
            protocol_error = {"code": "invalid_probe_output", "message": "malformed probe line"}
            continue
        identifier, state = fields
        if identifier == "__probe_error__":
            protocol_error = {"code": state, "message": "remote probe prerequisite failed"}
            continue
        if not identifier.isdigit() or int(identifier) not in requested or state not in {"0", "1", "?"}:
            protocol_error = {"code": "invalid_probe_output", "message": "unexpected probe value"}
            continue
        device = int(identifier)
        if device in states:
            protocol_error = {"code": "invalid_probe_output", "message": "duplicate device result"}
            continue
        states[device] = state

    if protocol_error:
        return _unknown_devices(target, protocol_error["code"]), protocol_error

    devices: list[dict[str, Any]] = []
    for device in target.devices:
        state = states.get(device, "?")
        item: dict[str, Any] = {
            "id": device,
            "state": {"0": "idle", "1": "busy", "?": "unknown"}[state],
        }
        if state == "?":
            item["reason"] = (
                protocol_error["code"] if protocol_error else "npu_smi_failed_or_unrecognized"
            )
        devices.append(item)
    if any(device["state"] == "unknown" for device in devices) and protocol_error is None:
        protocol_error = {
            "code": "device_probe_failed",
            "message": "one or more npu-smi results failed or were unrecognized",
        }
    return devices, protocol_error


def _target_status(devices: list[dict[str, Any]]) -> str:
    states = {device["state"] for device in devices}
    if "unknown" in states:
        return "indeterminate"
    if "busy" in states:
        return "busy"
    return "idle"


def probe_target(target: Target, timeout_limit: float | None = None) -> dict[str, Any]:
    started = time.perf_counter()

    def finish(result: dict[str, Any]) -> dict[str, Any]:
        result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        return result

    if timeout_limit is not None and timeout_limit <= 0:
        return finish({
            "name": target.name,
            "endpoint": target.endpoint,
            "status": "indeterminate",
            "devices": _unknown_devices(target, "wait_deadline_expired"),
            "error": {
                "code": "wait_deadline_expired",
                "message": "wait deadline expired before target probe started",
            },
        })
    device_arguments = [str(device) for device in target.devices]
    if target.is_local:
        command = [shutil.which("bash") or "bash", "-s", "--", *device_arguments]
    else:
        host = f"[{target.host}]" if ":" in target.host else target.host
        destination = f"{target.user}@{host}" if target.user else host
        command = [
            _resolve_ssh_path(),
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={target.connect_timeout}",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "UpdateHostKeys=no",
            "-o",
            "LogLevel=ERROR",
            "-p",
            str(target.port),
            destination,
            "bash",
            "-s",
            "--",
            *device_arguments,
        ]
    probe_timeout = target.probe_timeout
    if timeout_limit is not None:
        probe_timeout = min(probe_timeout, timeout_limit)
    try:
        completed = subprocess.run(
            command,
            input=REMOTE_PROBE.encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=probe_timeout,
        )
    except subprocess.TimeoutExpired:
        return finish({
            "name": target.name,
            "endpoint": target.endpoint,
            "status": "indeterminate",
            "devices": _unknown_devices(target),
            "error": {"code": "probe_timeout", "message": "target probe timed out"},
        })
    except OSError as error:
        return finish({
            "name": target.name,
            "endpoint": target.endpoint,
            "status": "indeterminate",
            "devices": _unknown_devices(target),
            "error": {"code": "probe_start_failed", "message": _one_line(str(error))},
        })

    if completed.returncode != 0:
        code = "local_probe_failed" if target.is_local else "ssh_probe_failed"
        stderr = completed.stderr.decode("utf-8", errors="replace")
        message = _one_line(stderr) or f"probe exited with status {completed.returncode}"
        return finish({
            "name": target.name,
            "endpoint": target.endpoint,
            "status": "indeterminate",
            "devices": _unknown_devices(target),
            "error": {"code": code, "message": message},
        })

    stdout = completed.stdout.decode("utf-8", errors="replace")
    devices, error = _parse_probe_output(stdout, target)
    result: dict[str, Any] = {
        "name": target.name,
        "endpoint": target.endpoint,
        "status": _target_status(devices),
        "devices": devices,
    }
    if error:
        result["error"] = error
    return finish(result)


def check_targets(
    targets: list[Target], max_workers: int, timeout_limit: float | None = None
) -> dict[str, Any]:
    workers = min(max_workers, len(targets))
    deadline = time.monotonic() + timeout_limit if timeout_limit is not None else None

    def probe_with_deadline(target: Target) -> dict[str, Any]:
        remaining = None if deadline is None else deadline - time.monotonic()
        return probe_target(target, remaining)

    ordered_results: list[dict[str, Any] | None] = [None] * len(targets)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        pending = {
            executor.submit(probe_with_deadline, target): index
            for index, target in enumerate(targets)
        }
        for future in concurrent.futures.as_completed(pending):
            ordered_results[pending[future]] = future.result()
    results = [result for result in ordered_results if result is not None]
    counts = {"idle": 0, "busy": 0, "unknown": 0}
    for target in results:
        for device in target["devices"]:
            counts[device["state"]] += 1
    if counts["unknown"]:
        status = "indeterminate"
    elif counts["busy"]:
        status = "busy"
    else:
        status = "idle"
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "safe_to_use": status == "idle",
        "summary": {
            "environments": len(results),
            "devices": sum(counts.values()),
            **counts,
        },
        "environments": results,
    }


def _cli_number(value: str, name: str, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"{name} must be a number") from error
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise argparse.ArgumentTypeError(f"{name} must be between {minimum:g} and {maximum:g}")
    return result


def _cli_integer(value: str, name: str, minimum: int, maximum: int) -> int:
    if not re.fullmatch(r"[0-9]+", value):
        raise argparse.ArgumentTypeError(f"{name} must be an integer")
    result = int(value)
    if not minimum <= result <= maximum:
        raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check JSON-selected Ascend NPUs for active processes."
    )
    parser.add_argument("env_list_json", help="v1 env_list.json file, or - for stdin")
    parser.add_argument(
        "--wait-timeout",
        type=lambda value: _cli_number(value, "wait timeout", 0, 3600),
        default=0.0,
        metavar="SECONDS",
        help="retry busy results until this deadline (default: one shot)",
    )
    parser.add_argument(
        "--interval",
        type=lambda value: _cli_number(value, "interval", 0.1, 60),
        default=5.0,
        metavar="SECONDS",
        help="delay between busy-result retries (default: 5)",
    )
    parser.add_argument(
        "--max-workers",
        type=lambda value: _cli_integer(value, "max workers", 1, 64),
        default=DEFAULT_MAX_WORKERS,
        metavar="COUNT",
        help="maximum concurrent target probes (default: 16)",
    )
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    return parser


def main(arguments: list[str] | None = None) -> int:
    args = build_parser().parse_args(arguments)
    try:
        targets = load_config(args.env_list_json)
    except ConfigError as error:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "status": "invalid_input",
                    "safe_to_use": False,
                    "error": {"code": "invalid_input", "message": str(error)},
                },
                indent=2 if args.pretty else None,
            )
        )
        return 2

    started = time.monotonic()
    deadline = started + args.wait_timeout if args.wait_timeout > 0 else None
    attempts = 0
    while True:
        remaining = None if deadline is None else deadline - time.monotonic()
        if remaining is not None and remaining <= 0 and attempts:
            break
        attempts += 1
        result = check_targets(targets, args.max_workers, remaining)
        elapsed = time.monotonic() - started
        if result["status"] != "busy" or deadline is None:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))

    elapsed = time.monotonic() - started
    result["wait"] = {
        "enabled": args.wait_timeout > 0,
        "attempts": attempts,
        "elapsed_seconds": round(elapsed, 3),
        "timeout_seconds": args.wait_timeout,
        "timed_out": (
            result["status"] == "busy"
            and args.wait_timeout > 0
            and elapsed >= args.wait_timeout
        ),
    }
    print(json.dumps(result, indent=2 if args.pretty else None))
    return {"idle": 0, "busy": 1, "indeterminate": 3}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
