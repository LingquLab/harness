#!/usr/bin/env python3
"""Persistent SSH shell client and per-user local daemon."""

from __future__ import annotations

import argparse
import base64
import errno
import getpass
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, BinaryIO, Dict, Iterator, List, Optional, Tuple

paramiko: Any = None
if len(sys.argv) > 1 and sys.argv[1] == "_serve":
    try:
        import paramiko as _paramiko

        paramiko = _paramiko
    except ImportError as exc:
        print("pshell requires Paramiko in its Python environment", file=sys.stderr)
        raise SystemExit(2) from exc


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "pshell"
STATE_FILE = APP_DIR / "daemon.json"
LOG_FILE = APP_DIR / "daemon.log"
START_LOCK_FILE = APP_DIR / "daemon-start.lock"
KNOWN_HOSTS = Path.home() / ".ssh" / "known_hosts"
MAX_MESSAGE = 16 * 1024 * 1024
DEFAULT_TIMEOUT = 60.0
DAEMON_PING_TIMEOUT = 1.0
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


class PshellError(RuntimeError):
    pass


class DaemonRequestError(PshellError):
    pass


def json_bytes(value: Dict[str, Any]) -> bytes:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
    if len(data) > MAX_MESSAGE:
        raise PshellError("message exceeds 16 MiB")
    return data


def recv_json(sock: socket.socket) -> Dict[str, Any]:
    data = bytearray()
    while b"\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            raise PshellError("connection closed before response")
        data.extend(chunk)
        if len(data) > MAX_MESSAGE:
            raise PshellError("message exceeds 16 MiB")
    try:
        result = json.loads(data.split(b"\n", 1)[0].decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PshellError(f"invalid JSON response: {exc}") from exc
    if not isinstance(result, dict):
        raise PshellError("response is not a JSON object")
    return result


def read_state() -> Optional[Dict[str, Any]]:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(state.get("port"), int) and isinstance(state.get("token"), str):
            return state
    except (OSError, ValueError, AttributeError):
        pass
    return None


def write_state(state: Dict[str, Any]) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(temporary, STATE_FILE)


def request_with_state(
    state: Dict[str, Any],
    action: str,
    payload: Optional[Dict[str, Any]],
    response_timeout: Optional[float] = None,
) -> Dict[str, Any]:
    message = {"token": state["token"], "action": action, **(payload or {})}
    timeout = response_timeout or max(DEFAULT_TIMEOUT + 10, float(message.get("timeout", 0)) + 10)
    with socket.create_connection(("127.0.0.1", state["port"]), timeout=min(3, timeout)) as sock:
        sock.settimeout(timeout)
        sock.sendall(json_bytes(message))
        response = recv_json(sock)
    if not response.get("ok"):
        raise DaemonRequestError(str(response.get("error", "daemon request failed")))
    return response


def start_daemon() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), "_serve"]
    with LOG_FILE.open("ab", buffering=0) as log:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            close_fds=True,
            creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        )


