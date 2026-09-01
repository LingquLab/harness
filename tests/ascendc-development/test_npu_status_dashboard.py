#!/usr/bin/env python3
"""Offline regression tests for the Ascend NPU occupancy dashboard."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import threading
import urllib.error
import urllib.request
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT_DIR = (
    ROOT / "plugins/ascendc-development/skills/ascendc-npu-status/scripts"
)
sys.path.insert(0, str(SCRIPT_DIR))
SCRIPT = SCRIPT_DIR / "npu_status_dashboard.py"
SPEC = importlib.util.spec_from_file_location("npu_status_dashboard", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class NpuStatusDashboardTest(unittest.TestCase):
    def test_idle_age_tracks_last_busy_observation(self) -> None:
        target = MODULE.check_npu_status.Target(
            "lab-1", "192.0.2.1", "root", 22, (0,), 3, 10
        )
        busy = {
            "environments": [
                {
                    "name": "lab-1",
                    "endpoint": "ssh://root@192.0.2.1:22",
                    "status": "busy",
                    "devices": [{"id": 0, "state": "busy"}],
                }
            ]
        }
        idle = {
            "environments": [
                {
                    "name": "lab-1",
                    "endpoint": "ssh://root@192.0.2.1:22",
                    "status": "idle",
                    "devices": [{"id": 0, "state": "idle"}],
                }
            ]
        }
        with mock.patch.object(MODULE.time, "time", return_value=100.0):
            store = MODULE.StatusStore([target], max_workers=1, interval=10)

        def stop_after_second_probe(_remaining: float) -> None:
            if check.call_count == 2:
                store.stop()

        with (
            mock.patch.object(
                MODULE.check_npu_status, "check_targets", side_effect=[busy, idle]
            ) as check,
            mock.patch.object(MODULE.time, "time", side_effect=[110.0, 120.0]),
            mock.patch.object(store._stop, "wait", side_effect=stop_after_second_probe),
        ):
            store.run()

        environment = store.snapshot()["environments"][0]
        self.assertEqual(environment["idle_since_epoch_seconds"], 110.0)
        self.assertFalse(environment["idle_duration_lower_bound"])
        self.assertEqual(store.snapshot()["refresh_interval_seconds"], 10)

    def test_initial_idle_duration_is_marked_as_lower_bound(self) -> None:
        target = MODULE.check_npu_status.Target(
            "local", None, None, None, (0,), 3, 10
        )
        result = {
            "environments": [
                {
                    "name": "local",
                    "endpoint": "local",
                    "status": "idle",
                    "devices": [{"id": 0, "state": "idle"}],
                }
            ]
        }
        with mock.patch.object(MODULE.time, "time", return_value=100.0):
            store = MODULE.StatusStore([target], max_workers=1, interval=10)

        def stop_after_probe(_remaining: float) -> None:
            store.stop()

        with (
            mock.patch.object(MODULE.check_npu_status, "check_targets", return_value=result),
            mock.patch.object(MODULE.time, "time", return_value=110.0),
            mock.patch.object(store._stop, "wait", side_effect=stop_after_probe),
        ):
            store.run()

        environment = store.snapshot()["environments"][0]
        self.assertEqual(environment["idle_since_epoch_seconds"], 100.0)
        self.assertTrue(environment["idle_duration_lower_bound"])

    def test_server_exposes_dashboard_and_json_only_on_selected_routes(self) -> None:
        store = mock.Mock()
        store.snapshot.return_value = {"status": "idle", "safe_to_use": True}
        server = MODULE.DashboardServer(("127.0.0.1", 0), store, b"<main>dashboard</main>")
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(f"{base_url}/", timeout=2) as response:
                self.assertEqual(response.read(), b"<main>dashboard</main>")
                self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            with urllib.request.urlopen(f"{base_url}/api/status?fresh=1", timeout=2) as response:
                self.assertEqual(json.load(response), store.snapshot.return_value)
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(f"{base_url}/missing", timeout=2)
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_parser_rejects_unsafe_refresh_intervals_and_invalid_ports(self) -> None:
        parser = MODULE.build_parser()
        for arguments in (["env.json", "--interval", "1"], ["env.json", "--port", "65536"]):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit):
                parser.parse_args(arguments)


if __name__ == "__main__":
    unittest.main()
