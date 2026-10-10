import argparse
import getpass
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import traceback
import uuid

from .config import load_config
from .controller import Bridge
from .hapi import HapiClient, HapiError
from .protocol import open_event, wire as _wire


def safe_error_detail(exc, secrets=()):
    detail = str(exc).strip() or "No additional error detail was provided."
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 4:
            detail = detail.replace(secret, "[REDACTED]")
    detail = "".join(char if char in "\t" or ord(char) >= 32 else "?" for char in detail)
    return detail[:2000] + ("...[truncated]" if len(detail) > 2000 else "")


def error_hint(exc):
    if isinstance(exc, HapiError):
        if exc.status == 401:
            return "Check HAPI_ACCESS_KEY and restart the Bridge."
        if exc.status is not None:
            return f"The HAPI server returned HTTP {exc.status}; check Hub availability and access policy."
        return "Check hub_url, DNS/network access, and whether the HAPI service is reachable."
    if isinstance(exc, json.JSONDecodeError):
        return "Fix the JSON syntax in the selected config file."
    if isinstance(exc, KeyError):
        return "Add the missing required field to the selected config file."
    if isinstance(exc, OSError):
        return "Check the reported file/directory, executable, and local permissions."
    return "Correct the reported configuration or local-state problem, then restart the Bridge."


def select_session(config, config_path, value):
    try:
        session_id = str(uuid.UUID(value or ""))
    except (ValueError, AttributeError):
        raise ValueError("--session must be a complete HAPI session UUID") from None
    config["session_id"] = session_id
    config["state_dir"] = str(Path(config_path).resolve().parent / ".state" / session_id)
    return session_id


class InstanceLock:
    """OS-held lock; automatically released on crash, unlike a PID lockfile."""

    def __init__(self, directory):
        self.path = Path(directory) / "bridge.lock"

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        self.file.seek(0)
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ValueError("Another bridge owns this state directory") from None
        return self

    def __exit__(self, *args):
        self.file.close()


def main():
    parser = argparse.ArgumentParser(description="HAPI cross-zone bridge (Windows / CodeAgent CLI)")
    parser.add_argument("--config", default="config.local.json")
    parser.add_argument("--session", help="HAPI session UUID; required except for 'sessions'")
    parser.add_argument("command", choices=["sessions", "doctor", "bind", "run", "open", "status", "acknowledge-recovery"])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bridge = None
    client = None
    config = None
    stage = "loading configuration"
    try:
        config = load_config(args.config)
        if args.command != "sessions":
            select_session(config, args.config, args.session)
        stage = "initializing HAPI authentication"
        local_only = args.command in ("status", "acknowledge-recovery")
        key = "" if local_only else (config.get("access_key") or os.environ.get("HAPI_ACCESS_KEY")
                                     or getpass.getpass("HAPI access key (hidden): "))
        client = HapiClient(config["hub_url"], key)
        stage = f"executing '{args.command}'"
        if args.command == "sessions":
            for session in client.sessions():
                metadata = session.get("metadata") or {}
                summary = metadata.get("summary") or {}
                title = summary.get("text", "") if isinstance(summary, dict) else ""
                print(json.dumps({"id": session["id"], "active": session.get("active"),
                                  "url": config["hub_url"].removesuffix("api/") + "sessions/" + session["id"],
                                  "title": title}, ensure_ascii=False))
            return
        if args.command == "doctor":
            sessions = client.sessions()
            selected = next((s for s in sessions if s["id"] == config["session_id"]), None)
            if selected is None:
                raise ValueError("Command-line session ID not found; use 'sessions' to list available sessions")
            page = client.messages(config["session_id"], limit=1)
            if "epoch" not in page.get("page", {}):
                raise ValueError("Unsupported Hub pagination contract")
            if not shutil.which(config["agent_command"][0]):
                raise ValueError("Configured agent executable not found")
            if not shutil.which("git"):
                raise ValueError("git executable not found")
            for repo in config["repositories"].values():
                if not Path(repo["cwd"]).is_dir():
                    raise ValueError("Configured repository directory does not exist")
            print("Authentication, session, message pagination, agent executable and directories: OK")
            print("Session active:", bool(selected.get("active")))
            return
        with InstanceLock(config["state_dir"]):
            bridge = Bridge(config, client)
            if args.command == "open":
                # Green initiates cross-zone work with the session the operator
                # selected by pasting its URL; the OPEN notice goes to blue first.
                event = open_event(config["target"], "sessions/" + config["session_id"])
                client.send(config["session_id"], _wire(event), event["event_id"])
                print("OPEN notice sent; waiting for blue to confirm the session.", flush=True)
                bridge.run()
            elif args.command == "run":
                try:
                    bridge.run()
                finally:
                    bridge = None  # run owns shutdown
            elif args.command == "bind":
                bridge.bind()
                print("Bound. Only subsequent protocol messages will be consumed.")
            elif args.command == "status":
                rows = bridge.store.db.execute("SELECT task_id,iteration,state,questions FROM tasks ORDER BY rowid").fetchall()
                print(json.dumps({"recovery_required": bool(bridge.store.get_meta("recovery_required")),
                                  "tasks": [dict(r) for r in rows],
                                  "pending_outbox": bridge.store.db.execute("SELECT count(*) FROM outbox WHERE sent=0").fetchone()[0]}, indent=2))
            elif args.command == "acknowledge-recovery":
                # Run recovery even if the daemon has not restarted after its crash.
                bridge.store.recover()
                with bridge.store.db:
                    bridge.store.set_meta("recovery_required", False)
                print("Recovery acknowledged; interrupted tasks remain terminal and are not retried.")
    except KeyboardInterrupt:
        print("Stopped.")
    except (HapiError, ValueError, KeyError, OSError, RuntimeError) as exc:
        secrets = [value for name, value in os.environ.items() if name.upper().startswith("HAPI_")]
        secrets.append(os.environ.get("HAPI_ACCESS_KEY", ""))
        if config:
            secrets.append(config.get("access_key", ""))
        if client:
            secrets.extend((client.access_key, client.token))
        detail = safe_error_detail(exc, secrets)
        print(f"Bridge error during {stage}: {type(exc).__name__}: {detail}", file=sys.stderr)
        print("Suggested action:", error_hint(exc), file=sys.stderr)
        if os.environ.get("BRIDGE_DEBUG", "").lower() in {"1", "true", "yes"}:
            traceback.print_exc()
        raise SystemExit(1) from None
    finally:
        if bridge:
            bridge.close()