def lock_start_file(stream: BinaryIO, platform: str = os.name) -> None:
    stream.seek(0, os.SEEK_END)
    if stream.tell() == 0:
        stream.write(b"\0")
        stream.flush()
    stream.seek(0)
    if platform == "nt":
        import msvcrt

        while True:
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                time.sleep(0.1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def unlock_start_file(stream: BinaryIO, platform: str = os.name) -> None:
    stream.seek(0)
    if platform == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def daemon_start_lock() -> Iterator[None]:
    START_LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with START_LOCK_FILE.open("a+b") as stream:
        lock_start_file(stream)
        try:
            yield
        finally:
            unlock_start_file(stream)


def ensure_daemon() -> Dict[str, Any]:
    with daemon_start_lock():
        state = read_state()
        if state:
            try:
                request_with_state(state, "ping", None, DAEMON_PING_TIMEOUT)
                return state
            except DaemonRequestError:
                raise
            except (OSError, PshellError):
                pass

        start_daemon()
        deadline = time.monotonic() + 8
        last_error = "daemon state was not published"
        while time.monotonic() < deadline:
            state = read_state()
            if state:
                try:
                    request_with_state(state, "ping", None, DAEMON_PING_TIMEOUT)
                    return state
                except DaemonRequestError:
                    raise
                except (OSError, PshellError) as exc:
                    last_error = str(exc)
            time.sleep(0.1)
    raise PshellError(f"daemon startup failed: {last_error}; see {LOG_FILE}")


def request(action: str, payload: Optional[Dict[str, Any]] = None, start: bool = True) -> Dict[str, Any]:
    state = read_state()
    if state:
        try:
            return request_with_state(state, action, payload)
        except DaemonRequestError:
            raise
        except (OSError, PshellError):
            pass
    if not start:
        raise PshellError("pshell daemon is not running")
    return request_with_state(ensure_daemon(), action, payload)


def remove_owned_state(pid: int) -> None:
    with daemon_start_lock():
        state = read_state()
        if state and state.get("pid") == pid:
            try:
                STATE_FILE.unlink()
            except OSError:
                pass


def expand_path(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value))


@dataclass(frozen=True)
class Target:
    name: str
    hostname: str
    user: str
    port: int
    identities: Tuple[str, ...]
    connect_timeout: float
    keepalive: int

    def describe(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "hostname": self.hostname,
            "user": self.user,
            "port": self.port,
            "identities": list(self.identities),
        }


def resolve_target(message: Dict[str, Any]) -> Target:
    raw = str(message.get("target", "")).strip()
    if not raw:
        raise PshellError("target is required")
    lookup = raw
    explicit_user = message.get("user")
    if "@" in raw:
        parsed_user, lookup = raw.rsplit("@", 1)
        explicit_user = explicit_user or parsed_user

    values: Dict[str, Any] = {}
    config_file = Path.home() / ".ssh" / "config"
    if config_file.exists():
        config = paramiko.SSHConfig()
        with config_file.open(encoding="utf-8") as stream:
            config.parse(stream)
        values = config.lookup(lookup)
    if values.get("proxycommand") or values.get("proxyjump"):
        raise PshellError("ProxyCommand and ProxyJump are not supported")

    identity = message.get("identity")
    configured = values.get("identityfile", [])
    if isinstance(configured, str):
        configured = [configured]
    identities = [expand_path(str(identity))] if identity else [expand_path(str(item)) for item in configured]
    identities = [item for item in identities if Path(item).exists()]
    return Target(
        name=raw,
        hostname=str(values.get("hostname", lookup)),
        user=str(explicit_user or values.get("user") or getpass.getuser()),
        port=int(message.get("port") or values.get("port") or 22),
        identities=tuple(identities),
        connect_timeout=float(values.get("connecttimeout", 10)),
        keepalive=int(values.get("serveraliveinterval", 30)),
    )


class SaveNewHostKey:
    """Trust a key only when no key is retained for this host name."""

    _lock = threading.Lock()

    def missing_host_key(self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey) -> None:
        with self._lock:
            KNOWN_HOSTS.parent.mkdir(parents=True, exist_ok=True)
            host_keys = paramiko.HostKeys()
            if KNOWN_HOSTS.exists():
                host_keys.load(str(KNOWN_HOSTS))
            existing = host_keys.lookup(hostname)
            if existing:
                raise paramiko.BadHostKeyException(hostname, key, next(iter(existing.values())))
            original = KNOWN_HOSTS.read_bytes() if KNOWN_HOSTS.exists() else b""
            separator = b"" if not original or original.endswith(b"\n") else b"\n"
            new_line = f"{hostname} {key.get_name()} {key.get_base64()}\n".encode("ascii")
            temporary = KNOWN_HOSTS.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_bytes(original + separator + new_line)
            os.replace(temporary, KNOWN_HOSTS)
            client.get_host_keys().add(hostname, key.get_name(), key)


