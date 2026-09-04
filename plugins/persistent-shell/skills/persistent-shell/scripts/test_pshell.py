import errno
import importlib.util
import multiprocessing
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import paramiko


SCRIPT = Path(__file__).with_name("pshell.py")
SPEC = importlib.util.spec_from_file_location("pshell_under_test", SCRIPT)
pshell = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pshell
SPEC.loader.exec_module(pshell)
pshell.paramiko = paramiko


def hold_daemon_start_lock(lock_path, attempting, acquired, release):
    pshell.START_LOCK_FILE = Path(lock_path)
    attempting.set()
    with pshell.daemon_start_lock():
        acquired.set()
        release.wait(5)


class JsonProtocolTests(unittest.TestCase):
    def test_json_line_round_trip(self):
        left, right = socket.socketpair()
        try:
            left.sendall(pshell.json_bytes({"ok": True, "text": "value"}))
            self.assertEqual(pshell.recv_json(right), {"ok": True, "text": "value"})
        finally:
            left.close()
            right.close()


class HostKeyPolicyTests(unittest.TestCase):
    def test_first_key_preserves_file_and_changed_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            known_hosts = Path(directory) / "known_hosts"
            known_hosts.write_text("# retained comment\n", encoding="ascii")
            original = pshell.KNOWN_HOSTS
            pshell.KNOWN_HOSTS = known_hosts
            try:
                first = paramiko.RSAKey.generate(1024)
                second = paramiko.RSAKey.generate(1024)
                client = paramiko.SSHClient()
                pshell.SaveNewHostKey().missing_host_key(client, "example.internal", first)
                content = known_hosts.read_text(encoding="ascii")
                self.assertTrue(content.startswith("# retained comment\n"))
                self.assertIn("example.internal ssh-rsa ", content)
                with self.assertRaises(paramiko.BadHostKeyException):
                    pshell.SaveNewHostKey().missing_host_key(client, "example.internal", second)
            finally:
                pshell.KNOWN_HOSTS = original


class ParserTests(unittest.TestCase):
    def test_exec_timeout_before_target(self):
        args = pshell.build_parser().parse_args(
            ["exec", "--timeout", "0.5", "host", "--", "printf", "hello"]
        )
        self.assertEqual(args.timeout, 0.5)
        self.assertEqual(args.target, "host")
        self.assertEqual(args.command, ["printf", "hello"])


class SessionLookupTests(unittest.TestCase):
    def test_existing_session_does_not_resolve_ssh_config_again(self):
        daemon = pshell.Daemon()
        retained = object()
        daemon.sessions["host"] = retained
        original = pshell.resolve_target
        pshell.resolve_target = lambda _message: self.fail("existing session was resolved again")
        try:
            self.assertIs(daemon.session({"target": "host"}, create=False), retained)
        finally:
            pshell.resolve_target = original


