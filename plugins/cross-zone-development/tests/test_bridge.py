import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from cross_zone.agent import CodeAgentCLI
from cross_zone.cli import InstanceLock, error_hint, safe_error_detail, select_session, preflight, main
from cross_zone.config import load_config
from cross_zone.controller import Bridge, CursorReset
from cross_zone.egress import failure_detail, review
from cross_zone.hapi import HapiClient, HapiError
from cross_zone.protocol import MARKER, ProtocolError, assistant_text, open_event, parse, read_wire, wire


def task(**changes):
    event = {"protocol": "cross-zone/v3", "type": "TASK", "event_id": "blue-1", "task_id": "task-1",
             "iteration": 1, "revision": "a" * 40, "goal": "Run the regression",
             "checks": [{"id": "regression", "action": "Run approved tests", "expected": "All pass"}],
             "timeout_seconds": 600}
    event.update(changes)
    return event


def general_task(**changes):
    event = task(**changes)
    event.pop("revision", None)
    return event


def output(**changes):
    value = {"kind": "RESULT", "status": "PASS", "summary": "The regression passed.",
             "checks": [{"id": "regression", "status": "PASS"}], "error_code": "", "question": "",
             "local_modification_tested": False, "local_modification_outcome": "NOT_RUN", "egress_reviewed": True}
    value.update(changes)
    return value


def message(event, seq, flavor="codex"):
    data = {"type": "message", "message": wire(event), "scope_role": "parent"}
    if flavor == "output":
        data = {"type": "assistant", "message": {"content": [{"type": "text", "text": wire(event)}]}}
    return {"id": str(seq), "seq": seq, "createdAt": seq * 1000,
            "content": {"role": "agent", "content": {"type": flavor, "data": data}}}


class FakeClient:
    access_key = "test-secret-not-exported"
    token = "test-jwt-not-exported"

    def __init__(self):
        self.rows = []
        self.sent = []
        self.epoch = 0
        self.fail_send = False

    def messages(self, session, **query):
        head = self.rows[-1]["seq"] if self.rows else None
        after = query.get("afterSeq")
        before = query.get("beforeSeq")
        rows = self.rows
        if after is not None:
            rows = [r for r in rows if r["seq"] > after]
            selected = rows[:query["limit"]]
        else:
            if before is not None:
                rows = [r for r in rows if r["seq"] < before]
            selected = rows[-query["limit"]:]
        last = selected[-1]["seq"] if selected else after
        oldest = selected[0]["seq"] if selected else None
        return {"messages": copy.deepcopy(selected), "page": {
            "epoch": self.epoch, "reset": False, "direction": "after" if after is not None else "latest",
            "snapshotHeadAt": head * 1000 if head else None, "snapshotHeadSeq": head,
            "nextAfterAt": last * 1000 if last else None, "nextAfterSeq": last,
            "nextBeforeAt": oldest * 1000 if oldest else None, "nextBeforeSeq": oldest,
            "hasMore": len(rows) > len(selected),
        }}

    def send(self, session, text, event_id):
        if self.fail_send:
            raise HapiError(409)
        self.sent.append((event_id, read_wire(text)))


class FakeAgent:
    def __init__(self, outputs=None):
        self.calls = []
        self.outputs = outputs or [{"output": output(), "session_id": "session-green", "dirty": False}]

    def run(self, *args):
        self.calls.append(args)
        return self.outputs.pop(0)


def config(directory):
    return {"hub_url": "http://localhost/hapi/", "session_id": "blue-session",
            "state_dir": str(Path(directory) / "state"), "sse": False,
            "workspace_dir": str(Path(directory) / "repo"),
            "max_task_seconds": 1800, "max_concurrent_tasks": 1, "max_questions": 3, "poll_seconds": 0.1, "agent_command": ["codeagent"],
            "agent_live_log": True, "agent_log_max_chars": 2000}


class OpenTests(unittest.TestCase):
    def test_open_event_is_green_only(self):
        event = open_event("sessions/19146292-52a4-4094-9cd5-6086b0c3ec05")
        self.assertEqual(event["protocol"], "cross-zone/v3")
        self.assertEqual(event["type"], "OPEN")
        self.assertEqual(event["version"], "0.5.2")
        self.assertNotIn("target", event)
        self.assertIn(event["session_url"], event["session_url"])
        self.assertIn("green-open-", event["event_id"])
        # Blue cannot inject an OPEN envelope; it must be green-originated.
        with self.assertRaises(ProtocolError):
            parse(wire(event))


class ConsoleEncodingTests(unittest.TestCase):
    def test_redirected_console_and_logs_are_utf8_under_legacy_encoding(self):
        code = ("from cross_zone.cli import configure_console\n"
                "import logging,sys\nconfigure_console()\n"
                "print('检查成功')\nlogging.basicConfig(level=logging.INFO)\n"
                "logging.info('服务器可访问')\n")
        env = {**os.environ, "PYTHONIOENCODING": "gbk", "PYTHONUTF8": "0"}
        result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("检查成功", result.stdout.decode("utf-8"))
        self.assertIn("服务器可访问", result.stderr.decode("utf-8"))


