import json
import sqlite3
import time
import uuid
from pathlib import Path

from .protocol import PROTOCOL, canonical, fingerprint, read_wire, wire


class Store:
    """Owned by the controller thread; callers choose transaction boundaries."""

    def __init__(self, path, binding, legacy_target=None):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS inbox (
                id TEXT PRIMARY KEY, digest TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT NOT NULL, iteration INTEGER NOT NULL,
                request TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL,
                session_id TEXT, question_id TEXT, answer TEXT,
                questions INTEGER NOT NULL DEFAULT 0, deadline REAL,
                PRIMARY KEY(task_id, iteration)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, text TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL
            );
        """)
        try:
            with self.db:
                old = self.get_meta("binding")
                # Legacy identity is used only to verify and migrate an existing
                # local database, never as a v3 routing or configuration option.
                candidates = {fingerprint(binding)}
                legacy_targets = {legacy_target} if isinstance(legacy_target, str) else set()
                for row in self.db.execute("SELECT request FROM tasks"):
                    request = json.loads(row["request"])
                    if request.get("protocol") == "cross-zone/v2" and isinstance(request.get("target"), str):
                        legacy_targets.add(request["target"])
                candidates.update(fingerprint({**binding, "target": value}) for value in legacy_targets)
                if old is not None and old not in candidates:
                    raise ValueError("State belongs to a different session/configuration; use another state_dir")
                state_protocol = self.get_meta("protocol")
                if state_protocol not in (None, "cross-zone/v2", PROTOCOL):
                    raise ValueError("Unsupported state protocol; retain this database and use a compatible Bridge")
                self.set_meta("binding", fingerprint(binding))
                self._upgrade_v2()
                self.set_meta("protocol", PROTOCOL)
        except Exception:
            self.db.close()
            raise

    def _upgrade_v2(self):
        """Retain old execution facts; never launch an old queued command."""
        # Preserve outbox IDs for Hub retry deduplication while switching only
        # their envelope. Completed task requests and inbox digests stay intact.
        for row in self.db.execute("SELECT id,text FROM outbox WHERE sent=0").fetchall():
            if not row["text"].startswith("CROSS_ZONE_V2\n"):
                continue
            event = read_wire("CROSS_ZONE\n" + row["text"].split("\n", 1)[1])
            if not isinstance(event, dict):
                raise ValueError("Invalid saved v2 notification; retain state for inspection")
            if event.get("type") in {"ACK", "QUESTION"}:
                self.db.execute("DELETE FROM outbox WHERE id=?", (row["id"],))
                continue
            event.pop("target", None)
            if "protocol" in event:
                event["protocol"] = PROTOCOL
            self.db.execute("UPDATE outbox SET text=? WHERE id=?", (wire(event, readable=True), row["id"]))
        for task in self.db.execute("SELECT * FROM tasks WHERE state IN ('QUEUED','RUNNING','CANCELLING','WAITING_ANSWER')").fetchall():
            request = json.loads(task["request"])
            if request.get("protocol") != "cross-zone/v2":
                continue
            continuation = task["session_id"] or task["answer"] is not None or task["questions"] > 0
            if task["state"] == "QUEUED" and not continuation:
                status, reason = "BLOCKED", "protocol_upgraded_command_not_started"
                detail = "Saved v2 command was not started. Send a new v3 instruction if still needed."
                self._drop_pending_notifications(request)
            else:
                # Never invite an ANSWER to a now-terminal old continuation.
                self._drop_pending_notifications(request, kinds={"ACK", "QUESTION"})
                self.require_recovery(task)
                status, reason = "NEEDS_HUMAN", "protocol_upgraded_prior_effects_unknown"
                detail = "Saved v2 execution or continuation will not be replayed; inspect its receipts and effects."
            self.terminal(task, status, reason, detail)

    def close(self):
        self.db.close()

    def get_meta(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, canonical(value)))

    def get_task(self, task_id, iteration):
        return self.db.execute("SELECT * FROM tasks WHERE task_id=? AND iteration=?", (task_id, iteration)).fetchone()

    def update(self, task, **fields):
        allowed = {"state", "session_id", "question_id", "answer", "questions", "deadline"}
        if not fields or not fields.keys() <= allowed:
            raise ValueError("invalid state fields")
        sql = ",".join(k + "=?" for k in fields)
        self.db.execute(f"UPDATE tasks SET {sql} WHERE task_id=? AND iteration=?",
                        (*fields.values(), task["task_id"], task["iteration"]))

    def _drop_pending_notifications(self, request, *, kinds=frozenset({"ACK"})):
        for row in self.db.execute("SELECT id,text FROM outbox WHERE sent=0").fetchall():
            event = read_wire(row["text"])
            binding = ("task_id", "iteration")
            if "protocol" in event:  # Legacy full envelope.
                binding += ("revision",)
            if event["type"] in kinds and all(event.get(k) == request.get(k) for k in binding):
                self.db.execute("DELETE FROM outbox WHERE id=?", (row["id"],))

    def emit(self, request, kind, **fields):
        if kind == "PROGRESS":
            self._drop_pending_notifications(request)
        event_id = "green-" + uuid.uuid4().hex
        event = {"protocol": PROTOCOL, "type": kind, "event_id": event_id,
                 **{k: request[k] for k in ("task_id", "iteration")}, **fields}
        if "revision" in request:
            event["revision"] = request["revision"]
        if kind in {"ACK", "PROGRESS"}:
            event = {k: event[k] for k in ("type", "task_id", "iteration")}
        self.db.execute("INSERT INTO outbox(id,text,created) VALUES (?,?,?)", (event_id, wire(event, readable=True), time.time()))
        return event_id

    def terminal(self, task, status, reason, detail="", execution=None):
        request = json.loads(task["request"])
        self.update(task, state=status)
        fields = {"detail": detail} if detail else {}
        if request["type"] == "EXEC":
            fields["execution"] = execution or {"status": "NOT_STARTED" if task["state"] == "QUEUED" else "UNKNOWN",
                                                "exit_code": None}
        self.emit(request, "RESULT", status=status, reason=reason, **fields)

    def require_recovery(self, task):
        pending = self.get_meta("recovery_tasks") or []
        identity = {"task_id": task["task_id"], "iteration": task["iteration"]}
        if identity not in pending:
            pending.append(identity)
        self.set_meta("recovery_tasks", pending)
        self.set_meta("recovery_required", True)

    def recover(self):
        """Keep interrupted work terminal; let agents inspect before further changes."""
        with self.db:
            # Older versions paused globally without recording the affected identities.
            if self.get_meta("recovery_required") and not self.get_meta("recovery_tasks"):
                for task in self.db.execute("SELECT * FROM tasks WHERE state='NEEDS_HUMAN'").fetchall():
                    self.require_recovery(task)
            running = self.db.execute("SELECT * FROM tasks WHERE state IN ('RUNNING','CANCELLING')").fetchall()
            for task in running:
                self.require_recovery(task)
                self.terminal(task, "NEEDS_HUMAN", "execution_interrupted_state_unknown",
                              f"Bridge restarted while task state was {task['state']}. "
                              "Child-process and remote effects are unknown. Interrupted work will not be retried. "
                              "Queued tasks can run with an automatic recovery check; blue should inspect "
                              "surviving processes and completed changes before requesting further mutations. "
                              "No manual recovery acknowledgement is required.")
        return bool(running)
