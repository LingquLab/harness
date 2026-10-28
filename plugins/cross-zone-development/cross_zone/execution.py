"""Exact, noninteractive execution with optional API AI egress review."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .agent import terminate_tree
from .protocol import canonical

OUTPUT_LIMIT = 32 * 1024 * 1024
REVIEW_SECONDS = 60


def facts(status, exit_code=None):
    return {"status": status, "exit_code": exit_code}


class DirectExecutor:
    def __init__(self, config, reviewer):
        self.config, self.reviewer = config, reviewer

    def run(self, request, session_id, answer, deadline, cancel, recovery):
        if recovery:
            return {"failure": "execution_recovery_pending", "status": "BLOCKED",
                    "detail": "Command was not started. Use a scoped read-only TASK to verify surviving "
                              "processes and completed effects before another EXEC.",
                    "execution": facts("NOT_STARTED")}
        if cancel.is_set() or time.time() >= deadline - REVIEW_SECONDS:
            return {"failure": "execution_not_started", "status": "CANCELLED" if cancel.is_set() else "TIMED_OUT",
                    "detail": "Command was not started; cancelled or insufficient time remains for execution and review.",
                    "execution": facts("NOT_STARTED")}
        root = Path(self.config["state_dir"]).resolve()
        directory = root / "runs" / request["task_id"] / str(request["iteration"]) / "execution"
        directory.mkdir(parents=True, exist_ok=True)
        receipt = directory / "execution.json"
        # Exclusive claim prevents command replay even if a caller bypasses inbox dedup.
        try:
            with receipt.open("x", encoding="utf-8") as stream:
                stream.write(canonical(facts("STARTING")))
        except FileExistsError:
            return {"failure": "execution_already_attempted", "status": "NEEDS_HUMAN", "pause": True,
                    "detail": "A saved execution receipt already exists. Inspect it; command was not repeated.",
                    "execution": facts("UNKNOWN")}
        stdout, stderr = directory / "stdout.log", directory / "stderr.log"
        record = facts("STARTING")
        process = None

        def save():
            temporary = receipt.with_suffix(".tmp")
            temporary.write_text(canonical(record), encoding="utf-8")
            temporary.replace(receipt)

        try:
            spec = request["execution"]
            if "argv" in spec:
                command = list(spec["argv"])
                # Windows may implicitly interpret batch files despite shell=False.
                resolved = shutil.which(command[0]) or command[0]
                if os.name == "nt" and Path(resolved).suffix.lower() in {".cmd", ".bat"}:
                    raise ValueError("Use an explicit interpreter for Windows batch commands")
            else:
                interpreter = spec["interpreter"]
                prefix, suffix = {
                    "bash": (["bash"], ".sh"),
                    "powershell": (["powershell", "-NoProfile", "-NonInteractive", "-File"], ".ps1"),
                    "python": ([sys.executable], ".py"),
                }[interpreter]
                script = directory / ("script" + suffix)
                script.write_bytes(spec["script"].encode("utf-8-sig" if interpreter == "powershell" else "utf-8"))
                command = [*prefix, str(script)]
            review_key = self.config.get("exec_review", {}).get("api_key")
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith("HAPI_")
                   and (not review_key or v != review_key)}
            env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            command_deadline = min(time.time() + request["execution_timeout_seconds"], deadline - REVIEW_SECONDS)
            with stdout.open("wb") as out, stderr.open("wb") as err:
                if cancel.is_set() or time.time() >= command_deadline:
                    record.update(facts("NOT_STARTED"))
                else:
                    process = subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                               stdout=out, stderr=err, shell=False, **options)
                    record.update(status="RUNNING", pid=process.pid, started=time.time())
                    save()
                    while True:
                        exit_code = process.poll()
                        if cancel.is_set():
                            status = "CANCELLED"
                        elif stdout.stat().st_size + stderr.stat().st_size > OUTPUT_LIMIT:
                            status = "OUTPUT_LIMIT"
                        elif exit_code is not None:
                            status = "EXITED"
                        elif time.time() >= command_deadline:
                            status = "TIMED_OUT"
                        else:
                            cancel.wait(0.05)
                            continue
                        if status != "EXITED" and exit_code is None:
                            terminate_tree(process)
                        record.update(facts(status, process.returncode))
                        break
        except (OSError, ValueError, subprocess.SubprocessError, RuntimeError) as exc:
            record.update(facts("START_FAILED" if process is None else "EXECUTION_ERROR"))
            record["error"] = f"{type(exc).__name__}: {exc}"
            if process is not None:
                try:
                    if process.poll() is None:
                        terminate_tree(process)
                    record["exit_code"] = process.returncode
                except (OSError, RuntimeError, subprocess.SubprocessError):
                    record.update(facts("TERMINATION_UNCONFIRMED"))
        record["finished"] = time.time()
        execution = facts(record["status"], record["exit_code"])
        try:
            save()
        except OSError:
            return {"failure": "execution_receipt_write_failed", "status": "NEEDS_HUMAN", "pause": True,
                    "detail": "Execution receipt could not be saved. Inspect local state before any further changes.",
                    "execution": execution}
        if execution["status"] == "TERMINATION_UNCONFIRMED":
            return {"failure": "termination_unconfirmed", "status": "NEEDS_HUMAN", "pause": True,
                    "detail": "Execution termination is unknown; inspect the local receipt and surviving processes.",
                    "execution": execution}
        if cancel.is_set():
            return {"failure": "cancelled", "status": "CANCELLED",
                    "detail": "Execution cancelled; raw output remains green-local and was not exported.",
                    "execution": execution}
        if request.get("ai_review", False) is False:
            # Only successful, small stdout is eligible for direct export. Never
            # return stderr or exception text from the command through this path.
            if execution["status"] != "EXITED" or execution["exit_code"] != 0:
                status = {"TIMED_OUT": "TIMED_OUT", "OUTPUT_LIMIT": "NEEDS_HUMAN",
                          "START_FAILED": "BLOCKED", "NOT_STARTED": "BLOCKED",
                          "EXECUTION_ERROR": "NEEDS_HUMAN"}.get(execution["status"], "FAIL")
                return {"failure": "direct_execution_failed", "status": status,
                        "detail": "Direct command did not exit successfully; output remains green-local.",
                        "execution": execution}
            try:
                if stdout.stat().st_size > 2000 or stderr.stat().st_size:
                    raise ValueError("unexpected output")
                summary = stdout.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
                if any((ord(c) < 32 or 127 <= ord(c) <= 159) and c not in "\n\t" for c in summary):
                    raise ValueError("control characters")
            except (OSError, UnicodeError, ValueError):
                return {"failure": "direct_output_rejected", "status": "NEEDS_HUMAN",
                        "detail": "Direct output is oversized, invalid UTF-8, contains control characters, or stderr is nonempty; output withheld.",
                        "execution": execution}
            return {"output": {"kind": "RESULT", "status": "PASS",
                               "summary": "Direct EXEC (no AI review):\n" + summary.strip(),
                               "checks": [{"id": c["id"], "status": "PASS"} for c in request["checks"]],
                               "error_code": "", "question": "", "local_modification_tested": False,
                               "local_modification_outcome": "NOT_RUN", "egress_reviewed": False},
                    "execution": execution}
        context = {"receipt": str(receipt), "stdout": str(stdout), "stderr": str(stderr),
                   "execution": execution}
        try:
            result = self.reviewer.run(request, None, None, deadline, cancel, [], context)
            if not isinstance(result, dict):
                raise TypeError("invalid reviewer result")
        except Exception:
            # Reviewer exceptions must never discard authoritative execution facts or raw-log boundaries.
            result = {"failure": "execution_review_failed", "status": "NEEDS_HUMAN",
                      "detail": "Output review failed after execution; inspect saved local evidence, do not rerun."}
        return {**result, "execution": execution}
