import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
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
from cross_zone.cli import InstanceLock, error_hint, safe_error_detail, select_session
from cross_zone.config import load_config
from cross_zone.controller import Bridge, CursorReset
from cross_zone.egress import review
from cross_zone.hapi import HapiClient, HapiError
from cross_zone.protocol import MARKER, ProtocolError, assistant_text, open_event, parse, wire


def task(**changes):
    event = {"protocol": "cross-zone/v2", "type": "TASK", "event_id": "blue-1", "task_id": "task-1",
             "iteration": 1, "target": "green-dev", "revision": "a" * 40, "repository": "candidate",
             "scope_profile": "isolated-test", "goal": "Run the regression",
             "checks": [{"id": "regression", "action": "Run approved tests", "expected": "All pass"}],
             "timeout_seconds": 30}
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
        self.sent.append((event_id, json.loads(text[len(MARKER):])))


class FakeAgent:
    def __init__(self, outputs=None):
        self.calls = []
        self.outputs = outputs or [{"output": output(), "session_id": "session-green", "dirty": False}]

    def run(self, *args):
        self.calls.append(args)
        return self.outputs.pop(0)


def config(directory):
    return {"hub_url": "http://localhost/hapi/", "session_id": "blue-session",
            "target": "green-dev", "state_dir": str(Path(directory) / "state"), "sse": False,
            "max_task_seconds": 30, "max_questions": 3, "poll_seconds": 0.1, "agent_command": ["codeagent"],
            "agent_live_log": True, "agent_log_max_chars": 2000,
            "task_binding": {"repository": "candidate", "scope_profile": "isolated-test"},
            "repositories": {"candidate": {"cwd": str(Path(directory) / "repo"), "remote": "origin",
                                               "profiles": ["isolated-test"]}},
            "profiles": {"isolated-test": {"allowed_tools": ["Read"], "instructions": "Read-only tests"}},
            "egress_deny_patterns": []}


class OpenTests(unittest.TestCase):
    def test_open_event_is_green_only(self):
        event = open_event("green-dev", "sessions/19146292-52a4-4094-9cd5-6086b0c3ec05")
        self.assertEqual(event["protocol"], "cross-zone/v2")
        self.assertEqual(event["type"], "OPEN")
        self.assertEqual(event["target"], "green-dev")
        self.assertIn(event["session_url"], event["session_url"])
        self.assertIn("green-open-", event["event_id"])
        # Blue cannot inject an OPEN envelope; it must be green-originated.
        with self.assertRaises(ProtocolError):
            parse(wire(event), "green-dev")


class GitBashLauncherTests(unittest.TestCase):
    def test_launcher_forwards_command_and_config_to_py(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_py = root / "py"
            capture = root / "capture.txt"
            config_path = root / "green config.json"
            config_path.write_text("{}", encoding="utf-8")
            fake_py.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE\"\n", encoding="utf-8")
            fake_py.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = str(root) + os.pathsep + env["PATH"]
            env["CAPTURE"] = str(capture)
            env["BRIDGE_LOG_DIR"] = str(root / "logs")
            session_id = "19146292-52a4-4094-9cd5-6086b0c3ec05"
            launcher = Path(__file__).parents[1] / "start-bridge.sh"
            result = subprocess.run(["bash", str(launcher), "doctor", session_id, str(config_path)],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(capture.read_text(encoding="utf-8").splitlines(),
                             ["-3", "-m", "cross_zone", "--config", str(config_path),
                              "--session", session_id, "doctor"])
            log_path = root / "logs" / ("bridge-doctor-" + session_id + ".log")
            self.assertTrue(log_path.is_file())
            self.assertIn("Bridge log:", log_path.read_text(encoding="utf-8"))

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
            for field in ("session_id", "session_url", "state_dir", "key_env"):
                value.pop(field, None)
            path = Path(directory) / "config.local.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            loaded = load_config(path)
            self.assertEqual(loaded["access_key"], "local-config-secret")
            self.assertEqual(safe_error_detail(ValueError("bad local-config-secret"),
                                               (loaded["access_key"],)),
                             "bad [REDACTED]")

    def test_config_rejects_session_and_state_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            for field in ("session_id", "session_url", "state_dir", "key_env"):
                value = config(directory)
                for runtime_field in ("session_id", "state_dir"):
                    value.pop(runtime_field, None)
                value[field] = "obsolete"
                path = Path(directory) / (field + ".json")
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "deprecated"):
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
    def test_roundtrip_codex_and_claude(self):
        for flavor in ("codex", "output"):
            self.assertEqual(parse(assistant_text(message(task(), 1, flavor)), "green-dev"), task())

    def test_new_task_omits_green_local_aliases(self):
        event = task()
        event.pop("repository")
        event.pop("scope_profile")
        self.assertEqual(parse(wire(event), "green-dev"), event)

    def test_general_task_and_controls_omit_revision(self):
        event = general_task(repository="candidate", scope_profile="isolated-test")
        self.assertEqual(parse(wire(event), "green-dev"), event)
        cancel = {"protocol": "cross-zone/v2", "type": "CANCEL", "event_id": "cancel-1",
                  "task_id": event["task_id"], "iteration": 1, "target": "green-dev"}
        self.assertEqual(parse(wire(cancel), "green-dev"), cancel)

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
        self.assertIsNone(parse("Example:\n" + wire(task()), "green-dev"))
        self.assertIsNone(parse("```json\n" + wire(task()) + "\n```", "green-dev"))
        self.assertIsNone(parse(wire(task(target="another")), "green-dev"))

    def test_malformed_envelopes_reject(self):
        variants = [task(iteration=True), task(revision="main"), task(timeout_seconds=-1),
                    task(checks=[]), task(task_id="../../escape"), task(extra="field"), task(type=[])]
        for event in variants:
            with self.subTest(event=event), self.assertRaises(ProtocolError):
                parse(wire(event), "green-dev")
        with self.assertRaises(ProtocolError):
            parse(MARKER + '{"protocol":"cross-zone/v2","protocol":"bad"}', "green-dev")


