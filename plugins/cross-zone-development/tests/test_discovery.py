"""Discovery integration regressions: real Bridge, isolated multi-session HAPI."""

import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from cross_zone.cli import InstanceLock, main
from cross_zone.controller import Bridge
from cross_zone.discovery import Discovery
from cross_zone.hapi import HapiError
from cross_zone.protocol import PROTOCOL, read_wire, wire
from test_bridge import FakeAgent, FakeClient, config, general_task, message, output


OWNER = "19146292-52a4-4094-9cd5-6086b0c3ec05"
OTHER = "fc85951c-ffeb-4fb3-b44f-ae052e9106f6"


def connection(kind="OPEN", event_id="open-1", **changes):
    return {"protocol": PROTOCOL, "type": kind, "event_id": event_id, **changes}


class MultiSessionHapi:
    access_key = FakeClient.access_key
    token = FakeClient.token

    def __init__(self):
        self.backends = {sid: FakeClient() for sid in (OWNER, OTHER)}
        self.attempts = []

    def sessions(self):
        return [{"id": sid, "active": True} for sid in self.backends]

    def messages(self, session, **query):
        return self.backends[session].messages(session, **query)

    def send(self, session, text, event_id):
        self.attempts.append((session, event_id, read_wire(text)))
        self.backends[session].send(session, text, event_id)

    def append(self, event, session=OWNER, mutate=None, historical=False):
        rows = self.backends.setdefault(session, FakeClient()).rows
        row = message(event, len(rows) + 1)
        # Keep timestamps ordered and use wall time for discovery's startup filter.
        row["createdAt"] = 1 if historical else int(time.time() * 1000) + len(rows)
        if mutate:
            mutate(row)
        rows.append(row)

    def replies(self, session=OWNER):
        return [event for _, event in self.backends[session].sent]


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = config(self.tmp.name)
        self.cfg.pop("session_id")
        self.cfg["state_dir"] = str(Path(self.tmp.name) / ".state" / "discovery")
        self.client = MultiSessionHapi()
        self.agent = FakeAgent()
        self.created = []
        self.discovery = None
        self.addCleanup(self.shutdown)
        self.restart()

    def shutdown(self):
        if self.discovery is not None:
            self.discovery.close()
            self.discovery = None

    def restart(self):
        self.shutdown()

        def factory(cfg, client):
            bridge = Bridge(cfg, client, agent=self.agent)
            self.created.append(bridge)
            return bridge

        self.discovery = Discovery(self.cfg, self.client, InstanceLock, factory)

    def start(self):
        self.discovery.tick()

    def send(self, kind="OPEN", event_id="open-1", session=OWNER):
        self.client.append(connection(kind, event_id), session)
        self.discovery.tick()

    def assert_reply(self, kind, request, session=OWNER):
        event = self.client.replies(session)[-1]
        self.assertEqual(event["type"], kind)
        self.assertEqual(event["request_event_id"], request)
        self.assertEqual(event["session_url"], "sessions/" + session)
        return event

    def settle(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.discovery.tick()
            if not self.discovery.bridge.active:
                return
            time.sleep(0.005)
        self.fail("fake agent did not settle")

    def test_baseline_skips_historical_open_then_new_open_is_ready(self):
        self.client.append(connection(event_id="historical"), historical=True)
        self.start()
        self.assertIsNone(self.discovery.bridge)
        self.assertEqual(self.client.replies(), [])
        self.send()
        self.assert_reply("READY", "open-1")
        self.assertEqual(self.discovery.bridge.config["session_id"], OWNER)
        self.assertEqual(self.agent.calls, [])

    def test_competing_session_busy_does_not_disclose_owner(self):
        self.start()
        self.send()
        self.send(event_id="other-open", session=OTHER)
        reply = self.assert_reply("BUSY", "other-open", OTHER)
        self.assertNotIn(OWNER, json.dumps(reply))
        self.assertEqual(len(self.created), 1)

    def test_new_session_bootstrap_finds_open_before_large_message_burst(self):
        self.start()
        new_session = "7ff9a609-b248-4294-97ef-159fbd012bbe"
        self.client.append(connection(event_id="old-new-session-open"), new_session, historical=True)
        self.client.append(connection(event_id="fresh-new-session-open"), new_session)
        for index in range(105):
            self.client.append({"type": "ordinary", "index": index}, new_session)
        self.discovery.tick()
        self.assert_reply("READY", "fresh-new-session-open", new_session)
        self.assertEqual(len(self.client.replies(new_session)), 1)

    def test_interrupted_saved_task_requires_recovery_without_reexecution(self):
        self.start()
        self.send()
        self.discovery.bridge.max_concurrent_tasks = 0
        self.client.append(general_task())
        self.discovery.tick()
        store = self.discovery.bridge.store
        with store.db:
            store.update(store.get_task("task-1", 1), state="RUNNING")
        self.restart()
        self.start()
        store = self.discovery.bridge.store
        self.assertEqual(store.get_task("task-1", 1)["state"], "NEEDS_HUMAN")
        self.assertTrue(store.get_meta("recovery_required"))
        self.assertEqual(self.agent.calls, [])
        self.send("CLOSE", "close-interrupted")
        self.assert_reply("BUSY", "close-interrupted")

    def test_same_session_open_preserves_waiting_task_and_cursor(self):
        self.agent.outputs = [{"output": output(kind="QUESTION", status="NEEDS_HUMAN", question="Which host?"),
                               "session_id": "green-question", "dirty": False}]
        self.start()
        self.send()
        self.client.append(general_task())
        self.settle()
        bridge = self.discovery.bridge
        self.assertEqual(bridge.store.get_task("task-1", 1)["state"], "WAITING_ANSWER")
        bound_at = bridge.store.get_meta("bound_at")
        self.send(event_id="open-again")
        self.assert_reply("READY", "open-again")
        self.assertIs(self.discovery.bridge, bridge)
        self.assertEqual(bridge.store.get_meta("bound_at"), bound_at)
        self.assertEqual(bridge.store.get_task("task-1", 1)["state"], "WAITING_ANSWER")
        self.send("CLOSE", "close-waiting")
        self.assert_reply("BUSY", "close-waiting")
        self.assertEqual(len(self.agent.calls), 1)

    def test_close_busy_while_task_running_then_idle_release_next_open(self):
        release = threading.Event()
        entered = threading.Event()
        agent = self.agent
        original = agent.run

        def run(*args):
            entered.set()
            release.wait(3)
            return original(*args)

        agent.run = run
        self.addCleanup(release.set)
        self.start()
        self.send()
        self.client.append(general_task())
        self.client.append(connection("CLOSE", "close-running"))
        self.discovery.tick()
        self.assertTrue(entered.wait(1))
        self.assert_reply("BUSY", "close-running")
        release.set()
        self.settle()
        self.send("CLOSE", "close-idle")
        self.assert_reply("CLOSED", "close-idle")
        self.assertIsNone(self.discovery.bridge)
        with InstanceLock(Path(self.cfg["state_dir"]).parent / OWNER):
            pass
        self.send(event_id="next-open", session=OTHER)
        self.assert_reply("READY", "next-open", OTHER)

    def test_close_busy_with_queued_task(self):
        self.start()
        self.send()
        self.discovery.bridge.max_concurrent_tasks = 0
        self.client.append(general_task())
        self.send("CLOSE", "close-queued")
        self.assert_reply("BUSY", "close-queued")
        self.assertEqual(self.discovery.bridge.store.get_task("task-1", 1)["state"], "QUEUED")
        self.assertEqual(self.agent.calls, [])

    def test_failed_owner_catchup_cannot_release_unaccepted_work(self):
        self.start()
        self.send()
        self.discovery.bridge.max_concurrent_tasks = 0
        self.client.append(general_task())
        self.client.append(connection("CLOSE", "close-after-failed-read"))
        with patch.object(self.discovery.bridge, "catch_up", side_effect=HapiError(503)):
            self.discovery.tick()
        self.assertIsNotNone(self.discovery.bridge)
        self.assertEqual(self.client.replies()[-1]["type"], "READY")
        self.discovery.tick()
        self.assert_reply("BUSY", "close-after-failed-read")
        self.assertEqual(self.discovery.bridge.store.get_task("task-1", 1)["state"], "QUEUED")

    def test_close_catches_task_arriving_between_worker_and_discovery_reads(self):
        self.start()
        self.send()
        self.discovery.bridge.max_concurrent_tasks = 0
        original_sessions = self.client.sessions

        def arrivals():
            self.client.append(general_task())
            self.client.append(connection("CLOSE", "close-racing-task"))
            return original_sessions()

        with patch.object(self.client, "sessions", side_effect=arrivals):
            self.discovery.tick()
        self.assert_reply("BUSY", "close-racing-task")
        self.assertIsNotNone(self.discovery.bridge)
        self.assertEqual(self.discovery.bridge.store.get_task("task-1", 1)["state"], "QUEUED")

    def test_close_defers_until_worker_cursor_reaches_close(self):
        self.start()
        self.send()
        self.discovery.tick()
        self.client.append(connection("CLOSE", "close-not-caught-up"))
        with patch.object(self.discovery.bridge, "catch_up"):
            self.discovery.tick()
        self.assertIsNotNone(self.discovery.bridge)
        self.assertEqual(self.client.replies()[-1]["type"], "READY")
        self.discovery.tick()
        self.assert_reply("CLOSED", "close-not-caught-up")

    def test_failed_reply_backlog_does_not_starve_other_sessions(self):
        self.start()
        self.client.backends[OTHER].fail_send = True
        for index in range(25):
            self.client.append(connection("CLOSE", "unbound-close-" + str(index)), OTHER)
        self.discovery.tick()
        self.assertEqual(self.client.replies(OTHER), [])
        self.send()
        self.assert_reply("READY", "open-1")

    def test_close_busy_with_pending_result_and_unresolved_recovery(self):
        self.start()
        self.send()
        self.client.backends[OWNER].fail_send = True
        self.client.append(general_task())
        self.settle()
        self.send("CLOSE", "close-result")
        self.assertTrue(self.discovery.bridge.store.db.execute("SELECT 1 FROM outbox WHERE sent=0").fetchone())
        self.client.backends[OWNER].fail_send = False
        self.discovery.tick()
        self.assert_reply("BUSY", "close-result")
        with self.discovery.bridge.store.db:
            self.discovery.bridge.store.set_meta("recovery_required", True)
        self.send("CLOSE", "close-recovery")
        self.assert_reply("BUSY", "close-recovery")

    def test_binding_and_failed_ready_reply_survive_restart(self):
        self.start()
        self.client.backends[OWNER].fail_send = True
        self.send()
        failed = copy.deepcopy(self.client.attempts[-1])
        self.assertEqual(self.client.replies(), [])
        self.restart()
        self.client.backends[OWNER].fail_send = False
        self.start()
        self.assertEqual(self.client.attempts[-1], failed)
        self.assert_reply("READY", "open-1")
        self.assertEqual(self.discovery.bridge.config["session_id"], OWNER)
        self.send()
        self.assertEqual(len(self.client.replies()), 1)

    def test_completed_task_and_unsent_result_not_executed_again_after_restart(self):
        self.start()
        self.send()
        self.client.backends[OWNER].fail_send = True
        request = general_task()
        self.client.append(request)
        self.settle()
        self.assertEqual(self.discovery.bridge.store.get_task("task-1", 1)["state"], "PASS")
        pending = self.discovery.bridge.store.db.execute("SELECT id FROM outbox WHERE sent=0").fetchall()
        self.restart()
        self.client.backends[OWNER].fail_send = False
        self.start()
        self.client.append(request)
        self.discovery.tick()
        self.assertEqual(len(self.agent.calls), 1)
        results = [e for e in self.client.replies() if e["type"] == "RESULT"]
        self.assertEqual(len(results), 1)
        sent_ids = {event_id for event_id, _ in self.client.backends[OWNER].sent}
        self.assertTrue(all(row[0] in sent_ids for row in pending))

    def test_duplicate_and_conflicting_connection_ids_do_not_close_binding(self):
        self.start()
        self.send()
        self.send()
        self.send("CLOSE", "open-1")
        self.assertEqual(len(self.client.replies()), 1)
        self.assertEqual(len(self.created), 1)
        self.assertIsNotNone(self.discovery.bridge)

    def test_existing_explicit_session_lock_returns_busy_then_allows_retry(self):
        self.start()
        with InstanceLock(Path(self.cfg["state_dir"]).parent / OWNER):
            self.send()
            self.assert_reply("BUSY", "open-1")
            self.assertIsNone(self.discovery.bridge)
        self.send(event_id="retry-open")
        self.assert_reply("READY", "retry-open")

    def test_bound_session_lock_is_held_and_reacquired_after_restart(self):
        self.start()
        self.send()
        directory = Path(self.cfg["state_dir"]).parent / OWNER
        for restart in (False, True):
            with self.subTest(restart=restart):
                if restart:
                    self.restart()
                    self.start()
                with self.assertRaisesRegex(ValueError, "Another bridge owns"):
                    with InstanceLock(directory):
                        pass
        self.send("CLOSE", "release-lock")
        self.assert_reply("CLOSED", "release-lock")
        with InstanceLock(directory):
            pass
        self.send(event_id="reopen-same-session")
        self.assert_reply("READY", "reopen-same-session")
        self.assertEqual(self.discovery.bridge.config["session_id"], OWNER)

    def test_restart_preserves_waiting_task_and_close_remains_busy(self):
        self.agent.outputs = [{"output": output(kind="QUESTION", status="NEEDS_HUMAN", question="Which host?"),
                               "session_id": "green-question", "dirty": False}]
        self.start()
        self.send()
        self.client.append(general_task())
        self.settle()
        before = dict(self.discovery.bridge.store.get_task("task-1", 1))
        self.restart()
        self.start()
        after = dict(self.discovery.bridge.store.get_task("task-1", 1))
        for field in ("state", "session_id", "question_id", "questions"):
            self.assertEqual(after[field], before[field])
        self.send("CLOSE", "close-after-restart")
        self.assert_reply("BUSY", "close-after-restart")
        self.assertEqual(len(self.agent.calls), 1)

    def test_malformed_user_tool_and_sidechain_envelopes_are_ignored(self):
        self.start()
        mutations = [
            lambda row: row["content"].update(role="user"),
            lambda row: row["content"]["content"]["data"].update(type="tool_result"),
            lambda row: row["content"]["content"]["data"].update(isSidechain=True),
            lambda row: row["content"]["content"]["data"].update(scope_role="subagent"),
        ]
        for mutate in mutations:
            self.client.append(connection(), mutate=mutate)
        for event in (connection(extra="not-allowed"), connection(event_id="../bad"),
                      connection(protocol="wrong"), {"protocol": PROTOCOL, "type": "OPEN"}):
            self.client.append(event)
        self.discovery.tick()
        self.assertIsNone(self.discovery.bridge)
        self.assertEqual(self.client.replies(), [])
        self.send(event_id="valid-after-invalid")
        self.assert_reply("READY", "valid-after-invalid")

    def test_non_string_connection_type_is_ignored_without_stopping_scan(self):
        self.start()
        for kind in ([], {}, ["OPEN"]):
            self.client.append(connection(type=kind))
        self.send(event_id="valid-after-malformed-type")
        self.assert_reply("READY", "valid-after-malformed-type")


class DefaultDiscoveryCliTests(unittest.TestCase):
    def test_no_command_selects_discovery_without_session(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(directory)
            cfg["access_key"] = "test-key"
            with patch("sys.argv", ["cross_zone", "--config", str(Path(directory) / "green.json")]), \
                    patch("cross_zone.cli.load_config", return_value=cfg), \
                    patch("cross_zone.cli.configure_console"), \
                    patch("cross_zone.cli.logging.basicConfig"), \
                    patch("cross_zone.cli.preflight"), \
                    patch("cross_zone.cli.HapiClient"), \
                    patch("cross_zone.cli.Discovery") as discovery:
                main()
            discovery.return_value.run.assert_called_once_with()
            actual = discovery.call_args.args[0]
            self.assertEqual(Path(actual["state_dir"]), Path(directory) / ".state" / "discovery")

    def test_default_shell_launcher_passes_discover_without_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = root / "args.json"
            launcher = root / "py"
            launcher.write_text("#!/usr/bin/env python3\nimport json,os,sys\n"
                                "with open(os.environ['DISCOVERY_CAPTURE'], 'w') as f: json.dump(sys.argv[1:], f)\n")
            launcher.chmod(0o755)
            # Copy the launcher so its default config and logs stay in the fixture.
            plugin = Path(__file__).parents[1]
            script = (plugin / "start-bridge.sh").read_text()
            copied = root / "start-bridge.sh"
            copied.write_text(script)
            (root / "config.local.json").write_text("{}")
            result = subprocess.run(["bash", str(copied)], cwd=root, capture_output=True, text=True,
                                    timeout=5, env={**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"],
                                                   "DISCOVERY_CAPTURE": str(capture), "BRIDGE_LOG_DIR": str(root / "logs")})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(capture.read_text()),
                             ["-3", "-m", "cross_zone", "--config", "config.local.json",
                              "--workspace", str(root), "discover"])


if __name__ == "__main__":
    unittest.main()
