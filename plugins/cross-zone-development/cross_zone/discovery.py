"""Single-session discovery supervisor; execution stays in the existing Bridge."""

from contextlib import ExitStack
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time
import uuid

from . import __version__
from .controller import Bridge
from .hapi import HapiError
from .protocol import PROTOCOL, ProtocolError, assistant_text, parse_connection, wire

from .scheduling import SessionSync

LOG = logging.getLogger(__name__)


class Discovery:
    def __init__(self, config, client, lock_factory, bridge_factory=Bridge):
        self.config, self.client = config, client
        self.lock_factory, self.bridge_factory = lock_factory, bridge_factory
        self.directory = Path(config["state_dir"])
        self.directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.directory / "discovery.sqlite3")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, cursor TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS requests(
                session TEXT, event_id TEXT, request TEXT NOT NULL, response TEXT,
                PRIMARY KEY(session,event_id));
            CREATE TABLE IF NOT EXISTS outbox(
                id TEXT PRIMARY KEY, session TEXT NOT NULL, text TEXT NOT NULL, sent INTEGER DEFAULT 0);
        """)
        identity = {key: config[key] for key in ("hub_url", "workspace_dir")}
        previous = self.get("identity")
        if previous is not None and previous != identity:
            self.db.close()
            changed = ", ".join(key for key in identity if previous.get(key) != identity[key])
            raise ValueError(
                f"Discovery state belongs to another Hub/workspace (changed: {changed}). "
                "Restore the original hub_url and launch workspace to reuse saved state. "
                "If the change is intentional, stop all Bridges using "
                f"'{self.directory.parent.resolve()}', then back up (recommended) or delete that entire "
                ".state folder and restart. Fresh state will not retain execution history, "
                "deduplication records or pending results, and will not stop previously launched "
                "remote tasks. After startup, send a new OPEN to reconnect."
            )
        with self.db:
            self.set("identity", identity)
        self.bridge = None
        self.session_lock = ExitStack()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.sync = SessionSync(config["poll_seconds"], self.wake)
        self.client.set_interactive(False)

    def get(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))

    @staticmethod
    def head(page):
        return {"at": page["snapshotHeadAt"], "seq": page["snapshotHeadSeq"], "epoch": page["epoch"]}

    def save_cursor(self, session, cursor):
        self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?)", (session, json.dumps(cursor)))

    def initialize(self):
        if self.get("initialized"):
            return
        # Establish all existing heads before advertising readiness. Failures roll
        # back the whole baseline; old OPENs can never be claimed on partial init.
        sessions = self.client.sessions()
        with self.db:
            self.set("started_at", int(time.time() * 1000))
            for session in sessions:
                sid = self.session_id(session["id"])
                self.save_cursor(sid, self.head(self.client.messages(sid, limit=1)["page"]))
            self.set("initialized", True)
        LOG.info("Discovery ready; waiting for a new blue OPEN")

    @staticmethod
    def session_id(value):
        # Session IDs become local directory names; never accept paths from Hub.
        return str(uuid.UUID(value))

    def attach(self):
        binding = self.get("binding")
        if not binding or self.bridge is not None:
            return
        cfg = dict(self.config)
        cfg["session_id"] = self.session_id(binding["session"])
        cfg["state_dir"] = str(self.directory.parent / cfg["session_id"])
        cfg["discovery"] = True
        stack = ExitStack()
        try:
            stack.enter_context(self.lock_factory(cfg["state_dir"]))
            bridge = self.bridge_factory(cfg, self.client)
            try:
                self.client.set_interactive(True)
                if not binding["prepared"]:
                    bridge.prepare_open()
                    binding["prepared"] = True
                    with self.db:
                        self.set("binding", binding)
                else:
                    bridge.store.recover()
            except BaseException:
                bridge.close()
                raise
        except BaseException:
            self.client.set_interactive(False)
            stack.close()
            raise
        self.session_lock = stack
        self.bridge = bridge
        bridge.wake = self.wake
        if cfg["sse"]:
            threading.Thread(target=self.client.listen,
                             args=(cfg["session_id"], self.sync, bridge.stop), daemon=True).start()
        LOG.info("Discovery bound to session %s", cfg["session_id"])

    def idle(self):
        store = self.bridge.store
        return (not self.bridge.active
                and not store.db.execute("SELECT 1 FROM tasks WHERE state IN "
                                         "('QUEUED','RUNNING','CANCELLING','WAITING_ANSWER') LIMIT 1").fetchone()
                and not store.db.execute("SELECT 1 FROM outbox WHERE sent=0 LIMIT 1").fetchone()
                and not store.get_meta("recovery_required"))

    def release(self):
        if self.bridge:
            self.bridge.close()
            self.bridge = None
        self.session_lock.close()
        self.client.set_interactive(False)

    def respond(self, session, event, kind):
        response = {"protocol": PROTOCOL, "type": kind, "event_id": "green-connection-" + uuid.uuid4().hex,
                    "request_event_id": event["event_id"], "version": __version__,
                    "session_url": "sessions/" + session}
        with self.db:
            self.db.execute("UPDATE requests SET response=? WHERE session=? AND event_id=?",
                            (json.dumps(response), session, event["event_id"]))
            self.db.execute("INSERT INTO outbox(id,session,text) VALUES (?,?,?)",
                            (response["event_id"], session, wire(response, readable=True)))

    def finish_force_open(self):
        """Resume a durable takeover; do not launch old work while cancellation drains."""
        pending = self.get("force_open")
        session, event = pending["session"], pending["event"]
        try:
            if pending["phase"] == "cancel":
                self.attach()
                if self.bridge:
                    self.bridge.interrupt_connection()
                    if self.bridge.active:
                        return False
                    # Keep original delivery IDs and destination when moving the
                    # old outbox. A crash may repeat the copy, never the command.
                    owner = self.bridge.config["session_id"]
                    with self.db:
                        for row in self.bridge.store.db.execute("SELECT id,text FROM outbox WHERE sent=0 ORDER BY rowid"):
                            self.db.execute("INSERT OR IGNORE INTO outbox(id,session,text) VALUES (?,?,?)",
                                            (row["id"], owner, row["text"]))
                with self.db:
                    self.set("binding", {"session": session, "prepared": False})
                    self.set("force_open", {**pending, "phase": "connect"})
                self.release()
            self.attach()
        except ValueError as exc:
            if str(exc) != "Another bridge owns this state directory":
                raise
            with self.db:
                self.set("binding", None)
                self.respond(session, event, "BUSY")
                self.set("force_open", None)
            return
        with self.db:
            self.respond(session, event, "READY")
            self.set("force_open", None)

    def handle(self, session, event, position=None):
        prior = self.db.execute("SELECT request,response FROM requests WHERE session=? AND event_id=?",
                                (session, event["event_id"])).fetchone()
        if prior:
            if json.loads(prior[0]) != event:
                LOG.warning("Conflicting connection event ignored")
                return
            if prior[1] is not None:
                return
        else:
            with self.db:
                self.db.execute("INSERT INTO requests(session,event_id,request) VALUES (?,?,?)",
                                (session, event["event_id"], json.dumps(event)))
        binding = self.get("binding")
        if event["type"] == "FORCE_OPEN":
            with self.db:
                self.set("force_open", {"session": session, "event": event, "phase": "cancel"})
            return self.finish_force_open()
        if event["type"] == "OPEN":
            if binding and binding["session"] != session:
                self.respond(session, event, "BUSY")
                return
            if not binding:
                with self.db:
                    self.set("binding", {"session": session, "prepared": False})
            try:
                self.attach()
            except ValueError as exc:
                # Explicit Bridge owns this session. Do not claim or reset it.
                if str(exc) != "Another bridge owns this state directory":
                    raise
                with self.db:
                    self.set("binding", None)
                self.respond(session, event, "BUSY")
                return
            self.respond(session, event, "READY")
        elif not binding:
            self.respond(session, event, "CLOSED")
        elif binding["session"] != session:
            self.respond(session, event, "BUSY")
        else:
            # Commands may have arrived since tick's first catch-up. Reach this
            # CLOSE's durable position before checking idle, including pagination.
            self.bridge.catch_up()
            cursor = self.bridge.store.get_meta("cursor")
            if position and (cursor["epoch"] != position["epoch"]
                             or cursor["seq"] is None or cursor["seq"] < position["seq"]):
                return False  # Retain scan cursor and retry after the next catch-up.
            if not self.idle():
                self.respond(session, event, "BUSY")
                return
            # Persist release and receipt together before closing the worker.
            # A crash cannot resurrect this binding or lose the CLOSED receipt.
            with self.db:
                self.set("binding", None)
                self.respond(session, event, "CLOSED")
            self.release()
            LOG.info("Discovery released; waiting for a new blue OPEN")

    def collect_completed(self):
        """Do not let unrelated discovery pages delay completed task results."""
        if not self.bridge or not any(future.done() for future, _, _ in self.bridge.active.values()):
            return
        self.bridge.work()
        try:
            self.bridge.flush()
        except HapiError as exc:
            LOG.warning("Bound results retained for retry (%s)", exc)

    def scan(self, session):
        row = self.db.execute("SELECT cursor FROM sessions WHERE id=?", (session,)).fetchone()
        cursor = json.loads(row[0]) if row else {"at": None, "seq": None, "epoch": None}
        # Service completed workers between network reads, including bootstrap pages.
        for _ in range(20):
            query = {"limit": 100}
            if cursor["seq"] is not None:
                query.update(afterAt=cursor["at"], afterSeq=cursor["seq"], epoch=cursor["epoch"])
            response = self.client.messages(session, **query)
            self.collect_completed()
            page = response["page"]
            if page.get("reset") or (cursor["epoch"] is not None and page["epoch"] != cursor["epoch"]):
                with self.db:
                    self.save_cursor(session, self.head(page))
                LOG.warning("Discovery history reset; new OPEN may need resending")
                return
            if cursor["seq"] is not None and page.get("direction") != "after":
                raise ValueError("Hub does not support the required discovery after cursor")
            messages = response["messages"]
            # Empty/new sessions require oldest-first bootstrap to avoid losing
            # an OPEN behind a large initial burst of messages.
            if cursor["seq"] is None:
                pages = [messages]
                older = page
                for _ in range(1000):
                    if not older["hasMore"]:
                        break
                    result = self.client.messages(session, limit=100,
                                                  beforeAt=older["nextBeforeAt"], beforeSeq=older["nextBeforeSeq"])
                    self.collect_completed()
                    older = result["page"]
                    if older["epoch"] != page["epoch"]:
                        return
                    pages.append(result["messages"])
                else:
                    raise ValueError("Discovery bootstrap history exceeds supported bound")
                messages = [msg for batch in reversed(pages) for msg in batch]
            for message in messages:
                if (row is None and message.get("createdAt", 0) < self.get("started_at")):
                    continue
                try:
                    event = parse_connection(assistant_text(message))
                except ProtocolError:
                    continue
                if event:
                    position = {"seq": message["seq"], "epoch": page["epoch"]}
                    if self.handle(session, event, position) is False:
                        return
            next_cursor = (self.head(page) if cursor["seq"] is None else
                           {"at": page["nextAfterAt"], "seq": page["nextAfterSeq"], "epoch": page["epoch"]})
            with self.db:
                self.save_cursor(session, next_cursor)
            if cursor["seq"] is None or not page["hasMore"]:
                return
            if next_cursor == cursor:
                raise ValueError("Discovery pagination made no progress")
            cursor = next_cursor

    def flush(self):
        sessions = self.db.execute("SELECT session FROM outbox WHERE sent=0 "
                                   "GROUP BY session ORDER BY MIN(rowid)").fetchall()
        for (session,) in sessions:
            rows = self.db.execute("SELECT id,text FROM outbox WHERE sent=0 AND session=? "
                                   "ORDER BY rowid LIMIT 20", (session,)).fetchall()
            for event_id, text in rows:
                try:
                    self.client.send(session, text, event_id)
                except HapiError as exc:
                    LOG.warning("Connection reply retained for retry (%s)", exc)
                    break
                with self.db:
                    self.db.execute("UPDATE outbox SET sent=1 WHERE id=?", (event_id,))

    def tick(self, *, discover=True, sync=True):
        if discover:
            self.initialize()
        if self.get("force_open"):
            self.finish_force_open()
            self.flush()
            return
        self.attach()
        self.collect_completed()
        unavailable_owner = self.bridge.config["session_id"] if self.bridge and not sync else None
        # First drain commands/results of the owner so CLOSE cannot overlook an
        # accepted TASK. Connection controls themselves never enter its inbox.
        if self.bridge:
            if sync:
                try:
                    self.bridge.catch_up()
                except HapiError as exc:
                    LOG.warning("Bound session unavailable; retrying (%s)", exc)
                    unavailable_owner = self.bridge.config["session_id"]
            self.bridge.work()
            try:
                self.bridge.flush()
            except HapiError as exc:
                LOG.warning("Bound results retained for retry (%s)", exc)
        sessions = self.client.sessions() if discover else (
            [{"id": self.bridge.config["session_id"]}] if sync and self.bridge else [])
        self.collect_completed()
        for session in sessions:
            if self.get("force_open"):
                break
            try:
                sid = self.session_id(session["id"])
                if sid != unavailable_owner:
                    self.scan(sid)
            except HapiError as exc:
                LOG.warning("Discovery session unavailable; retrying (%s)", exc)
        self.flush()

    def run(self):
        next_discovery = 0
        try:
            while not self.stop.is_set():
                self.wake.clear()
                now = time.monotonic()
                discover = now >= next_discovery
                if discover:
                    # Advance before I/O so failed requests also respect cadence.
                    next_discovery = now + self.config.get("discovery_poll_seconds", 30)
                sync = self.sync.due(now)
                started = time.monotonic()
                LOG.debug("Discovery tick begin discover=%s sync=%s bound=%s", discover, sync, self.bridge is not None)
                try:
                    self.tick(discover=discover, sync=sync)
                except HapiError as exc:
                    LOG.warning("Discovery Hub unavailable; retrying (%s)", exc)
                finally:
                    LOG.debug("Discovery tick end elapsed_ms=%.1f", (time.monotonic() - started) * 1000)
                now = time.monotonic()
                self.wake.wait(min(self.sync.wait_seconds(now), max(0, next_discovery - now)))
        finally:
            self.close()

    def close(self):
        self.stop.set()
        self.release()
        self.db.close()