class Session:
    def __init__(self, target: Target) -> None:
        self.target = target
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None
        self.lock = threading.Lock()
        self.generation = 0
        self.connected_at: Optional[float] = None
        self.last_used: Optional[float] = None

    def close(self) -> None:
        channel, client = self.channel, self.client
        self.channel = None
        self.client = None
        if channel:
            channel.close()
        if client:
            client.close()

    def connect(self) -> None:
        self.close()
        client = paramiko.SSHClient()
        if KNOWN_HOSTS.exists():
            client.load_host_keys(str(KNOWN_HOSTS))
        client.set_missing_host_key_policy(SaveNewHostKey())
        options: Dict[str, Any] = {
            "hostname": self.target.hostname,
            "port": self.target.port,
            "username": self.target.user,
            "timeout": self.target.connect_timeout,
            "banner_timeout": self.target.connect_timeout,
            "auth_timeout": self.target.connect_timeout,
            "allow_agent": True,
            "look_for_keys": not self.target.identities,
        }
        if self.target.identities:
            options["key_filename"] = list(self.target.identities)
        try:
            client.connect(**options)
            transport = client.get_transport()
            if not transport or not transport.is_active():
                raise PshellError("SSH transport is not active")
            transport.set_keepalive(self.target.keepalive)
            channel = transport.open_session()
            channel.set_combine_stderr(True)
            channel.exec_command(
                "if command -v bash >/dev/null 2>&1; "
                "then exec bash --noprofile --norc; else exec sh; fi"
            )
            channel.settimeout(0.2)
            self.client, self.channel = client, channel
            self.initialize_shell()
        except Exception:
            client.close()
            raise
        self.generation += 1
        self.connected_at = self.last_used = time.time()

    def initialize_shell(self) -> None:
        assert self.channel
        marker = f"__PSHELL_READY_{uuid.uuid4().hex}__".encode()
        command = b"printf '" + marker + b"\\n'\n"
        self.channel.sendall(command)
        self.read_until(marker, 10)
        self.drain()

    def read_until(self, marker: bytes, timeout: float) -> bytes:
        assert self.channel
        deadline = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < deadline:
            if self.channel.recv_ready():
                chunk = self.channel.recv(65536)
                if not chunk:
                    raise PshellError("remote shell closed")
                data.extend(chunk)
                if len(data) > MAX_MESSAGE:
                    raise PshellError("output exceeds 16 MiB")
                index = data.find(marker)
                if index >= 0:
                    return bytes(data[:index])
            elif self.channel.closed:
                raise PshellError("remote shell closed")
            else:
                time.sleep(0.01)
        raise TimeoutError(f"operation timed out after {timeout:g}s")

    def drain(self) -> None:
        assert self.channel
        while self.channel.recv_ready():
            self.channel.recv(65536)

    def ensure_connected(self) -> bool:
        transport = self.client.get_transport() if self.client else None
        if self.channel and not self.channel.closed and transport and transport.is_active():
            return False
        reset = self.generation > 0
        self.connect()
        return reset

    def execute(self, command: str, timeout: float) -> Dict[str, Any]:
        if not command.strip():
            raise PshellError("command is empty")
        with self.lock:
            reset = self.ensure_connected()
            assert self.channel
            self.drain()
            tag = uuid.uuid4().hex
            marker = f"__PSHELL_RESULT_{tag}:"
            pattern = re.compile(re.escape(marker.encode()) + rb"([0-9]+)__")
            payload = command.rstrip("\r\n") + f"\n__pshell_rc=$?; printf '{marker}%s__\\n' \"$__pshell_rc\"\n"
            self.channel.sendall(payload.encode())
            deadline = time.monotonic() + timeout
            data = bytearray()
            try:
                while time.monotonic() < deadline:
                    if self.channel.recv_ready():
                        chunk = self.channel.recv(65536)
                        if not chunk:
                            raise PshellError("remote shell closed")
                        data.extend(chunk)
                        if len(data) > MAX_MESSAGE:
                            raise PshellError("output exceeds 16 MiB")
                        match = pattern.search(data)
                        if match:
                            output = bytes(data[: match.start()]).replace(b"\r\n", b"\n")
                            self.last_used = time.time()
                            return {
                                "output": base64.b64encode(output).decode(),
                                "exit_code": int(match.group(1)),
                                "generation": self.generation,
                                "state_reset": reset,
                            }
                    elif self.channel.closed:
                        raise PshellError("remote shell closed")
                    else:
                        time.sleep(0.01)
                raise TimeoutError(f"command timed out after {timeout:g}s; shell was discarded")
            except Exception:
                self.close()
                raise

    def status(self) -> Dict[str, Any]:
        transport = self.client.get_transport() if self.client else None
        connected = bool(self.channel and not self.channel.closed and transport and transport.is_active())
        return {
            **self.target.describe(),
            "connected": connected,
            "generation": self.generation,
            "connected_at": self.connected_at,
            "last_used": self.last_used,
        }