class EgressTests(unittest.TestCase):
    def test_pass_and_failed_local_fix(self):
        self.assertEqual(review(output(), task())["status"], "PASS")
        value = output(status="FAIL", local_modification_tested=True, local_modification_outcome="PASS",
                       checks=[{"id": "regression", "status": "FAIL"}])
        self.assertEqual(review(value, task())["status"], "FAIL")

    def test_reject_protected_output(self):
        for summary in ["http://internal.example", "192.168.1.1", "C:\\work\\secret", "```python", "/root/key", "password=example"]:
            with self.subTest(summary=summary), self.assertRaises(ValueError):
                review(output(summary=summary), task())
        with self.assertRaises(ValueError):
            review(output(summary="contains test-secret"), task(), secrets=["test-secret"])
        with self.assertRaises(ValueError):
            review(output(summary="projectX info"), task(), deny_patterns=["projectX"])

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
            if not self.bridge.current:
                return
            time.sleep(0.01)
        self.fail("worker did not settle")

    def row(self):
        return self.bridge.store.get_task("task-1", 1)

    def control(self, kind, **fields):
        base = {k: v for k, v in task().items() if k in {"protocol", "task_id", "iteration", "target", "revision"}}
        return {**base, "type": kind, "event_id": "control-" + str(len(self.client.rows)), **fields}

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

    def test_new_task_uses_green_local_binding(self):
        event = task()
        event.pop("repository")
        event.pop("scope_profile")
        self.bridge.bind()
        self.ingest(event)
        self.settle()
        request = self.agent.calls[0][0]
        self.assertEqual(request["repository"], "candidate")
        self.assertEqual(request["scope_profile"], "isolated-test")

    def test_general_task_runs_without_revision_and_returns_revisionless_result(self):
        event = general_task()
        event.pop("repository")
        event.pop("scope_profile")
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

    def test_epoch_reset_does_not_advance_or_execute(self):
        self.bridge.bind()
        self.client.epoch += 1
        with self.assertRaises(CursorReset):
            self.ingest(task())
        self.assertIsNone(self.row())

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

        def waiting(request, session_id, answer, deadline, cancel):
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

    def test_recovery_pauses_and_does_not_rerun(self):
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
        self.repo = Path(self.cfg["repositories"]["candidate"]["cwd"])
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
                                    "assert 'cross-zone/v2' in sys.stdin.read()\n"
                                    + "print(" + repr(json.dumps({"structured_output": output(), "session_id": "green"})) + ")\n")
            self.assertEqual(result["output"]["status"], "PASS")
            self.assertFalse(result["dirty"])
        finally:
            if previous is None:
                os.environ.pop("HAPI_ACCESS_KEY", None)
            else:
                os.environ["HAPI_ACCESS_KEY"] = previous

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
                if not bridge.current:
                    break
                time.sleep(0.01)
            bridge.flush()
            events = [json.loads(p["text"][len(MARKER):]) for p in hub.posted]
            self.assertEqual([e["type"] for e in events], ["ACK", "PROGRESS", "RESULT"])
            self.assertEqual(events[-1]["status"], "PASS")
            self.assertEqual(events[-1]["revision"], self.revision)
        finally:
            bridge.close()
            hub.tearDown()

    def test_timeout_and_cancel(self):
        result = self.run_agent("import time\ntime.sleep(30)\n", deadline=time.time() + 0.2)
        self.assertEqual(result["status"], "TIMED_OUT")
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
        self.assertEqual(self.run_agent(code, deadline=time.time() - 1)["status"], "TIMED_OUT")
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

    def test_general_task_runs_in_authorized_workspace_without_git_checkout(self):
        event = general_task()
        self.script.write_text("import json,sys\nsys.stdin.read()\nprint(" +
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
        result = self.run_agent("print('protected source text')\n")
        self.assertNotIn("protected", str(result))
        self.assertEqual(result["status"], "NEEDS_HUMAN")


if __name__ == "__main__":
    unittest.main()