class DaemonStartupTests(unittest.TestCase):
    def test_windows_file_lock_retries_contention_until_acquired(self):
        calls = []

        def fake_locking(descriptor, mode, size):
            calls.append((descriptor, mode, size))
            lock_attempts = sum(call[1] == 1 for call in calls)
            if mode == 1 and lock_attempts < 3:
                raise OSError(errno.EACCES, "locked")

        fake_msvcrt = types.SimpleNamespace(
            LK_NBLCK=1,
            LK_UNLCK=2,
            locking=fake_locking,
        )
        with tempfile.TemporaryFile() as stream:
            with mock.patch.dict(sys.modules, {"msvcrt": fake_msvcrt}), mock.patch.object(
                pshell.time, "sleep"
            ) as sleep:
                pshell.lock_start_file(stream, platform="nt")
                pshell.unlock_start_file(stream, platform="nt")
            descriptor = stream.fileno()

        self.assertEqual(
            calls,
            [(descriptor, 1, 1), (descriptor, 1, 1), (descriptor, 1, 1), (descriptor, 2, 1)],
        )
        self.assertEqual(sleep.call_count, 2)

    def test_start_lock_serializes_processes(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "daemon-start.lock"
            first_attempting = context.Event()
            first_acquired = context.Event()
            first_release = context.Event()
            second_attempting = context.Event()
            second_acquired = context.Event()
            second_release = context.Event()
            first = context.Process(
                target=hold_daemon_start_lock,
                args=(lock_path, first_attempting, first_acquired, first_release),
            )
            second = context.Process(
                target=hold_daemon_start_lock,
                args=(lock_path, second_attempting, second_acquired, second_release),
            )
            first.start()
            self.assertTrue(first_attempting.wait(3))
            self.assertTrue(first_acquired.wait(3))
            second.start()
            try:
                self.assertTrue(second_attempting.wait(3))
                self.assertFalse(second_acquired.wait(0.2))
                first_release.set()
                self.assertTrue(second_acquired.wait(3))
                second_release.set()
                first.join(3)
                second.join(3)
                self.assertEqual(first.exitcode, 0)
                self.assertEqual(second.exitcode, 0)
            finally:
                first_release.set()
                second_release.set()
                for process in (first, second):
                    if process.is_alive():
                        process.terminate()
                    process.join()

    def test_old_daemon_cleanup_cannot_remove_replacement_state(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory) / "pshell"
            state_file = app_dir / "daemon.json"
            lock_file = app_dir / "daemon-start.lock"
            app_dir.mkdir()
            original_app_dir = pshell.APP_DIR
            original_state_file = pshell.STATE_FILE
            original_lock_file = pshell.START_LOCK_FILE
            pshell.APP_DIR = app_dir
            pshell.STATE_FILE = state_file
            pshell.START_LOCK_FILE = lock_file
            try:
                pshell.write_state({"pid": 1, "port": 2, "token": "old"})
                original_read_state = pshell.read_state
                old_state_read = threading.Event()
                allow_cleanup = threading.Event()
                replacement_written = threading.Event()

                def paused_read_state():
                    state = original_read_state()
                    old_state_read.set()
                    allow_cleanup.wait(3)
                    return state

                def publish_replacement():
                    with pshell.daemon_start_lock():
                        pshell.write_state({"pid": 2, "port": 3, "token": "new"})
                    replacement_written.set()

                with mock.patch.object(
                    pshell, "read_state", side_effect=paused_read_state
                ):
                    cleanup = threading.Thread(
                        target=pshell.remove_owned_state, args=(1,)
                    )
                    replacement = threading.Thread(target=publish_replacement)
                    cleanup.start()
                    self.assertTrue(old_state_read.wait(3))
                    replacement.start()
                    try:
                        self.assertFalse(replacement_written.wait(0.2))
                    finally:
                        allow_cleanup.set()
                    cleanup.join(3)
                    replacement.join(3)

                self.assertFalse(cleanup.is_alive())
                self.assertFalse(replacement.is_alive())
                self.assertTrue(replacement_written.is_set())
                self.assertEqual(pshell.read_state()["pid"], 2)
            finally:
                pshell.APP_DIR = original_app_dir
                pshell.STATE_FILE = original_state_file
                pshell.START_LOCK_FILE = original_lock_file

    def test_concurrent_requests_start_only_one_daemon(self):
        workers = 6
        barrier = threading.Barrier(workers)
        state_lock = threading.Lock()
        state = None
        starts = 0

        def fake_read_state():
            with state_lock:
                return state

        def fake_start_daemon():
            nonlocal starts, state
            with state_lock:
                starts += 1
            time.sleep(0.05)
            with state_lock:
                state = {"pid": 1, "port": 2, "token": "test"}

        def fake_request_with_state(_state, action, _payload, _response_timeout=None):
            return {"action": action}

        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(
                pshell,
                "START_LOCK_FILE",
                Path(directory) / "daemon-start.lock",
                create=True,
            ), mock.patch.object(
                pshell, "read_state", side_effect=fake_read_state
            ), mock.patch.object(
                pshell, "start_daemon", side_effect=fake_start_daemon
            ), mock.patch.object(
                pshell,
                "request_with_state",
                side_effect=fake_request_with_state,
            ):
                def request_at_once():
                    barrier.wait()
                    return pshell.request("ping")

                with ThreadPoolExecutor(max_workers=workers) as executor:
                    results = list(
                        executor.map(lambda _index: request_at_once(), range(workers))
                    )

        self.assertEqual(starts, 1)
        self.assertEqual(results, [{"action": "ping"}] * workers)


if __name__ == "__main__":
    unittest.main()
