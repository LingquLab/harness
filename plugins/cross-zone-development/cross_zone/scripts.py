"""Session-local scripts and commit-pinned CrossZoneScript snapshots."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time


REPOSITORY = "https://github.com/LingquLab/CrossZoneScript.git"
CAPABILITIES = ["exec.git-session.v1"]
SUFFIXES = {".py", ".sh", ".ps1"}


class ScriptFeedback(Exception):
    def __init__(self, code, **payload):
        details = {
            "SCRIPT_NOT_FOUND": "Script does not exist in this session/snapshot.",
            "SCRIPT_GIT_FAILED": "Git preparation failed at the reported stage; no script was executed.",
            "SCRIPT_CANCELLED": "Script preparation was cancelled.",
            "SCRIPT_TIMED_OUT": "Script preparation exceeded the task deadline.",
        }
        self.payload = {"error_code": code, **payload}
        if code:
            self.payload["detail"] = details.get(code, code.replace("_", " ").capitalize() + ".")
        super().__init__(code)


def valid_path(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value and ":" not in value
            and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts
            and PurePosixPath(value).parts)


def valid_entry(value):
    return valid_path(value) and PurePosixPath(value).suffix in SUFFIXES


def validate(spec):
    if set(spec) != {"git", "commit", "entry", "args"}:
        raise ValueError("invalid_execution_fields")
    if (spec["git"] != "session" or not isinstance(spec["commit"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", spec["commit"]) or not valid_entry(spec["entry"])):
        raise ValueError("invalid_git_script")
    if not isinstance(spec["args"], dict):
        raise ValueError("invalid_script_args")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_stop(deadline, cancel):
    if cancel.is_set():
        raise ScriptFeedback("SCRIPT_CANCELLED")
    if time.time() >= deadline:
        raise ScriptFeedback("SCRIPT_TIMED_OUT")


def git_command(args, cwd, deadline, cancel):
    check_stop(deadline, cancel)
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="Never")
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with subprocess.Popen(["git", "-c", "core.hooksPath=" + os.devnull, *args], cwd=cwd, env=env,
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options) as process:
        while True:
            try:
                out, _ = process.communicate(timeout=min(.1, max(.001, deadline-time.time())))
                break
            except subprocess.TimeoutExpired:
                try:
                    check_stop(deadline, cancel)
                except ScriptFeedback:
                    from .agent import terminate_tree
                    terminate_tree(process)
                    raise
        if process.returncode:
            raise ScriptFeedback("SCRIPT_GIT_FAILED", stage=args[0])
        check_stop(deadline, cancel)
        return out


def git_snapshot(spec, config, directory, deadline, cancel):
    session = config["session_id"]
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", session):
        raise ScriptFeedback("SCRIPT_SESSION_INVALID")
    repo = directory / "repository"
    repo.mkdir()
    git_command(["init"], repo, deadline, cancel)
    git_command(["fetch", "--no-tags", REPOSITORY, "refs/heads/" + session], repo, min(deadline, time.time() + 120), cancel)
    commit = spec["commit"]
    git_command(["merge-base", "--is-ancestor", commit, "FETCH_HEAD"], repo, deadline, cancel)
    tree = git_command(["ls-tree", "-rz", "--full-tree", commit], repo, deadline, cancel)
    snapshot = directory / "source"
    snapshot.mkdir()
    for row in tree.split(b"\0"):
        if not row:
            continue
        metadata, raw_name = row.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        if kind != b"blob" or mode not in {b"100644", b"100755"}:
            raise ScriptFeedback("SCRIPT_GIT_FILE_UNSUPPORTED")
        name = raw_name.decode("utf-8")
        if not valid_path(name):
            raise ScriptFeedback("SCRIPT_GIT_PATH_INVALID")
        destination = snapshot / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(git_command(["cat-file", "blob", oid.decode()], repo, deadline, cancel))
    path = snapshot / spec["entry"]
    if not path.is_file():
        raise ScriptFeedback("SCRIPT_NOT_FOUND", name=spec["entry"])
    return path


def prepare(spec, config, directory, deadline, cancel):
    """Resolve to argv, or return script-control feedback through an exception."""
    check_stop(deadline, cancel)
    path = git_snapshot(spec, config, directory, deadline, cancel)
    check_stop(deadline, cancel)
    args_file = directory / "args.json"
    args_file.write_text(json.dumps(spec.get("args", {}), ensure_ascii=False), encoding="utf-8")
    prefix = {".py": [sys.executable], ".sh": ["bash"],
              ".ps1": ["powershell", "-NoProfile", "-NonInteractive", "-File"]}[path.suffix]
    (directory / "script-source.json").write_text(json.dumps({"sha256": digest(path.read_bytes()),
        "name": spec["entry"], "commit": spec.get("commit")}), encoding="utf-8")
    return [*prefix, str(path), "--args-file", str(args_file)]