class GitBashLauncherTests(unittest.TestCase):
    def test_launcher_forwards_command_and_config_to_py(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_py = root / "py"
            capture = root / "capture.txt"
            config_path = root / "green config.json"
            config_path.write_text("{}", encoding="utf-8")
            fake_py.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE\"\n", encoding="utf-8")
            fake_py.write_text(fake_py.read_text(encoding="utf-8") +
                               'test "$PYTHONUTF8" = 1 && test "$PYTHONIOENCODING" = utf-8 || exit 42\n',
                               encoding="utf-8")
            fake_py.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = str(root) + os.pathsep + env["PATH"]
            env["CAPTURE"] = str(capture)
            env["BRIDGE_LOG_DIR"] = str(root / "logs")
            session_id = "19146292-52a4-4094-9cd5-6086b0c3ec05"
            launcher = Path(__file__).parents[1] / "start-bridge.sh"
            result = subprocess.run(["bash", str(launcher), "doctor", session_id, str(config_path)],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(capture.read_text(encoding="utf-8").splitlines(),
                             ["-3", "-m", "cross_zone", "--config", str(config_path),
                              "--workspace", str(root),
                              "--session", session_id, "doctor"])
            log_path = root / "logs" / ("bridge-doctor-" + session_id + ".log")
            self.assertTrue(log_path.is_file())
            self.assertIn("Bridge log:", log_path.read_text(encoding="utf-8"))

    @unittest.skipIf(os.name == "nt", "POSIX process-group test; launcher also targets Git Bash")
    def test_watchdog_restarts_killed_bridge_and_stops_on_ctrl_c(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watcher = root / "watch-bridge.sh"
            watcher.write_text((Path(__file__).parents[1] / "watch-bridge.sh").read_text(), encoding="utf-8")
            capture, child_pid = root / "calls", root / "child.pid"
            (root / "start-bridge.sh").write_text(
                '#!/bin/bash\nprintf "%s\\n" "$#" "$1" "$2" "$3" "$PWD" >> "$CAPTURE"\n'
                'count=$(wc -l < "$CAPTURE")\n'
                'if [[ "$count" -eq 5 ]]; then echo "$$" > "$CHILD_PID"; exec sleep 60; fi\n'
                'if [[ "$count" -eq 10 ]]; then exit 0; fi\nexec sleep 60\n', encoding="utf-8")
            env = dict(os.environ, CAPTURE=str(capture), CHILD_PID=str(child_pid), BRIDGE_RESTART_DELAY="0.05")
            session = "fc85951c-ffeb-4fb3-b44f-ae052e9106f6"
            process = subprocess.Popen(["bash", str(watcher), session, "green config.json"],
                                       cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True)
            try:
                deadline = time.monotonic() + 5
                while not child_pid.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue(child_pid.exists(), "child did not start")
                os.kill(int(child_pid.read_text().strip()), signal.SIGKILL)
                while time.monotonic() < deadline:
                    if capture.exists() and len(capture.read_text().splitlines()) >= 15:
                        break
                    time.sleep(0.01)
                records = capture.read_text().splitlines()
                expected = ["3", "open", session, "green config.json", str(root)]
                self.assertEqual(records, expected * 3)
                os.killpg(process.pid, signal.SIGINT)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 130, stderr)
                self.assertIn("restarting", stdout)
                self.assertIn("watchdog stopped", stdout)
                self.assertEqual(capture.read_text().splitlines(), records)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=5)

    def test_watchdog_rejects_invalid_arguments_and_restart_delay(self):
        watcher = Path(__file__).parents[1] / "watch-bridge.sh"
        invalid = subprocess.run(["bash", str(watcher)], capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        for delay in ("0", "0.0", "-1", "invalid"):
            with self.subTest(delay=delay):
                result = subprocess.run(["bash", str(watcher), "session"],
                                        env=dict(os.environ, BRIDGE_RESTART_DELAY=delay), capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("positive number", result.stderr)

    def test_launcher_rejects_unknown_command(self):
        launcher = Path(__file__).parents[1] / "start-bridge.sh"
        result = subprocess.run(["bash", str(launcher), "unknown"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Usage:", result.stderr)


class CliErrorTests(unittest.TestCase):
    def test_error_detail_is_actionable_bounded_and_redacted(self):
        secret = "super-secret-access-key"
        detail = safe_error_detail(ValueError("State mismatch for " + secret), (secret,))
        self.assertEqual(detail, "State mismatch for [REDACTED]")
        self.assertNotIn(secret, detail)
        self.assertLessEqual(len(safe_error_detail(ValueError("x" * 5000))), 2014)

    def test_error_hints_cover_hapi_and_config(self):
        self.assertIn("HAPI_ACCESS_KEY", error_hint(HapiError(401)))
        self.assertIn("HTTP 403", error_hint(HapiError(403)))
        self.assertIn("JSON", error_hint(json.JSONDecodeError("bad", "{}", 1)))

    def test_config_accepts_local_access_key_without_logging_it(self):
        with tempfile.TemporaryDirectory() as directory:
            value = config(directory)
            value["access_key"] = "local-config-secret"
            for field in ("session_id", "session_url", "state_dir", "workspace_dir", "key_env"):
                value.pop(field, None)
            path = Path(directory) / "config.local.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            loaded = load_config(path)
            self.assertEqual(loaded["access_key"], "local-config-secret")
            self.assertEqual(safe_error_detail(ValueError("bad local-config-secret"),
                                               (loaded["access_key"],)),
                             "bad [REDACTED]")

    def test_config_ignores_removed_session_state_and_repository_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            for field in ("session_id", "session_url", "state_dir", "workspace_dir", "key_env",
                          "task_binding", "repositories", "profiles", "profile",
                          "egress_deny_patterns"):
                value = config(directory)
                for runtime_field in ("session_id", "state_dir", "workspace_dir"):
                    value.pop(runtime_field, None)
                value[field] = "obsolete"
                path = Path(directory) / (field + ".json")
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(field=field):
                    loaded = load_config(path)
                    self.assertNotIn(field, loaded)

    def test_preflight_checks_workspace_and_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            value = config(directory)
            value["agent_command"] = [sys.executable]
            Path(value["workspace_dir"]).mkdir()
            preflight(value)
            self.assertTrue(Path(value["state_dir"]).is_dir())
            value["agent_command"] = [str(Path(directory) / "missing-cli")]
            with self.assertRaisesRegex(ValueError, "executable not found"):
                preflight(value)

    def test_open_preflights_and_binds_before_notification(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            value = config(directory)
            value["access_key"] = "test-local-key"
            argv = ["bridge", "--session", "19146292-52a4-4094-9cd5-6086b0c3ec05", "open"]
            with patch("sys.argv", argv), patch("cross_zone.cli.load_config", return_value=value), \
                 patch("cross_zone.cli.preflight", side_effect=lambda cfg: calls.append("preflight")), \
                 patch("cross_zone.cli.InstanceLock"), patch("cross_zone.cli.HapiClient") as client, \
                 patch("cross_zone.cli.Bridge") as bridge:
                bridge.return_value.prepare_open.side_effect = lambda: calls.append("bind")
                client.return_value.send.side_effect = lambda *args: calls.append("send")
                bridge.return_value.run.side_effect = lambda: calls.append("run")
                main()
                self.assertEqual(calls, ["preflight", "bind", "send", "run"])
                bridge.return_value.close.assert_not_called()

    def test_config_caps_questions_at_three(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.local.json"
            for count in (4, True, 2.5):
                value = config(directory)
                value["max_questions"] = count
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(count=count), self.assertRaises(ValueError):
                    load_config(path)

    def test_command_line_session_derives_isolated_state(self):
        with tempfile.TemporaryDirectory() as directory:
            value = {}
            config_path = Path(directory) / "config.local.json"
            session_id = "19146292-52a4-4094-9cd5-6086b0c3ec05"
            self.assertEqual(select_session(value, config_path, session_id), session_id)
            self.assertEqual(Path(value["state_dir"]), Path(directory) / ".state" / session_id)
            with self.assertRaisesRegex(ValueError, "complete HAPI session UUID"):
                select_session({}, config_path, "not-a-session")

class ProtocolTests(unittest.TestCase):
    def test_readable_and_legacy_task_formats_are_accepted(self):
        event = task()
        readable = wire(event, readable=True)
        self.assertTrue(readable.startswith(MARKER + "```json\n{\n"))
        self.assertIn('\n  "type": "TASK"', readable)
        self.assertEqual(parse(readable), event)
        self.assertEqual(parse(wire(event)), event)

    def test_readable_format_rejects_trailing_prose_and_duplicate_fields(self):
        for text in (wire(task(), readable=True) + "\nextra prose",
                     MARKER + '```json\n{"protocol":"cross-zone/v3","protocol":"bad"}\n```'):
            with self.subTest(text=text), self.assertRaises(ProtocolError):
                parse(text)

    def test_roundtrip_codex_and_claude(self):
        for flavor in ("codex", "output"):
            self.assertEqual(parse(assistant_text(message(task(), 1, flavor))), task())

    def test_null_payload_remains_an_invalid_protocol(self):
        with self.assertRaisesRegex(ProtocolError, "invalid_protocol"):
            parse(MARKER + "null")

    def test_new_task_omits_green_local_aliases(self):
        event = task()
        self.assertEqual(parse(wire(event)), event)
        with self.assertRaises(ProtocolError):
            parse(wire({**event, "repository": "candidate", "scope_profile": "tests"}))

    def test_general_task_and_controls_omit_revision(self):
        event = general_task()
        self.assertEqual(parse(wire(event)), event)
        cancel = {"protocol": "cross-zone/v3", "type": "CANCEL", "event_id": "cancel-1",
                  "task_id": event["task_id"], "iteration": 1}
        self.assertEqual(parse(wire(cancel)), cancel)

    def test_commands_are_session_bound_and_reject_target(self):
        controls = [task(), general_task(),
                    {"protocol": "cross-zone/v3", "type": "CANCEL", "event_id": "cancel", "task_id": "task-1", "iteration": 1},
                    {"protocol": "cross-zone/v3", "type": "ANSWER", "event_id": "answer", "task_id": "task-1", "iteration": 1, "question_id": "q-1", "answer": "yes"}]
        for event in controls:
            with self.subTest(kind=event["type"]):
                self.assertEqual(parse(wire(event)), event)
                with self.assertRaisesRegex(ProtocolError, "invalid_fields"):
                    parse(wire(dict(event, target="green-dev")))

    def test_ignore_user_tool_child_partial_and_examples(self):
        row = message(task(), 1)
        row["content"]["role"] = "user"
        self.assertIsNone(assistant_text(row))
        row = message(task(), 1)
        row["content"]["content"]["data"]["type"] = "tool-call"
        self.assertIsNone(assistant_text(row))
        row = message(task(), 1)
        row["content"]["content"]["data"]["scope_role"] = "child"
        self.assertIsNone(assistant_text(row))
        self.assertIsNone(parse("Example:\n" + wire(task())))
        self.assertIsNone(parse("```json\n" + wire(task()) + "\n```"))
        with self.assertRaisesRegex(ProtocolError, "invalid_fields"):
            parse(wire(task(target="another")))

    def test_v2_live_protocol_is_not_accepted(self):
        self.assertIsNone(parse("CROSS_ZONE_V2\n" + json.dumps(task())))
        with self.assertRaisesRegex(ProtocolError, "invalid_protocol"):
            parse(wire(task(protocol="cross-zone/v2")))

    def test_malformed_envelopes_reject(self):
        variants = [task(iteration=True), task(revision="main"), task(timeout_seconds=599),
                    task(checks=[]), task(task_id="../../escape"), task(extra="field"), task(type=[]), task(type="UNKNOWN")]
        for event in variants:
            with self.subTest(event=event), self.assertRaises(ProtocolError):
                parse(wire(event))
        with self.assertRaises(ProtocolError):
            parse(MARKER + '{"protocol":"cross-zone/v3","protocol":"bad"}')


class EgressTests(unittest.TestCase):
    def test_revisionless_authorized_changes_can_pass(self):
        value = output(local_modification_tested=True, local_modification_outcome="PASS")
        self.assertEqual(review(value, general_task())["status"], "PASS")
        with self.assertRaisesRegex(ValueError, "baseline_not_passed"):
            review(value, task())

    def test_revisionless_changes_do_not_override_failed_checks(self):
        value = output(local_modification_tested=True, local_modification_outcome="PASS",
                       checks=[{"id": "regression", "status": "NOT_RUN"}])
        with self.assertRaisesRegex(ValueError, "baseline_not_passed"):
            review(value, general_task())

    def test_pass_and_failed_local_fix(self):
        self.assertEqual(review(output(), task())["status"], "PASS")
        value = output(status="FAIL", local_modification_tested=True, local_modification_outcome="PASS",
                       checks=[{"id": "regression", "status": "FAIL"}])
        self.assertEqual(review(value, task())["status"], "FAIL")

    def test_allow_diagnostic_output(self):
        values = [
            "http://internal.example and https://service.example/status",
            "192.168.1.1",
            "C:\\work\\project and \\\\server\\share",
            "/root/key /tmp/run /workspace/repo /Users/test",
            "```python\nprint('one')\nprint('two')\n```",
            "Traceback:\n" + "  stack frame\n" * 12,
            "Pseudo: fetch config, validate token, then return the parsed result.\r",
        ]
        for summary in values:
            with self.subTest(summary=summary):
                self.assertEqual(review(output(summary=summary), task())["summary"], summary)

    def test_reject_credentials(self):
        for summary in ["password=example", "Bearer secret-value", "api_key: secret-value"]:
            with self.subTest(summary=summary), self.assertRaises(ValueError):
                review(output(summary=summary), task())
        with self.assertRaises(ValueError):
            review(output(summary="contains test-secret"), task(), secrets=["test-secret"])

    def test_result_and_summary_limits(self):
        self.assertEqual(len(review(output(summary="x" * 3000), task())["summary"]), 3000)
        with self.assertRaises(ValueError):
            review(output(summary="x" * 3001), task())

        check_ids = [f"check-{index}-" + "x" * 60 for index in range(20)]
        request = task(checks=[{"id": check_id, "action": "observe", "expected": "ok"}
                               for check_id in check_ids])
        value = output(kind="QUESTION", status="BLOCKED", summary="x" * 3000,
                       question="q" * 800,
                       checks=[{"id": check_id, "status": "NOT_RUN"} for check_id in check_ids])
        with self.assertRaisesRegex(ValueError, "egress_size_limit"):
            review(value, request)

    def test_size_limit_includes_transport_envelope(self):
        # Agent fields fit under 4K; protocol/task metadata puts the actual RESULT over.
        from cross_zone.protocol import canonical
        value = output(summary="x" * 3000, error_code="e" * 100)
        value["checks"] = [{"id": "c" * 78 + str(i), "status": "PASS"} for i in range(6)]
        request = task(task_id="t" * 80,
                       checks=[{"id": c["id"]} for c in value["checks"]])
        self.assertLess(len(canonical(value).encode("utf-8")), 4096)
        with self.assertRaisesRegex(ValueError, "egress_size_limit"):
            review(value, request)

    def test_failure_detail_redacts_credentials_before_truncating(self):
        detail = ("known-secret password=abc Bearer xyz api_key: value gho_1234567890123456 "
                  "https://user:pass@host/path password=\"quoted secret\" \"token\": 'another secret'")
        result = failure_detail(detail, secrets=("known-secret",))
        for secret in ("known-secret", "abc", "xyz", "value", "gho_1234567890123456", "user:pass", "quoted secret", "another secret"):
            self.assertNotIn(secret, result)
        self.assertIn("[REDACTED]", result)
        bounded = failure_detail("错误\n" * 5000)
        self.assertLessEqual(len(json.dumps(bounded, ensure_ascii=False).encode("utf-8")), 2000)
        self.assertIn("[truncated]", bounded)

    def test_failure_detail_redacts_cli_flags_and_http_basic_auth(self):
        cases = (
            ("error executing client --api-key confidential-value", "confidential-value"),
            ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
            ('client --access-token "quoted secret" failed', "quoted secret"),
            ("client --password=example-password failed", "example-password"),
        )
        for detail, secret in cases:
            with self.subTest(detail=detail):
                exported = failure_detail(detail)
                self.assertNotIn(secret, exported)
                self.assertIn("[REDACTED]", exported)

    def test_result_size_budget_counts_json_indentation(self):
        checks = [{"id": "c" * 78 + str(i), "status": "PASS"} for i in range(6)]
        value = output(summary="x" * 2900, checks=checks)
        request = task(checks=[{"id": check["id"]} for check in checks])
        with self.assertRaisesRegex(ValueError, "egress_size_limit"):
            review(value, request)

    def test_result_question_placeholders_are_normalized_without_mutating_input(self):
        for question in ("", " \t\n", "None", " NONE ", "null", "Null", "N/A", " n/a "):
            with self.subTest(question=question):
                value = output(question=question)
                self.assertEqual(review(value, task())["question"], "")
                self.assertEqual(value["question"], question)

    def test_question_placeholder_does_not_bypass_result_checks(self):
        for changes in ({"checks": []}, {"local_modification_tested": True},
                        {"checks": [{"id": "regression", "status": "NOT_RUN"}]},
                        {"egress_reviewed": False}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                review(output(question="None", **changes), task())

    def test_result_with_actual_question_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplete_result"):
            review(output(question="Which fixture should I use?"), task())

    def test_question_text_is_not_normalized(self):
        for question in ("None", "null", "N/A", "Which fixture should I use?"):
            with self.subTest(question=question):
                value = output(kind="QUESTION", status="BLOCKED", question=question)
                self.assertEqual(review(value, task())["question"], question)

    def test_no_false_pass(self):
        for changes in ({"checks": []}, {"local_modification_tested": True}, {"egress_reviewed": False},
                        {"checks": [{"id": "regression", "status": "NOT_RUN"}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                review(output(**changes), task())


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = config(self.tmp.name)
        self.client = FakeClient()
        self.agent = FakeAgent()
        self.bridge = Bridge(self.cfg, self.client, self.agent)

    def tearDown(self):
        self.bridge.close()
        self.tmp.cleanup()

    def ingest(self, event):
        self.client.rows.append(message(event, len(self.client.rows) + 1))
        self.bridge.catch_up()

    def settle(self):
        for _ in range(100):
            self.bridge.work()
            if not self.bridge.active:
                return
            time.sleep(0.01)
        self.fail("worker did not settle")

    def row(self):
        return self.bridge.store.get_task("task-1", 1)

    def control(self, kind, **fields):
        base = {k: v for k, v in task().items() if k in {"protocol", "task_id", "iteration", "revision"}}
        return {**base, "type": kind, "event_id": "control-" + str(len(self.client.rows)), **fields}

    def test_fresh_open_does_not_resume_old_queue_or_continuation(self):
        self.bridge.bind()
        self.ingest(task())
        self.ingest(task(task_id="continuation", event_id="continuation"))
        with self.bridge.store.db:
            self.bridge.store.db.execute("UPDATE tasks SET state='WAITING_ANSWER',session_id='prior',questions=1 WHERE task_id='continuation'")
        # This historical command was never accepted; fresh OPEN must skip it.
        self.client.rows.append(message(task(task_id="unread", event_id="unread"), 3))
        self.bridge.prepare_open()
        self.assertEqual(self.row()["state"], "BLOCKED")
        self.assertEqual(self.bridge.store.get_task("continuation", 1)["state"], "NEEDS_HUMAN")
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))
        self.bridge.catch_up()
        self.bridge.work()
        self.assertIsNone(self.bridge.store.get_task("unread", 1))
        self.assertEqual(self.agent.calls, [])
        self.ingest(task(task_id="new-instruction", event_id="new-instruction"))
        self.agent.outputs = [{"output": output(status="BLOCKED", checks=[{"id": "regression", "status": "BLOCKED"}]), "recovery_checked": False}]
        self.settle()
        self.assertEqual(len(self.agent.calls), 1)
        self.assertEqual(self.bridge.store.get_task("new-instruction", 1)["state"], "BLOCKED")

    def test_fresh_open_discards_question_of_an_already_timed_out_task(self):
        self.agent.outputs = [{"output": output(kind="QUESTION", status="BLOCKED", question="Which fixture?"),
                               "session_id": "prior-session"}]
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        with self.bridge.store.db:
            self.bridge.store.update(self.row(), deadline=time.time() - 1)
        self.bridge.work()
        self.assertEqual(self.row()["state"], "TIMED_OUT")
        self.assertTrue(any(read_wire(row["text"])["type"] == "QUESTION"
                            for row in self.bridge.store.db.execute("SELECT text FROM outbox WHERE sent=0")))
        self.bridge.prepare_open()
        self.bridge.flush()
        self.assertFalse(any(event["type"] in {"ACK", "QUESTION"} for _, event in self.client.sent))
        self.assertTrue(any(event["type"] == "RESULT" and event["status"] == "TIMED_OUT"
                            for _, event in self.client.sent))

    def test_first_bind_skips_history(self):
        self.client.rows.append(message(task(), 1))
        self.bridge.catch_up()
        self.assertIsNone(self.row())

    def test_poison_envelope_does_not_block_next_task(self):
        self.bridge.bind()
        self.ingest(task(type=[]))
        self.ingest(task())
        self.settle()
        self.assertEqual(self.row()["state"], "PASS")

    def test_task_execution_duplicate_and_conflict(self):
        self.bridge.bind()
        self.ingest(task())
        self.ingest(task(event_id="retry"))
        self.ingest(task(event_id="conflict", goal="changed"))
        self.settle()
        self.assertEqual(len(self.agent.calls), 1)
        self.assertEqual(self.row()["state"], "PASS")
        self.bridge.flush()
        events = [e for _, e in self.client.sent]
        self.assertEqual(sum(e["type"] == "RESULT" for e in events), 1)
        self.assertTrue(any(e["type"] == "REJECTED" for e in events))

    def test_new_outbox_messages_are_indented_json_code_blocks(self):
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        rows = self.bridge.store.db.execute("SELECT text FROM outbox ORDER BY rowid").fetchall()
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertTrue(row["text"].startswith(MARKER + "```json\n{\n"))
            self.assertTrue(row["text"].endswith("\n```"))

    def test_result_validation_failures_report_fields_and_limits(self):
        cases = (
            (output(question="Need approval"), "incomplete_result", "question must be empty"),
            (output(summary="x" * 3001), "result_schema", "summary length=3001 exceeds limit=3000"),
            (output(local_modification_tested="false"), "result_schema", "local_modification_tested expected boolean, got str"),
            (output(checks=[]), "incomplete_result", "missing requested checks"),
            (output(egress_reviewed=False), "egress_not_reviewed", "egress_reviewed must be true"),
            (output(local_modification_tested=True), "baseline_not_passed", "local_modification_tested=True"),
        )
        self.bridge.bind()
        for iteration, (value, code, condition) in enumerate(cases, 1):
            with self.subTest(code=code, condition=condition):
                self.agent.outputs = [{"output": value, "dirty": False}]
                self.ingest(task(iteration=iteration, event_id=f"validation-{iteration}"))
                self.settle()
                self.bridge.flush()
                event = self.client.sent[-1][1]
                self.assertEqual(event["status"], "NEEDS_HUMAN")
                self.assertEqual(event["reason"], "structured_result_or_egress_review_failed")
                self.assertIn(code, event["detail"])
                self.assertIn(condition, event["detail"])
                self.assertIn("do not repeat remote actions", event["detail"])

    def test_rejected_credentials_report_field_without_exporting_payload(self):
        self.agent.outputs = [{"output": output(summary="sensitive-content " + self.client.access_key), "dirty": False}]
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.bridge.flush()
        event = self.client.sent[-1][1]
        self.assertEqual(event["status"], "NEEDS_HUMAN")
        self.assertIn("egress_content_rejected", event["detail"])
        self.assertIn("summary", event["detail"])
        self.assertNotIn(self.client.access_key, str(event))
        self.assertNotIn("sensitive-content", str(event))

    def test_agent_failure_detail_reaches_blue_without_known_secrets(self):
        self.agent.outputs = [{"failure": "agent_runtime_error", "status": "NEEDS_HUMAN",
                               "detail": "RuntimeError: agent_output_reader_stuck\n" + self.client.access_key}]
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.bridge.flush()
        result = next(event for _, event in self.client.sent if event["type"] == "RESULT")
        self.assertEqual(result["reason"], "agent_runtime_error")
        self.assertIn("RuntimeError: agent_output_reader_stuck", result["detail"])
        self.assertNotIn(self.client.access_key, result["detail"])
        self.assertIn("[REDACTED]", result["detail"])

    def test_failure_result_with_unicode_detail_stays_within_wire_budget(self):
        self.agent.outputs = [{"failure": "agent_runtime_error", "status": "NEEDS_HUMAN", "detail": "错误\n" * 5000}]
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        row = self.bridge.store.db.execute("SELECT text FROM outbox ORDER BY rowid DESC LIMIT 1").fetchone()
        event = read_wire(row["text"])
        self.assertLessEqual(len(json.dumps(event, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")), 4096)
        self.assertEqual(event["reason"], "agent_runtime_error")

    def test_adapter_exception_details_are_reported_and_pause_execution(self):
        def fail(*args):
            raise RuntimeError("worker exploded")

        self.agent.run = fail
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.bridge.flush()
        result = next(event for _, event in self.client.sent if event["type"] == "RESULT")
        self.assertEqual(result["reason"], "agent_adapter_exception")
        self.assertIn("RuntimeError: worker exploded", result["detail"])
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))

    def test_immediate_start_sends_only_compact_progress_and_full_result(self):
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.bridge.flush()
        events = [event for _, event in self.client.sent]
        self.assertEqual([event["type"] for event in events], ["PROGRESS", "RESULT"])
        self.assertEqual(events[0], {"type": "PROGRESS", "task_id": "task-1", "iteration": 1})
        self.assertNotIn("target", events[1])
        self.assertEqual(events[1]["revision"], task()["revision"])
        self.assertEqual(events[1]["event_id"], self.client.sent[1][0])

    def test_queued_ack_and_later_progress_are_both_delivered(self):
        self.bridge.bind()
        self.ingest(task())
        self.bridge.flush()
        self.assertEqual(self.client.sent[0][1], {"type": "ACK", "task_id": "task-1", "iteration": 1})
        self.settle()
        self.bridge.flush()
        self.assertEqual([event["type"] for _, event in self.client.sent], ["ACK", "PROGRESS", "RESULT"])

    def test_start_does_not_suppress_another_tasks_ack(self):
        self.bridge.bind()
        self.ingest(task())
        self.ingest(task(event_id="next-task", task_id="task-2"))
        self.bridge.work()
        self.bridge.flush()
        events = [event for _, event in self.client.sent]
        self.assertEqual(events, [
            {"type": "ACK", "task_id": "task-2", "iteration": 1},
            {"type": "PROGRESS", "task_id": "task-1", "iteration": 1},
        ])

    def test_coalescing_keeps_other_iterations_and_revisions(self):
        request = task()
        variants = (task(iteration=2), task(revision="b" * 40), general_task())
        with self.bridge.store.db:
            retained = set()
            for index, variant in enumerate(variants):
                event_id = f"legacy-{index}"
                event = {**{k: v for k, v in variant.items() if k in
                            {"protocol", "task_id", "iteration", "revision"}},
                         "type": "ACK", "event_id": event_id, "state": "QUEUED"}
                self.bridge.store.db.execute("INSERT INTO outbox(id,text,created) VALUES (?,?,?)",
                                             (event_id, wire(event), time.time()))
                retained.add(event_id)
            removed = self.bridge.store.emit(request, "ACK", state="QUEUED")
            progress = self.bridge.store.emit(request, "PROGRESS", state="RUNNING")
        pending = {row["id"] for row in self.bridge.store.db.execute("SELECT id FROM outbox WHERE sent=0")}
        self.assertEqual(pending, retained | {progress})
        self.assertNotIn(removed, pending)

    def test_progress_rollback_restores_pending_ack(self):
        self.bridge.bind()
        self.ingest(task())
        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.bridge.store.db:
                self.bridge.store.emit(task(), "PROGRESS", state="RUNNING")
                raise RuntimeError("rollback")
        self.bridge.flush()
        self.assertEqual([event["type"] for _, event in self.client.sent], ["ACK"])

    def test_notification_retry_keeps_compact_body_and_transport_id(self):
        self.bridge.bind()
        self.ingest(task())
        self.bridge.work()
        attempts = []
        original_send = self.client.send

        def response_lost_once(session, text, event_id):
            attempts.append((text, event_id))
            if len(attempts) == 1:
                raise HapiError()
            original_send(session, text, event_id)

        with patch.object(self.client, "send", side_effect=response_lost_once):
            with self.assertRaises(HapiError):
                self.bridge.flush()
            self.bridge.flush()
        self.assertEqual(attempts[0], attempts[1])
        self.assertEqual(read_wire(attempts[0][0]),
                         {"type": "PROGRESS", "task_id": "task-1", "iteration": 1})

    def test_legacy_outbox_retry_preserves_body_and_transport_id(self):
        self.bridge.bind()
        self.ingest(task())
        row = self.bridge.store.db.execute("SELECT * FROM outbox").fetchone()
        legacy = {"protocol": "cross-zone/v3", "type": "ACK", "event_id": row["id"],
                  "task_id": "task-1", "iteration": 1,
                  "revision": task()["revision"], "state": "QUEUED"}
        with self.bridge.store.db:
            self.bridge.store.db.execute("UPDATE outbox SET text=? WHERE id=?", (wire(legacy), row["id"]))
        # HAPI accepted a legacy send, but the old bridge lost the response.
        self.client.send(self.cfg["session_id"], wire(legacy), row["id"])
        self.bridge.close()
        self.bridge = Bridge(self.cfg, self.client, self.agent)
        self.bridge.flush()
        self.assertEqual(self.client.sent, [(row["id"], legacy), (row["id"], legacy)])

    def test_none_question_result_reaches_pass(self):
        self.agent.outputs = [{"output": output(question="None"), "dirty": False}]
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.bridge.flush()
        self.assertEqual(self.row()["state"], "PASS")
        result = next(event for _, event in self.client.sent if event["type"] == "RESULT")
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["question"], "")

    def test_duplicate_session_commands_keep_dedup_identity(self):
        self.bridge.bind()
        event = task()
        compact = {k: v for k, v in event.items() if k != "target"}
        self.ingest(compact)
        self.settle()
        self.ingest(event)  # Same event ID: no duplicate execution.
        self.ingest(dict(event, event_id="legacy-retry"))
        self.bridge.flush()
        self.assertEqual(len(self.agent.calls), 1)
        self.assertFalse(any(event["type"] == "REJECTED" for _, event in self.client.sent))
        request = json.loads(self.row()["request"])
        self.assertNotIn("target", request)
        self.assertNotIn("target", self.client.sent[-1][1])

    def test_targetless_cancel_matches_session_task(self):
        self.bridge.bind()
        self.ingest(task())
        self.ingest({"protocol": "cross-zone/v3", "type": "CANCEL", "event_id": "cancel",
                     "task_id": "task-1", "iteration": 1, "revision": task()["revision"]})
        self.bridge.work()
        self.assertEqual(self.row()["state"], "CANCELLED")
        self.assertFalse(self.agent.calls)

    def test_new_task_uses_green_local_binding(self):
        event = task()
        self.bridge.bind()
        self.ingest(event)
        self.settle()
        request = self.agent.calls[0][0]
        self.assertNotIn("repository", request)
        self.assertNotIn("scope_profile", request)

    def test_general_task_changed_system_result_is_delivered_as_pass(self):
        self.agent.outputs = [{"output": output(local_modification_tested=True,
                                               local_modification_outcome="PASS"), "dirty": False}]
        self.bridge.bind()
        self.ingest(general_task())
        self.settle()
        self.bridge.flush()
        event = self.client.sent[-1][1]
        self.assertEqual(event["status"], "PASS")
        self.assertTrue(event["local_modification_tested"])
        self.assertNotIn("revision", event)

    def test_general_task_runs_without_revision_and_returns_revisionless_result(self):
        event = general_task()
        self.bridge.bind()
        self.ingest(event)
        self.settle()
        self.bridge.flush()
        request = self.agent.calls[0][0]
        self.assertNotIn("revision", request)
        result = next(sent for _, sent in self.client.sent if sent["type"] == "RESULT")
        self.assertNotIn("revision", result)

    def test_multi_page_after_and_empty_bootstrap(self):
        self.bridge.bind()
        for i in range(1, 206):
            self.client.rows.append(message(task(event_id=f"e{i}", task_id=f"t{i}"), i))
        self.bridge.catch_up()
        self.assertEqual(self.bridge.store.db.execute("SELECT count(*) FROM tasks").fetchone()[0], 205)
        for i in range(206, 412):
            self.client.rows.append(message(task(event_id=f"e{i}", task_id=f"t{i}"), i))
        self.bridge.catch_up()
        self.assertEqual(self.bridge.store.db.execute("SELECT count(*) FROM tasks").fetchone()[0], 411)

    def test_epoch_reset_rebinds_without_replaying_and_accepts_next_command(self):
        self.bridge.bind()
        self.client.epoch += 1
        with self.assertLogs("cross_zone.controller", level="WARNING") as logs:
            self.ingest(task())
        self.assertIsNone(self.row())
        self.assertIn("resend", " ".join(logs.output))
        self.assertEqual(self.bridge.store.get_meta("cursor")["epoch"], self.client.epoch)
        self.ingest(task(task_id="after-reset", event_id="after-reset"))
        self.settle()
        self.assertEqual(self.bridge.store.get_task("after-reset", 1)["state"], "PASS")
        self.assertEqual(len(self.agent.calls), 1)

    def test_epoch_reset_preserves_completed_task_outbox_and_recovery(self):
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        pending = [tuple(row) for row in self.bridge.store.db.execute("SELECT * FROM outbox")]
        with self.bridge.store.db:
            self.bridge.store.set_meta("recovery_required", True)
            self.bridge.store.set_meta("recovery_tasks", [{"task_id": "interrupted", "iteration": 1}])
        self.client.epoch += 1
        self.bridge.catch_up()
        self.assertEqual(self.row()["state"], "PASS")
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))
        self.assertEqual(self.bridge.store.get_meta("recovery_tasks"), [{"task_id": "interrupted", "iteration": 1}])
        self.assertEqual(pending, [tuple(row) for row in self.bridge.store.db.execute("SELECT * FROM outbox")])
        self.ingest(task(event_id="retry-after-reset"))
        self.settle()
        self.assertEqual(len(self.agent.calls), 1)
        self.bridge.flush()
        self.assertTrue(any(event["type"] == "RESULT" for _, event in self.client.sent))

    def test_deleted_state_fresh_open_survives_later_epoch_reset(self):
        import shutil
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.bridge.close()
        shutil.rmtree(self.cfg["state_dir"])
        self.agent = FakeAgent()
        self.bridge = Bridge(self.cfg, self.client, self.agent)
        self.bridge.bind()
        self.assertIsNone(self.row())  # Existing history is not replayed after deletion.
        self.client.epoch += 1
        self.bridge.catch_up()
        self.ingest(task(task_id="fresh", event_id="fresh"))
        self.settle()
        self.assertEqual(self.bridge.store.get_task("fresh", 1)["state"], "PASS")
        self.assertEqual(len(self.agent.calls), 1)

    def test_server_reset_flag_rebinds_even_without_epoch_change(self):
        self.bridge.bind()
        self.client.rows.append(message(task(), 1))
        response = self.client.messages(self.cfg["session_id"], limit=100)
        response["page"]["reset"] = True
        with patch.object(self.client, "messages", return_value=response):
            self.bridge.catch_up()
        self.assertIsNone(self.row())
        self.assertEqual(self.bridge.store.get_meta("cursor")["seq"], 1)

    def test_bootstrap_epoch_reset_rebinds_without_partial_history_execution(self):
        self.bridge.bind()
        for seq in range(1, 106):
            self.client.rows.append(message(task(task_id=f"history-{seq}", event_id=f"history-{seq}"), seq))
        original = self.client.messages
        def reset_during_bootstrap(session, **query):
            if "beforeSeq" in query:
                self.client.epoch = 1
            return original(session, **query)
        with patch.object(self.client, "messages", side_effect=reset_during_bootstrap):
            self.bridge.catch_up()
        self.assertEqual(self.bridge.store.db.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)
        self.assertEqual(self.bridge.store.get_meta("cursor"), {"at": 105000, "seq": 105, "epoch": 1})
        self.ingest(task())
        self.settle()
        self.assertEqual(self.row()["state"], "PASS")

    def test_epoch_reset_does_not_cancel_active_worker(self):
        started, release = threading.Event(), threading.Event()
        def running(*args):
            started.set()
            release.wait(2)
            return {"output": output()}
        self.agent.run = running
        self.bridge.bind()
        self.ingest(task())
        self.bridge.work()
        self.assertTrue(started.wait(1))
        current = self.bridge.active
        try:
            self.client.epoch += 1
            self.bridge.catch_up()
            self.assertIs(self.bridge.active, current)
            self.assertFalse(next(iter(current.values()))[1].is_set())
        finally:
            release.set()
        self.settle()
        self.assertEqual(self.row()["state"], "PASS")

    def test_listener_continues_after_epoch_reset_and_returns_next_result(self):
        self.bridge.bind()
        self.client.epoch += 1
        deadline = time.monotonic() + 3
        sent = False
        def next_tick(_timeout):
            nonlocal sent
            if not sent:
                self.client.rows.append(message(task(), 1))
                sent = True
            if any(event["type"] == "RESULT" for _, event in self.client.sent) or time.monotonic() > deadline:
                self.bridge.stop.set()
            time.sleep(0.01)
        with patch.object(self.bridge.wake, "wait", side_effect=next_tick):
            self.bridge.run()
        self.assertEqual(len(self.agent.calls), 1)
        self.assertTrue(any(event["type"] == "RESULT" and event["status"] == "PASS"
                            for _, event in self.client.sent))

    def test_outbox_offline_retry_same_id(self):
        self.bridge.bind()
        self.ingest(task())
        self.client.fail_send = True
        with self.assertRaises(HapiError):
            self.bridge.flush()
        row = self.bridge.store.db.execute("SELECT * FROM outbox").fetchone()
        self.assertFalse(row["sent"])
        self.client.fail_send = False
        self.bridge.flush()
        self.assertEqual(self.client.sent[0][0], row["id"])

    def test_question_answer_resume(self):
        self.agent.outputs = [{"output": output(kind="QUESTION", status="BLOCKED", question="Which approved fixture?"),
                               "session_id": "green-id", "dirty": False},
                              {"output": output(), "session_id": "green-id", "dirty": False}]
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.assertEqual(self.row()["state"], "WAITING_ANSWER")
        question_id = self.row()["question_id"]
        self.ingest(self.control("ANSWER", question_id="wrong", answer="fixture-a"))
        self.assertEqual(self.row()["state"], "WAITING_ANSWER")
        self.ingest(self.control("ANSWER", question_id=question_id, answer="fixture-a"))
        self.settle()
        self.assertEqual(self.agent.calls[1][1:3], ("green-id", "fixture-a"))
        self.assertEqual(self.row()["state"], "PASS")

    def test_cancel_queued_and_wait_timeout(self):
        self.bridge.bind()
        self.ingest(task())
        self.ingest(self.control("CANCEL"))
        self.settle()
        self.assertEqual(self.row()["state"], "CANCELLED")
        self.assertFalse(self.agent.calls)

    def test_cancel_running_waits_for_worker(self):
        started = threading.Event()

        def waiting(request, session_id, answer, deadline, cancel, recovery):
            started.set()
            if not cancel.wait(3):
                return {"failure": "test_wait_expired", "status": "NEEDS_HUMAN"}
            return {"failure": "cancelled", "status": "CANCELLED"}

        self.agent.run = waiting
        self.bridge.bind()
        self.ingest(task())
        self.bridge.work()
        self.assertTrue(started.wait(1))
        self.ingest(self.control("CANCEL"))
        self.assertEqual(self.row()["state"], "CANCELLING")
        self.settle()
        self.assertEqual(self.row()["state"], "CANCELLED")

    def test_waiting_question_deadline(self):
        self.bridge.bind()
        self.ingest(task())
        with self.bridge.store.db:
            self.bridge.store.update(self.row(), state="WAITING_ANSWER", deadline=time.time() - 1)
        self.bridge.work()
        self.assertEqual(self.row()["state"], "TIMED_OUT")
        self.assertFalse(self.agent.calls)

    def test_question_budget_and_unconfirmed_termination(self):
        self.bridge.config["max_questions"] = 0
        self.agent.outputs[0] = {"output": output(kind="QUESTION", status="BLOCKED", question="Fixture?"),
                                 "session_id": "green", "dirty": False}
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.assertEqual(self.row()["state"], "NEEDS_HUMAN")
        self.agent.outputs.append({"failure": "termination_unconfirmed", "status": "NEEDS_HUMAN", "pause": True})
        self.ingest(task(event_id="next", iteration=2))
        self.settle()
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))

    def test_inbox_and_cursor_rollback_together(self):
        self.bridge.bind()
        initial = self.bridge.store.get_meta("cursor")
        self.client.rows.extend([message(task(), 1), message(task(event_id="next", task_id="task-2"), 2)])
        real_accept = self.bridge._accept

        def fail_second(event):
            if event["task_id"] == "task-2":
                raise RuntimeError("simulated crash")
            real_accept(event)

        with patch.object(self.bridge, "_accept", fail_second), self.assertRaises(RuntimeError):
            self.bridge.catch_up()
        self.assertEqual(self.bridge.store.get_meta("cursor"), initial)
        self.assertIsNone(self.row())
        self.bridge.catch_up()
        self.assertEqual(self.row()["state"], "QUEUED")
        self.assertIsNotNone(self.bridge.store.get_task("task-2", 1))

    def test_recovery_inspects_queued_work_without_rerunning_interrupted_task(self):
        self.bridge.bind()
        self.ingest(task())
        with self.bridge.store.db:
            self.bridge.store.update(self.row(), state="RUNNING")
        self.bridge.close()
        self.bridge = Bridge(self.cfg, self.client, self.agent)
        self.assertTrue(self.bridge.store.recover())
        self.settle()
        self.assertEqual(self.row()["state"], "NEEDS_HUMAN")
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))
        self.assertFalse(self.agent.calls)
        self.bridge.flush()
        result = self.client.sent[-1][1]
        self.assertIn("Bridge restarted while task state was RUNNING", result["detail"])
        self.assertIn("surviving processes", result["detail"])
        self.assertIn("No manual recovery acknowledgement", result["detail"])
        self.ingest(task(event_id="after-restart", iteration=2))
        self.settle()
        self.assertEqual(self.row()["state"], "NEEDS_HUMAN")
        self.assertEqual(self.bridge.store.get_task("task-1", 2)["state"], "PASS")
        self.assertEqual(len(self.agent.calls), 1)
        self.assertEqual(self.agent.calls[0][0]["iteration"], 2)
        self.assertEqual(self.agent.calls[0][5], [{"task_id": "task-1", "iteration": 1}])
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))

    def test_recovery_migrates_old_global_pause_and_only_clears_after_valid_evidence(self):
        self.bridge.bind()
        self.ingest(task())
        with self.bridge.store.db:
            self.bridge.store.update(self.row(), state="NEEDS_HUMAN")
            self.bridge.store.set_meta("recovery_required", True)
        self.bridge.store.recover()
        self.assertEqual(self.bridge.store.get_meta("recovery_tasks"),
                         [{"task_id": "task-1", "iteration": 1}])
        # An invalid/unsafe result must not release recovery, even if it claims success.
        self.agent.outputs = [{"output": output(question="invalid"), "recovery_checked": True},
                              {"output": output(), "recovery_checked": True},
                              {"output": output()}]
        self.ingest(task(event_id="check-2", iteration=2))
        self.settle()
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))
        self.ingest(task(event_id="check-3", iteration=3))
        self.settle()
        self.assertFalse(self.bridge.store.get_meta("recovery_required"))
        self.assertEqual(self.bridge.store.get_meta("recovery_tasks"), [])
        self.ingest(task(event_id="check-4", iteration=4))
        self.settle()
        self.assertEqual(self.agent.calls[-1][5], [])

    def test_termination_uncertainty_allows_followup_diagnostics(self):
        self.bridge.bind()
        self.agent.outputs = [{"failure": "termination_unconfirmed", "status": "NEEDS_HUMAN", "pause": True},
                              {"output": output(status="BLOCKED", checks=[{"id": "regression", "status": "BLOCKED"}]),
                               "recovery_checked": False}]
        self.ingest(task())
        self.settle()
        self.ingest(task(event_id="diagnostics", iteration=2))
        self.settle()
        self.assertEqual(len(self.agent.calls), 2)
        self.assertTrue(self.bridge.store.get_meta("recovery_required"))
        self.assertEqual(self.bridge.store.get_task("task-1", 2)["state"], "BLOCKED")

    def test_scope_and_revision_control_rejected(self):
        self.bridge.bind()
        self.ingest(task(repository="unknown"))
        self.assertIsNone(self.row())
        self.ingest(task(event_id="good"))
        self.ingest(self.control("CANCEL", revision="b" * 40))
        self.assertEqual(self.row()["state"], "QUEUED")

    def test_dirty_pass_rejected(self):
        self.agent.outputs[0]["dirty"] = True
        self.bridge.bind()
        self.ingest(task())
        self.settle()
        self.assertEqual(self.row()["state"], "NEEDS_HUMAN")

    def test_changed_session_cannot_reuse_state(self):
        other = {**self.cfg, "session_id": "other"}
        with self.assertRaises(ValueError):
            Bridge(other, self.client)

    def test_instance_lock(self):
        with InstanceLock(self.cfg["state_dir"]):
            with self.assertRaises(ValueError):
                with InstanceLock(self.cfg["state_dir"]):
                    pass


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.auth_count = 0
        self.fail_token_once = False
        self.backend = FakeClient()
        self.posted = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                owner.requests.append((self.path, self.headers.get("Authorization"), json.loads(body) if body else None))
                if self.path == "/hapi/api/auth":
                    owner.auth_count += 1
                    self.send_json(200, {"token": "jwt-" + str(owner.auth_count)})
                elif owner.fail_token_once:
                    owner.fail_token_once = False
                    self.send_json(401, {})
                elif self.path.startswith("/hapi/api/events"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    self.wfile.write(b'id: 1\ndata: {"type":"message"}\n\n')
                elif self.path == "/hapi/api/sessions":
                    self.send_json(200, {"sessions": [{"id": "blue", "active": True}]})
                elif self.path.startswith("/hapi/api/sessions/blue/messages"):
                    if self.command == "POST":
                        owner.posted.append(json.loads(body))
                        self.send_json(200, {"ok": True})
                    else:
                        query = {k: int(v[0]) for k, v in parse_qs(urlsplit(self.path).query).items()}
                        self.send_json(200, owner.backend.messages("blue", **query))
                elif self.path == "/hapi/api/redirect":
                    self.send_response(302)
                    self.send_header("Location", "/must-not-follow")
                    self.end_headers()
                else:
                    self.send_json(404, {})

            do_GET = handle_request
            do_POST = handle_request

            def send_json(self, status, value):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = HapiClient(f"http://127.0.0.1:{self.server.server_port}/hapi/", "test-access-key")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_auth_prefix_refresh_and_send(self):
        self.fail_token_once = True
        self.assertEqual(self.client.sessions()[0]["id"], "blue")
        self.assertEqual(self.auth_count, 2)
        self.client.send("blue", "test", "stable-id")
        path, auth, body = self.requests[-1]
        self.assertEqual(path, "/hapi/api/sessions/blue/messages")
        self.assertEqual(auth, "Bearer jwt-2")
        self.assertEqual(body, {"text": "test", "localId": "stable-id", "deliveryMode": "queue"})

    def test_pagination_queries(self):
        self.client.messages("blue", limit=100, afterAt=1000, afterSeq=1, epoch=0)
        query = parse_qs(urlsplit(self.requests[-1][0]).query)
        self.assertEqual(query["afterAt"], ["1000"])

    def test_redirect_not_followed(self):
        with self.assertRaises(HapiError):
            self.client.request("redirect")
        self.assertFalse(any(r[0] == "/must-not-follow" for r in self.requests))

    def test_sse_wakeup_header_auth(self):
        wake, stop = threading.Event(), threading.Event()
        thread = threading.Thread(target=self.client.listen, args=("blue", wake, stop))
        thread.start()
        try:
            self.assertTrue(wake.wait(3))
        finally:
            stop.set()
            thread.join(3)
        path, auth, _ = next(r for r in self.requests if "/events?" in r[0])
        self.assertNotIn("token=", path)
        self.assertEqual(auth, "Bearer jwt-1")


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = config(self.tmp.name)
        self.repo = Path(self.cfg["workspace_dir"])
        self.repo.mkdir()
        subprocess.run(["git", "init", str(self.repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "--allow-empty", "-m", "baseline"], check=True, capture_output=True)
        self.revision = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin", str(self.repo)],
                       check=True, capture_output=True)
        self.script = Path(self.tmp.name) / "fake_cli.py"
        self.cfg["agent_command"] = [sys.executable, str(self.script)]

    def tearDown(self):
        self.tmp.cleanup()

    def run_agent(self, code, deadline=None, cancel=None):
        self.script.write_text(code, encoding="utf-8")
        return CodeAgentCLI(self.cfg).run(task(revision=self.revision), None, None,
                                          deadline or time.time() + 10, cancel or threading.Event())

    def test_stdin_json_permissions_and_no_hapi_key_in_child(self):
        previous = os.environ.get("HAPI_ACCESS_KEY")
        os.environ["HAPI_ACCESS_KEY"] = "test-secret"
        try:
            result = self.run_agent("import sys,json,os\n"
                                    "assert 'HAPI_ACCESS_KEY' not in os.environ\n"
                                    "assert 'dontAsk' in sys.argv and '--dangerously-skip-permissions' not in sys.argv\n"
                                    "assert '--skip-safe-check' in sys.argv\n"
                                    "assert '--allow-dangerously-skip-permissions' in sys.argv\n"
                                    "assert sys.argv[sys.argv.index('--output-format') + 1] == 'stream-json'\n"
                                    "assert '--verbose' in sys.argv\n"
                                    "assert '--max-turns' not in sys.argv\n"
                                    "assert 'cross-zone/v3' in sys.stdin.read()\n"
                                    + "print(" + repr(json.dumps({"structured_output": output(), "session_id": "green"})) + ")\n")
            self.assertEqual(result["output"]["status"], "PASS")
            self.assertFalse(result["dirty"])
        finally:
            if previous is None:
                os.environ.pop("HAPI_ACCESS_KEY", None)
            else:
                os.environ["HAPI_ACCESS_KEY"] = previous

    def test_recovery_context_is_in_prompt_and_private_flag_is_not_exported(self):
        self.script.write_text("import sys,json\n"
                               "prompt = sys.stdin.read()\n"
                               "assert 'Bridge recovery' in prompt\n"
                               "assert 'never kill a process from its PID alone' in prompt\n"
                               "assert 'interrupted-task' in prompt\n"
                               "schema = json.loads(sys.argv[sys.argv.index('--json-schema') + 1])\n"
                               "assert 'recovery_checked' in schema['required']\n"
                               + "print(" + repr(json.dumps({"structured_output": output(recovery_checked=True)})) + ")\n",
                               encoding="utf-8")
        result = CodeAgentCLI(self.cfg).run(general_task(), None, None, time.time() + 10,
                                            threading.Event(), [{"task_id": "interrupted-task", "iteration": 1}])
        self.assertTrue(result["recovery_checked"])
        self.assertNotIn("recovery_checked", result["output"])
        self.assertEqual(review(result["output"], general_task())["status"], "PASS")

    def test_stream_json_is_logged_locally_and_final_result_is_parsed(self):
        events = [
            {"type": "system", "subtype": "init", "session_id": "green"},
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Checking the requested revision"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "python -m pytest"}},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": "tests completed"},
            ]}},
            {"type": "result", "subtype": "success", "structured_output": output()},
        ]
        code = "import json,sys\nsys.stdin.read()\n"
        code += "\n".join("print(" + repr(json.dumps(event)) + ", flush=True)" for event in events)
        with self.assertLogs("cross_zone.agent", level="INFO") as logs:
            result = self.run_agent(code)
        self.assertEqual(result["output"]["status"], "PASS")
        combined = "\n".join(logs.output)
        self.assertIn("Agent session initialized", combined)
        self.assertIn("Checking the requested revision", combined)
        self.assertIn("Agent tool Bash", combined)
        self.assertIn("tests completed", combined)
        self.assertIn("Agent completed: success", combined)

    def test_agent_stdin_and_live_output_preserve_chinese_under_legacy_encoding(self):
        text = "检查成功，服务器可访问"
        event = {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}
        result_event = {"type": "result", "subtype": "success", "structured_output": output(summary=text)}
        code = "import sys,json\nsys.stdin.read()\n"
        code += "print(json.dumps(" + repr(event) + ", ensure_ascii=False), flush=True)\n"
        code += "print(json.dumps(" + repr(result_event) + ", ensure_ascii=False), flush=True)\n"
        with patch.dict(os.environ, {"PYTHONIOENCODING": "gbk", "PYTHONUTF8": "0"}), self.assertLogs("cross_zone.agent", level="INFO") as logs:
            result = self.run_agent(code)
        self.assertEqual(result["output"]["summary"], text)
        self.assertIn(text, "\n".join(logs.output))

    def test_codeagent_structured_output_tool_is_used_as_result(self):
        events = [
            {"type": "system", "subtype": "init", "session_id": "green-session"},
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "StructuredOutput", "input": output()},
            ]}},
            {"type": "user", "message": {"content": [
                {"type": "tool_result", "content": "Structured output provided successfully"},
            ]}},
            {"type": "result", "subtype": "success", "is_error": False},
        ]
        code = "import json,sys\nsys.stdin.read()\n"
        code += "\n".join("print(" + repr(json.dumps(event)) + ", flush=True)" for event in events)
        result = self.run_agent(code)
        self.assertEqual(result["output"], output())
        self.assertEqual(result["session_id"], "green-session")

    def test_live_log_can_be_disabled(self):
        self.cfg["agent_live_log"] = False
        event = {"type": "result", "subtype": "success", "structured_output": output()}
        result = self.run_agent("import json\nprint(" + repr(json.dumps(event)) + ")\n")
        self.assertEqual(result["output"]["status"], "PASS")

    def test_full_http_to_cli_to_http_result(self):
        hub = HttpTests()
        hub.setUp()
        self.cfg["hub_url"] = hub.client.base.removesuffix("api/")
        self.cfg["session_id"] = "blue"
        self.script.write_text("import sys\nsys.stdin.read()\nprint(" +
                               repr(json.dumps({"structured_output": output(), "session_id": "green"})) + ")\n")
        bridge = Bridge(self.cfg, hub.client)
        try:
            bridge.bind()
            hub.backend.rows.append(message(task(revision=self.revision), 1))
            bridge.catch_up()
            for _ in range(200):
                bridge.work()
                if not bridge.active:
                    break
                time.sleep(0.01)
            bridge.flush()
            events = [read_wire(p["text"]) for p in hub.posted]
            self.assertEqual([e["type"] for e in events], ["PROGRESS", "RESULT"])
            self.assertEqual(events[-1]["status"], "PASS")
            self.assertEqual(events[-1]["revision"], self.revision)
        finally:
            bridge.close()
            hub.tearDown()

    def test_timeout_and_cancel(self):
        result = self.run_agent("import time\ntime.sleep(30)\n", deadline=time.time() + 0.2)
        self.assertEqual(result["status"], "TIMED_OUT")
        self.assertIn("deadline", result["detail"])
        cancel = threading.Event()
        cancel.set()
        result = self.run_agent("import time\ntime.sleep(30)\n", cancel=cancel)
        self.assertEqual(result["status"], "CANCELLED")

    def test_already_cancelled_or_expired_never_launches_cli(self):
        marker = Path(self.tmp.name) / "launched"
        code = "from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(self.run_agent(code, cancel=cancel)["status"], "CANCELLED")
        self.assertFalse(marker.exists())
        expired = self.run_agent(code, deadline=time.time() - 1)
        self.assertEqual(expired["status"], "TIMED_OUT")
        self.assertIn("before the CLI launched", expired["detail"])
        self.assertFalse(marker.exists())

    def test_revision_and_dirty_baseline_block(self):
        result = CodeAgentCLI(self.cfg).run(task(), None, None, time.time() + 10, threading.Event())
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.run_agent("import json\nprint(" +
                                        repr(json.dumps({"structured_output": output()})) + ")\n")["output"]["status"],
                         "PASS")
        checkout = Path(self.cfg["state_dir"]) / "checkouts" / "task-1" / "1"
        (checkout / "dirty.txt").write_text("uncommitted")
        result = self.run_agent("raise Exception('should not launch')\n")
        self.assertEqual(result["status"], "BLOCKED")

    def test_general_task_runs_in_session_directory_without_git_checkout(self):
        event = general_task()
        self.script.write_text("import json,sys,os\nsys.stdin.read()\n"
                               + "assert os.getcwd() == " + repr(str(Path(self.cfg["state_dir"]).resolve())) + "\n"
                               + "print(" +
                               repr(json.dumps({"structured_output": output()})) + ")\n",
                               encoding="utf-8")
        result = CodeAgentCLI(self.cfg).run(
            event,
            None,
            None,
            time.time() + 10,
            threading.Event(),
        )
        self.assertEqual(result["output"]["status"], "PASS")
        self.assertFalse((Path(self.cfg["state_dir"]) / "checkouts").exists())

    def test_agent_failure_does_not_export_stdout(self):
        with self.assertLogs("cross_zone.agent", level="ERROR") as logs:
            result = self.run_agent("print('protected source text')\n")
        self.assertNotIn("protected", str(result))
        self.assertEqual(result["status"], "NEEDS_HUMAN")
        self.assertEqual(result["failure"], "agent_output_protocol_error")
        self.assertIn("JSONDecodeError", "\n".join(logs.output))

    def test_missing_agent_executable_has_specific_error_and_local_guidance(self):
        self.cfg["agent_command"] = [str(Path(self.tmp.name) / "missing-codeagent.exe")]
        with self.assertLogs("cross_zone.agent", level="ERROR") as logs:
            result = CodeAgentCLI(self.cfg).run(
                task(revision=self.revision), None, None,
                time.time() + 10, threading.Event(),
            )
        self.assertEqual(result["failure"], "agent_executable_not_found")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("agent_command[0]", result["detail"])
        combined = "\n".join(logs.output)
        self.assertIn("agent_executable_not_found", combined)
        self.assertIn("agent_command[0]", combined)

    def test_runtime_failure_includes_exception_type_and_message(self):
        with patch("cross_zone.agent._read_agent_result", side_effect=RuntimeError("agent_output_reader_stuck")):
            result = self.run_agent("print('{}')\n")
        self.assertEqual(result["failure"], "agent_runtime_error")
        self.assertIn("RuntimeError: agent_output_reader_stuck", result["detail"])

    def test_nonzero_agent_exit_includes_subtype_and_bounded_stderr(self):
        code = ("import sys,json\nprint(json.dumps({'type':'result','subtype':'error_max_turns'}))\n"
                "sys.stderr.write('old line\\n' * 20 + 'runtime diagnostic\\n')\nsys.exit(1)\n")
        result = self.run_agent(code)
        self.assertIn("error_max_turns", result["detail"])
        self.assertIn("runtime diagnostic", result["detail"])
        self.assertEqual(result["detail"].count("old line"), 7)

    def test_nonzero_agent_exit_reports_exit_code_locally(self):
        with self.assertLogs("cross_zone.agent", level="ERROR") as logs:
            result = self.run_agent("import sys\nsys.exit(7)\n")
        self.assertEqual(result["failure"], "agent_exit_nonzero")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("code 7", result["detail"])
        self.assertIn("code 7", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
