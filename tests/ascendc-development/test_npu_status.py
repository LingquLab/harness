#!/usr/bin/env python3
"""Offline regression tests for the JSON-driven NPU occupancy checker."""

from __future__ import annotations

import importlib.util
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "plugins/ascendc-development/skills/ascendc-npu-status/scripts/check_npu_status.py"
)
SPEC = importlib.util.spec_from_file_location("check_npu_status", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class NpuStatusTest(unittest.TestCase):
    def test_parses_remote_uri_host_defaults_and_local_target(self) -> None:
        targets = MODULE.parse_config_data(
            {
                "version": 1,
                "defaults": {
                    "user": "root",
                    "port": 2222,
                    "devices": [0, 3],
                    "connect_timeout_seconds": 4,
                    "probe_timeout_seconds": 9,
                },
                "environments": [
                    {"name": "uri", "ssh": "ssh://worker@example.test:2200"},
                    {"name": "host", "ssh": "ssh://192.0.2.4", "devices": [1]},
                    {"name": "local", "ssh": "local"},
                ],
            }
        )

        self.assertEqual(targets[0].endpoint, "ssh://worker@example.test:2200")
        self.assertEqual(targets[0].devices, (0, 3))
        self.assertEqual(targets[1].endpoint, "ssh://root@192.0.2.4:2222")
        self.assertEqual(targets[1].devices, (1,))
        self.assertTrue(targets[2].is_local)
        self.assertIsNone(targets[2].user)
        self.assertIsNone(targets[2].port)

    def test_accepts_legacy_targets_alias(self) -> None:
        targets = MODULE.parse_config_data(
            {"version": 1, "targets": [{"host": "example.test", "devices": [0]}]}
        )

        self.assertEqual(targets[0].name, "example.test")

    def test_loads_environment_inventory_from_env_list_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            env_list = pathlib.Path(temporary) / "env_list.json"
            env_list.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "environments": [
                            {"name": "primary", "host": "npu.example.test", "devices": [0, 1]}
                        ],
                    }
                ),
                encoding="utf-8",
            )

            targets = MODULE.load_config(str(env_list))

        self.assertEqual(targets[0].name, "primary")
        self.assertEqual(targets[0].devices, (0, 1))

    def test_rejects_credentials_duplicate_devices_and_unknown_fields(self) -> None:
        invalid_targets = [
            {"ssh": "ssh://user:secret@example.test", "devices": [0]},
            {"host": "example.test", "devices": [0, 0]},
            {"host": "example.test", "devices": [0], "password": "secret"},
        ]
        for target in invalid_targets:
            with self.subTest(target=target), self.assertRaises(MODULE.ConfigError):
                MODULE.parse_config_data({"version": 1, "targets": [target]})

        with self.assertRaises(MODULE.ConfigError):
            MODULE.parse_config_data(
                {"version": True, "targets": [{"host": "example.test", "devices": [0]}]}
            )

    def test_rejects_malformed_ssh_uri_as_config_error(self) -> None:
        with self.assertRaises(MODULE.ConfigError):
            MODULE.parse_config_data(
                {"version": 1, "environments": [{"ssh": "ssh://[", "devices": [0]}]}
            )

    def test_rejects_excessive_total_device_fanout(self) -> None:
        environments = [
            {"name": f"node-{index}", "host": f"node-{index}.example.test", "devices": list(range(64))}
            for index in range(17)
        ]

        with self.assertRaisesRegex(MODULE.ConfigError, "maximum is 1024"):
            MODULE.parse_config_data({"version": 1, "environments": environments})

    def test_remote_probe_classifies_idle_busy_and_unknown(self) -> None:
        fake_commands = r'''
timeout() {
    shift
    "$@"
}
npu-smi() {
    local device="${@: -1}"
    case "${device}" in
        0) printf 'NPU ID : 0\n' ;;
        1) printf 'NPU ID : 1\nProcess id : 1234\n' ;;
        2) printf 'unrecognized output\n' ;;
        *) return 1 ;;
    esac
}
'''
        completed = subprocess.run(
            ["bash", "-s", "--", "0", "1", "2", "3"],
            input=fake_commands + MODULE.REMOTE_PROBE,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.splitlines(), ["0\t0", "1\t1", "2\t?", "3\t?"])

    def test_invalid_probe_protocol_cannot_report_idle(self) -> None:
        target = MODULE.Target("node", "example.test", "root", 22, (0,), 3, 10)

        devices, error = MODULE._parse_probe_output("login banner\n0\t0\n", target)

        self.assertEqual(devices, [{"id": 0, "state": "unknown", "reason": "invalid_probe_output"}])
        self.assertEqual(error["code"], "invalid_probe_output")

    def test_probe_error_marker_cannot_report_idle(self) -> None:
        target = MODULE.Target("node", "example.test", "root", 22, (0,), 3, 10)

        devices, error = MODULE._parse_probe_output(
            "__probe_error__\tnpu_smi_not_found\n0\t0\n", target
        )

        self.assertEqual(devices[0]["state"], "unknown")
        self.assertEqual(devices[0]["reason"], "npu_smi_not_found")
        self.assertEqual(error["code"], "npu_smi_not_found")

    def test_probe_uses_strict_batch_ssh_and_parses_result(self) -> None:
        target = MODULE.Target("node", "example.test", "root", 2200, (0, 1), 4, 9)
        completed = subprocess.CompletedProcess([], 0, b"0\t0\n1\t1\n", b"")
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            result = MODULE.probe_target(target, timeout_limit=2.5)

        command = run.call_args.args[0]
        self.assertEqual(command[1], "-T")
        self.assertIn("BatchMode=yes", command)
        self.assertIn("StrictHostKeyChecking=accept-new", command)
        self.assertIn("UpdateHostKeys=no", command)
        self.assertEqual(command[command.index("-p") + 1], "2200")
        self.assertIsInstance(run.call_args.kwargs["input"], bytes)
        self.assertEqual(run.call_args.kwargs["timeout"], 2.5)
        self.assertEqual(result["status"], "busy")
        self.assertEqual([item["state"] for item in result["devices"]], ["idle", "busy"])
        self.assertGreaterEqual(result["elapsed_seconds"], 0)

    def test_windows_prefers_system_openssh_over_git_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            system_ssh = (
                pathlib.Path(temporary) / "System32" / "OpenSSH" / "ssh.exe"
            )
            system_ssh.parent.mkdir(parents=True)
            system_ssh.touch()
            with (
                mock.patch.object(MODULE.sys, "platform", "win32"),
                mock.patch.dict(
                    MODULE.os.environ, {"SystemRoot": temporary}, clear=False
                ),
            ):
                resolved = MODULE._resolve_ssh_path()

        self.assertEqual(resolved, str(system_ssh))

    def test_cli_returns_structured_invalid_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = pathlib.Path(temporary) / "targets.json"
            config.write_text(json.dumps({"version": 1, "targets": []}), encoding="utf-8")
            completed = subprocess.run(
                ["python", str(SCRIPT), str(config)],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "invalid_input")
        self.assertFalse(payload["safe_to_use"])

    def test_cli_reports_malformed_uri_as_structured_invalid_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = pathlib.Path(temporary) / "env_list.json"
            config.write_text(
                json.dumps(
                    {"version": 1, "environments": [{"ssh": "ssh://[", "devices": [0]}]}
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                ["python", str(SCRIPT), str(config)],
                text=True,
                capture_output=True,
                check=False,
                timeout=10,
            )

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["status"], "invalid_input")

    def test_worker_count_uses_full_host_concurrency_and_preserves_order(self) -> None:
        targets = [
            MODULE.Target(
                f"node-{index}", f"node-{index}.example.test", "root", 22, tuple(range(8)), 3, 10
            )
            for index in range(80)
        ]
        executor = mock.MagicMock()

        def submit(_probe, target):
            future = MODULE.concurrent.futures.Future()
            future.set_result(
                {
                    "name": target.name,
                    "endpoint": target.endpoint,
                    "status": "idle",
                    "devices": [
                        {"id": device, "state": "idle"} for device in target.devices
                    ],
                    "elapsed_seconds": 0.01,
                }
            )
            return future

        executor.__enter__.return_value.submit.side_effect = submit
        with mock.patch.object(
            MODULE.concurrent.futures, "ThreadPoolExecutor", return_value=executor
        ) as pool:
            result = MODULE.check_targets(targets, max_workers=64)

        pool.assert_called_once_with(max_workers=64)
        self.assertEqual(
            [environment["name"] for environment in result["environments"]],
            [target.name for target in targets],
        )

    def test_cli_defaults_to_bounded_npu_concurrency(self) -> None:
        args = MODULE.build_parser().parse_args(["env_list.json"])

        self.assertEqual(args.max_workers, 16)

    def test_busy_wait_retries_and_can_become_idle(self) -> None:
        busy = {"status": "busy"}
        idle = {"status": "idle"}
        output = io.StringIO()
        with (
            mock.patch.object(MODULE, "load_config", return_value=[mock.sentinel.target]),
            mock.patch.object(MODULE, "check_targets", side_effect=[busy, idle]) as check,
            mock.patch.object(MODULE.time, "monotonic", side_effect=[0, 1, 2, 3, 8, 9, 9]),
            mock.patch.object(MODULE.time, "sleep") as sleep,
            redirect_stdout(output),
        ):
            status = MODULE.main(
                ["ignored.json", "--wait-timeout", "120", "--interval", "5"]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(check.call_count, 2)
        sleep.assert_called_once_with(5.0)
        self.assertEqual(payload["wait"]["attempts"], 2)
        self.assertEqual(check.call_args_list[0].args[2], 119)
        self.assertEqual(check.call_args_list[1].args[2], 112)

    def test_wait_deadline_does_not_start_an_extra_probe(self) -> None:
        busy = {"status": "busy"}
        output = io.StringIO()
        with (
            mock.patch.object(MODULE, "load_config", return_value=[mock.sentinel.target]),
            mock.patch.object(MODULE, "check_targets", return_value=busy) as check,
            mock.patch.object(
                MODULE.time, "monotonic", side_effect=[0, 1, 120.1, 120.2, 120.3]
            ),
            mock.patch.object(MODULE.time, "sleep") as sleep,
            redirect_stdout(output),
        ):
            status = MODULE.main(["env_list.json", "--wait-timeout", "120"])

        self.assertEqual(status, 1)
        check.assert_called_once_with([mock.sentinel.target], 16, 119)
        sleep.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())["wait"]["timed_out"])


if __name__ == "__main__":
    unittest.main()
