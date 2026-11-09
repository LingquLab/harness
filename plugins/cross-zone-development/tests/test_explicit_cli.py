"""Explicit green connection and retired discovery entry points."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cross_zone.cli import main
from cross_zone.protocol import read_wire
from test_bridge import config

SESSION = "19146292-52a4-4094-9cd5-6086b0c3ec05"
PLUGIN = Path(__file__).parents[1]


class ExplicitCliTests(unittest.TestCase):
    def test_missing_command_and_retired_discover_fail_before_config_or_network(self):
        for args in ([], ["discover"], ["--session", SESSION, "discover"]):
            with self.subTest(args=args), patch("sys.argv", ["cross_zone", *args]), \
                    patch("cross_zone.cli.load_config") as load, patch("sys.stderr"), \
                    self.assertRaises(SystemExit) as error:
                main()
            self.assertEqual(error.exception.code, 2)
            load.assert_not_called()

    def test_open_prepares_and_notifies_only_selected_session(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(directory)
            cfg["access_key"] = "test-key"
            with patch("sys.argv", ["cross_zone", "--config", str(Path(directory) / "green.json"),
                                    "--session", SESSION, "open"]), \
                    patch("cross_zone.cli.load_config", return_value=cfg), \
                    patch("cross_zone.cli.preflight"), patch("cross_zone.cli.HapiClient") as client, \
                    patch("cross_zone.cli.Bridge") as bridge:
                main()
            bridge.return_value.prepare_open.assert_called_once_with()
            bridge.return_value.run.assert_called_once_with()
            client.return_value.sessions.assert_not_called()
            client.return_value.messages.assert_not_called()
            args = client.return_value.send.call_args.args
            self.assertEqual(args[0], SESSION)
            event = read_wire(args[1])
            self.assertEqual(event["type"], "OPEN")
            self.assertEqual(event["session_url"], "sessions/" + SESSION)
            self.assertEqual(event["version"], "0.8.0")
            self.assertEqual(set(event), {"protocol", "type", "event_id", "version", "session_url"})

    def test_shell_requires_explicit_session_and_forwards_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied = root / "start-bridge.sh"
            copied.write_text((PLUGIN / "start-bridge.sh").read_text())
            for args in ([], ["discover"], ["open"]):
                result = subprocess.run(["bash", str(copied), *args], capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
            capture = root / "args.json"
            launcher = root / "py"
            launcher.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                                "with open(os.environ['BRIDGE_CAPTURE'], 'w') as f: json.dump(sys.argv[1:], f)\n")
            launcher.chmod(0o755)
            (root / "config.local.json").write_text("{}")
            result = subprocess.run(["bash", str(copied), "open", SESSION], cwd=root,
                                    capture_output=True, text=True, timeout=5,
                                    env={**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                                         "BRIDGE_CAPTURE": str(capture), "BRIDGE_LOG_DIR": str(root / "logs")})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(capture.read_text()),
                             ["-3", "-m", "cross_zone", "--config", "config.local.json",
                              "--workspace", str(root), "--session", SESSION, "open"])

    def test_watchdog_rejects_missing_session_and_discover(self):
        for args in ([], ["discover"]):
            result = subprocess.run(["bash", str(PLUGIN / "watch-bridge.sh"), *args], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