class Daemon:
    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)
        self.sessions: Dict[str, Session] = {}
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        self.server: Optional[socket.socket] = None

    def session(self, message: Dict[str, Any], create: bool) -> Session:
        name = str(message.get("target", ""))
        with self.lock:
            session = self.sessions.get(name)
        if session or not create:
            if not session:
                raise PshellError(f"no session named {name!r}; run 'pshell start {name}' first")
            return session
        candidate = Session(resolve_target(message))
        with self.lock:
            return self.sessions.setdefault(name, candidate)

    def dispatch(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if not secrets.compare_digest(str(message.get("token", "")), self.token):
            raise PshellError("authentication failed")
        action = message.get("action")
        if action == "ping":
            return {"pid": os.getpid()}
        if action == "start":
            session = self.session(message, create=True)
            with session.lock:
                reset = session.ensure_connected()
                return {"session": session.status(), "state_reset": reset}
        if action == "exec":
            return self.session(message, create=False).execute(
                str(message.get("command", "")), float(message.get("timeout", DEFAULT_TIMEOUT))
            )
        if action == "status":
            name = message.get("target")
            with self.lock:
                if name:
                    session = self.sessions.get(str(name))
                    if not session:
                        raise PshellError(f"no session named {name!r}")
                    return {"sessions": [session.status()]}
                return {"sessions": [session.status() for session in self.sessions.values()]}
        if action == "stop":
            name = str(message.get("target", ""))
            with self.lock:
                session = self.sessions.pop(name, None)
            if not session:
                raise PshellError(f"no session named {name!r}")
            session.close()
            return {"stopped": [name]}
        if action == "stop_all":
            with self.lock:
                sessions, self.sessions = self.sessions, {}
            for session in sessions.values():
                session.close()
            return {"stopped": list(sessions)}
        if action == "daemon_stop":
            self.stopping.set()
            if self.server:
                self.server.close()
            return {"stopping": True}
        raise PshellError(f"unknown action {action!r}")

    def handle(self, conn: socket.socket, address: Tuple[str, int]) -> None:
        with conn:
            try:
                if address[0] != "127.0.0.1":
                    raise PshellError("non-loopback client rejected")
                conn.settimeout(DEFAULT_TIMEOUT + 15)
                response = {"ok": True, **self.dispatch(recv_json(conn))}
            except Exception as exc:
                response = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            try:
                conn.sendall(json_bytes(response))
            except OSError:
                pass

    def serve(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(16)
        server.settimeout(0.5)
        self.server = server
        write_state({"pid": os.getpid(), "port": server.getsockname()[1], "token": self.token, "started_at": time.time()})
        try:
            while not self.stopping.is_set():
                try:
                    conn, address = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self.handle, args=(conn, address), daemon=True).start()
        finally:
            with self.lock:
                sessions, self.sessions = self.sessions, {}
            for session in sessions.values():
                session.close()
            server.close()
            remove_owned_state(os.getpid())


def target_payload(args: argparse.Namespace) -> Dict[str, Any]:
    payload = {"target": args.target}
    for name in ("user", "port", "identity"):
        value = getattr(args, name, None)
        if value is not None:
            payload[name] = value
    return payload


def print_sessions(sessions: List[Dict[str, Any]]) -> None:
    if not sessions:
        print("No persistent shells.")
    for item in sessions:
        state = "connected" if item["connected"] else "disconnected"
        print(f"{item['name']}: {item['user']}@{item['hostname']}:{item['port']} {state} generation={item['generation']}")


def run_command(args: argparse.Namespace, command: str) -> int:
    response = request("exec", {**target_payload(args), "command": command, "timeout": args.timeout})
    output = base64.b64decode(response.get("output", ""))
    if output:
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
    if response.get("state_reset"):
        print("pshell: shell state was reset after reconnect", file=sys.stderr)
    return int(response.get("exit_code", 1))


def add_target_options(parser: argparse.ArgumentParser, timeout: bool = False) -> None:
    parser.add_argument("target")
    parser.add_argument("--user")
    parser.add_argument("--port", type=int)
    parser.add_argument("--identity")
    if timeout:
        parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pshell", description="Run commands through reusable SSH shells")
    sub = parser.add_subparsers(dest="action", required=True)
    add_target_options(sub.add_parser("start"))
    execute = sub.add_parser(
        "exec",
        usage="pshell exec [--timeout SECONDS] [--user USER] [--port PORT] [--identity PATH] target -- command",
    )
    add_target_options(execute, timeout=True)
    execute.add_argument("command", nargs=argparse.REMAINDER)
    add_target_options(sub.add_parser("shell"), timeout=True)
    status = sub.add_parser("status")
    status.add_argument("target", nargs="?")
    sub.add_parser("list")
    stop = sub.add_parser("stop")
    group = stop.add_mutually_exclusive_group(required=True)
    group.add_argument("target", nargs="?")
    group.add_argument("--all", action="store_true")
    sub.add_parser("daemon-stop")
    sub.add_parser("doctor")
    sub.add_parser("_serve", help=argparse.SUPPRESS)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.action == "_serve":
            Daemon().serve()
            return 0
        if args.action == "doctor":
            print(f"Python: {sys.executable}")
            try:
                print(f"Paramiko: {version('paramiko')}")
            except PackageNotFoundError:
                print("Paramiko: not installed")
            print(f"State: {STATE_FILE}")
            print(f"Known hosts: {KNOWN_HOSTS}")
            try:
                print(f"Daemon: running pid={request('ping', start=False)['pid']}")
            except PshellError as exc:
                print(f"Daemon: stopped ({exc})")
            return 0
        if args.action == "start":
            print_sessions([request("start", target_payload(args))["session"]])
            return 0
        if args.action == "exec":
            words = list(args.command)
            if words and words[0] == "--":
                words.pop(0)
            return run_command(args, " ".join(words))
        if args.action == "shell":
            request("start", target_payload(args))
            print(f"Persistent shell {args.target!r}; use .exit to leave.")
            while True:
                try:
                    command = input(f"{args.target}> ")
                except (EOFError, KeyboardInterrupt):
                    print()
                    return 0
                if command.strip() in (".exit", ".quit"):
                    return 0
                if command.strip():
                    run_command(args, command)
        if args.action in ("list", "status"):
            payload = {"target": args.target} if args.action == "status" and args.target else None
            print_sessions(request("status", payload, start=False)["sessions"])
            return 0
        if args.action == "stop":
            response = request("stop_all" if args.all else "stop", None if args.all else {"target": args.target}, start=False)
            print("Stopped: " + ", ".join(response["stopped"]))
            return 0
        if args.action == "daemon-stop":
            request("daemon_stop", start=False)
            print("Daemon stopping.")
            return 0
    except (PshellError, OSError) as exc:
        print(f"pshell: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
