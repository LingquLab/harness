import json
import sqlite3
import time
import uuid
from pathlib import Path

from .protocol import PROTOCOL, canonical, fingerprint, wire


class Store:
    """Owned by the controller thread; callers choose transaction boundaries."""

    def __init__(self, path, binding):
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
        with self.db:
            old = self.get_meta("binding")
            if old is not None and old != fingerprint(binding):
                # Close below rather than leaving an open Windows file handle.
                mismatch = True
            else:
                mismatch = False
                self.set_meta("binding", fingerprint(binding))
        if mismatch:
            self.db.close()
            raise ValueError("State belongs to a different session/configuration; use another state_dir")

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

    def emit(self, request, kind, **fields):
        event_id = "green-" + uuid.uuid4().hex
        event = {"protocol": PROTOCOL, "type": kind, "event_id": event_id,
                 **{k: request[k] for k in ("task_id", "iteration", "target")}, **fields}
        if "revision" in request:
            event["revision"] = request["revision"]
        self.db.execute("INSERT INTO outbox(id,text,created) VALUES (?,?,?)", (event_id, wire(event), time.time()))
        return event_id

    def terminal(self, task, status, reason):
        request = json.loads(task["request"])
        self.update(task, state=status)
        self.emit(request, "RESULT", status=status, reason=reason)

    def recover(self):
        """A crash cannot prove whether a child or its effects survived."""
        with self.db:
            running = self.db.execute("SELECT * FROM tasks WHERE state IN ('RUNNING','CANCELLING')").fetchall()
            for task in running:
                self.terminal(task, "NEEDS_HUMAN", "execution_interrupted_state_unknown")
            if running:
                self.set_meta("recovery_required", True)
        return bool(running)
