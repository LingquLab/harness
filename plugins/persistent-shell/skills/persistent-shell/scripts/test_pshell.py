import importlib.util
import socket
import sys
import tempfile
import unittest
from pathlib import Path

import paramiko


SCRIPT = Path(__file__).with_name("pshell.py")
SPEC = importlib.util.spec_from_file_location("pshell_under_test", SCRIPT)
pshell = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pshell
SPEC.loader.exec_module(pshell)
pshell.paramiko = paramiko


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


if __name__ == "__main__":
    unittest.main()
