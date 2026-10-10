from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import re
import threading
import time
import uuid

from .agent import CodeAgentCLI
from .egress import review
from .hapi import HapiError
from .protocol import ProtocolError, assistant_text, canonical, fingerprint, parse
from .store import Store

LOG = logging.getLogger(__name__)
TERMINAL = {"PASS", "FAIL", "BLOCKED", "NEEDS_HUMAN", "CANCELLED", "TIMED_OUT"}


class CursorReset(RuntimeError):
    pass


class Bridge:
    def __init__(self, config, client, agent=None):
        self.config, self.client = config, client
        binding = {k: config[k] for k in ("hub_url", "session_id", "target", "repositories", "profiles")}
        self.store = Store(Path(config["state_dir"]) / "bridge.sqlite3", binding)
        self.agent = agent or CodeAgentCLI(config)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.current = None
        self.stop = threading.Event()
        self.wake = threading.Event()

    def bind(self):
        if self.store.get_meta("cursor") is not None:
            return
        response = self.client.messages(self.config["session_id"], limit=1)
        page = response["page"]
        cursor = {"at": page["snapshotHeadAt"], "seq": page["snapshotHeadSeq"], "epoch": page["epoch"]}
        # An empty session has no valid `afterSeq`; latest-page bootstrap handles it.
        with self.store.db:
            self.store.set_meta("cursor", cursor)
            self.store.set_meta("bound_at", int(time.time() * 1000))
        LOG.info("Bound to current message head; historical commands skipped")

    def _accept(self, event):
        store = self.store
        digest = fingerprint(event)
        prior = store.db.execute("SELECT digest FROM inbox WHERE id=?", (event["event_id"],)).fetchone()
        if prior:
            if prior[0] != digest:
                LOG.warning("Conflicting event ID ignored")
            return
        store.db.execute("INSERT INTO inbox VALUES (?,?)", (event["event_id"], digest))
        task = store.get_task(event["task_id"], event["iteration"])
        if event["type"] == "TASK":
            # The event ID may change on transport retries; task semantics may not.
            task_digest = fingerprint({k: v for k, v in event.items() if k != "event_id"})
            if task:
                if task["digest"] != task_digest:
                    store.emit(event, "REJECTED", reason="task_content_conflict")
                return
            previous = store.db.execute("SELECT * FROM tasks WHERE task_id=? ORDER BY iteration DESC LIMIT 1",
                                        (event["task_id"],)).fetchone()
            reason = None
            if previous and (previous["iteration"] >= event["iteration"] or previous["state"] not in TERMINAL):
                reason = "iteration_stale_or_previous_running"
            binding = self.config["task_binding"]
            repository = event.get("repository", binding["repository"])
            scope_profile = event.get("scope_profile", binding["scope_profile"])
            repo = self.config["repositories"].get(repository)
            if repo is None or scope_profile not in self.config["profiles"]:
                reason = "unknown_repository_or_profile"
            elif scope_profile not in repo["profiles"]:
                reason = "profile_not_authorized_for_repository"
            if reason:
                store.emit(event, "REJECTED", reason=reason)
                return
            request = dict(event, repository=repository, scope_profile=scope_profile)
            store.db.execute("INSERT INTO tasks(task_id,iteration,request,digest,state) VALUES (?,?,?,?,?)",
                             (event["task_id"], event["iteration"], canonical(request), task_digest, "QUEUED"))
            store.emit(event, "ACK", state="QUEUED")
            LOG.info("Task queued: %s / %s", event["task_id"], event["iteration"])
            return
        if task is None or json.loads(task["request"])["revision"] != event["revision"]:
            store.emit(event, "REJECTED", reason="unknown_task_or_revision")
        elif event["type"] == "CANCEL":
            if task["state"] in {"QUEUED", "WAITING_ANSWER"}:
                store.terminal(task, "CANCELLED", "cancelled_before_execution")
            elif task["state"] == "RUNNING":
                store.update(task, state="CANCELLING")
        elif task["state"] != "WAITING_ANSWER" or task["question_id"] != event["question_id"]:
            store.emit(event, "REJECTED", reason="question_not_pending")
        else:
            store.update(task, state="QUEUED", answer=event["answer"], question_id=None)

    def catch_up(self):
        self.bind()
        cursor = self.store.get_meta("cursor")
        # Limit each tick so a busy session cannot starve cancellation/worker handling.
        for _ in range(20):
            query = {"limit": 100}
            if cursor["seq"] is not None:
                query.update(afterAt=cursor["at"], afterSeq=cursor["seq"], epoch=cursor["epoch"])
            response = self.client.messages(self.config["session_id"], **query)
            page = response["page"]
            if page.get("reset") or page["epoch"] != cursor["epoch"]:
                raise CursorReset("Message history epoch changed; operator must rebind using a new state directory")
            messages = response["messages"]
            if cursor["seq"] is None and page["hasMore"]:
                # Empty-at-bind sessions may produce more than a page before first poll.
                pages = [messages]
                before = page
                for _ in range(1000):
                    older = self.client.messages(self.config["session_id"], limit=100,
                                                 beforeAt=before["nextBeforeAt"], beforeSeq=before["nextBeforeSeq"])
                    if older["page"]["epoch"] != cursor["epoch"]:
                        raise CursorReset("Message history changed during bootstrap")
                    pages.append(older["messages"])
                    before = older["page"]
                    if not before["hasMore"]:
                        break
                else:
                    raise CursorReset("Bootstrap history exceeds supported bound")
                messages = [m for p in reversed(pages) for m in p]
            if cursor["seq"] is None:
                next_cursor = {"at": page["snapshotHeadAt"], "seq": page["snapshotHeadSeq"], "epoch": page["epoch"]}
            else:
                if page.get("direction") != "after":
                    raise CursorReset("Hub does not support the required after cursor")
                next_cursor = {"at": page["nextAfterAt"], "seq": page["nextAfterSeq"], "epoch": page["epoch"]}
            with self.store.db:
                for message in messages:
                    try:
                        event = parse(assistant_text(message), self.config["target"])
                        if event:
                            self._accept(event)
                    except ProtocolError:
                        LOG.warning("Malformed cross-zone envelope ignored")
                self.store.set_meta("cursor", next_cursor)
            if not page["hasMore"] or cursor["seq"] is None:
                return
            if cursor == next_cursor:
                raise CursorReset("Hub pagination made no progress")
            cursor = next_cursor

    def _complete(self, task, result):
        request = json.loads(task["request"])
        if result.get("pause"):
            self.store.set_meta("recovery_required", True)
        if task["state"] == "CANCELLING":
            # A concurrent successful exit does not erase a requested cancellation.
            self.store.terminal(task, "NEEDS_HUMAN" if result.get("pause") else "CANCELLED",
                                "termination_unconfirmed" if result.get("pause") else "cancelled")
            return
        if "failure" in result:
            self.store.terminal(task, result["status"], result["failure"])
            return
        if time.time() >= task["deadline"]:
            self.store.terminal(task, "TIMED_OUT", "task_deadline_exceeded")
            return
        try:
            output = result["output"]
            fields = review(output, request, secrets=(self.client.access_key, self.client.token),
                            deny_patterns=self.config["egress_deny_patterns"])
            if result.get("dirty") and fields["status"] == "PASS":
                raise ValueError("baseline_worktree_modified")
            fields["worktree_modified"] = bool(result.get("dirty"))
            if output["kind"] == "QUESTION":
                sid = result.get("session_id")
                if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", sid):
                    raise ValueError("missing_agent_session")
                if task["questions"] >= self.config["max_questions"]:
                    raise ValueError("question_limit")
                question_id = "q-" + uuid.uuid4().hex
                self.store.update(task, state="WAITING_ANSWER", session_id=sid, question_id=question_id,
                                  questions=task["questions"] + 1, answer=None)
                self.store.emit(request, "QUESTION", question_id=question_id, question=fields["question"])
            else:
                self.store.update(task, state=fields["status"])
                self.store.emit(request, "RESULT", **fields)
        except (ValueError, TypeError, KeyError):
            self.store.terminal(task, "NEEDS_HUMAN", "structured_result_or_egress_review_failed")

    def work(self):
        if self.current:
            task_id, iteration, future, cancel = self.current
            task = self.store.get_task(task_id, iteration)
            if task["state"] == "CANCELLING":
                cancel.set()
            if future.done():
                try:
                    result = future.result()
                except Exception:
                    result = {"failure": "agent_adapter_exception", "status": "NEEDS_HUMAN", "pause": True}
                with self.store.db:
                    self._complete(task, result)
                LOG.info("Task state: %s / %s = %s", task_id, iteration,
                         self.store.get_task(task_id, iteration)["state"])
                self.current = None
        with self.store.db:
            for task in self.store.db.execute("SELECT * FROM tasks WHERE state IN ('WAITING_ANSWER','QUEUED') AND deadline IS NOT NULL AND deadline<=?", (time.time(),)).fetchall():
                self.store.terminal(task, "TIMED_OUT", "task_deadline_exceeded")
        if self.current or self.store.get_meta("recovery_required") or self.stop.is_set():
            return
        task = self.store.db.execute("SELECT * FROM tasks WHERE state='QUEUED' ORDER BY rowid LIMIT 1").fetchone()
        if task:
            request = json.loads(task["request"])
            deadline = task["deadline"] or time.time() + min(request["timeout_seconds"], self.config["max_task_seconds"])
            with self.store.db:
                self.store.update(task, state="RUNNING", deadline=deadline)
                self.store.emit(request, "PROGRESS", state="RUNNING")
            cancel = threading.Event()
            LOG.info("Task running: %s / %s", task["task_id"], task["iteration"])
            future = self.executor.submit(self.agent.run, request, task["session_id"], task["answer"], deadline, cancel)
            self.current = (task["task_id"], task["iteration"], future, cancel)

    def flush(self):
        for row in self.store.db.execute("SELECT * FROM outbox WHERE sent=0 ORDER BY rowid LIMIT 20").fetchall():
            self.client.send(self.config["session_id"], row["text"], row["id"])
            with self.store.db:
                self.store.db.execute("UPDATE outbox SET sent=1 WHERE id=?", (row["id"],))

    def run(self):
        self.store.recover()
        if self.config["sse"]:
            threading.Thread(target=self.client.listen, args=(self.config["session_id"], self.wake, self.stop), daemon=True).start()
        try:
            while not self.stop.is_set():
                try:
                    self.catch_up()
                except HapiError as exc:
                    LOG.warning("Hub unavailable; retrying (%s)", exc)
                self.work()
                try:
                    self.flush()
                except HapiError as exc:
                    LOG.warning("Outbound messages retained for retry (%s)", exc)
                self.wake.wait(self.config["poll_seconds"])
                self.wake.clear()
        finally:
            self.close()

    def close(self):
        self.stop.set()
        if self.current:
            self.current[3].set()
            # work() translates adapter exceptions and persists the terminal state.
            try:
                self.current[2].result()
            except Exception:
                pass
            self.work()
        self.executor.shutdown(wait=True)
        self.store.close()
