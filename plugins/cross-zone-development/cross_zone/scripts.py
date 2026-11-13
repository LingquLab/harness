"""Session-local scripts and commit-pinned CrossZoneScript snapshots."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import threading
import time


REPOSITORY = "https://github.com/LingquLab/CrossZoneScript.git"
CAPABILITIES = ["exec.session-script.v1", "exec.git-session.v1"]
LOCK = threading.Lock()
SUFFIXES = {".py", ".sh", ".ps1"}


class ScriptFeedback(Exception):
    def __init__(self, code, **payload):
        details = {
            "SCRIPT_HASH_MISMATCH": "Script changed; use the returned full content and SHA256 before updating or executing.",
            "SCRIPT_NOT_FOUND": "Script does not exist in this session/snapshot.",
            "SCRIPT_REPLACEMENT_MISMATCH": "Each old string must occur exactly once; script was not modified.",
            "SCRIPT_GIT_FAILED": "Git preparation failed at the reported stage; no script was executed.",
            "SCRIPT_CANCELLED": "Script preparation was cancelled.",
            "SCRIPT_TIMED_OUT": "Script preparation exceeded the task deadline.",
        }
        self.payload = {"error_code": code, **payload}
        if code:
            self.payload["detail"] = details.get(code, code.replace("_", " ").capitalize() + ".")
        super().__init__(code)


def valid_name(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value)) and Path(value).suffix in SUFFIXES


def valid_path(value):
    return (isinstance(value, str) and bool(value) and "\\" not in value and ":" not in value
            and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts
            and PurePosixPath(value).parts)


def valid_entry(value):
    return valid_path(value) and PurePosixPath(value).suffix in SUFFIXES


def validate(spec):
    fields = set(spec)
    if fields == {"script", "sha256", "args"}:
        name = spec["script"]
    elif fields == {"script_read"}:
        name = spec["script_read"]
    elif fields in ({"script_update", "sha256", "content"}, {"script_update", "sha256", "replacements"}):
        name = spec["script_update"]
        if "content" in spec and (not isinstance(spec["content"], str) or "\0" in spec["content"]):
            raise ValueError("invalid_script_content")
        if "replacements" in spec:
            replacements = spec["replacements"]
            if not isinstance(replacements, list) or not replacements:
                raise ValueError("invalid_script_replacements")
            for item in replacements:
                if (not isinstance(item, dict) or set(item) != {"old", "new"}
                        or not isinstance(item["old"], str) or not item["old"]
                        or not isinstance(item["new"], str) or "\0" in item["old"] + item["new"]):
                    raise ValueError("invalid_script_replacements")
    elif fields == {"git", "commit", "entry", "args"}:
        if (spec["git"] != "session" or not isinstance(spec["commit"], str)
                or not re.fullmatch(r"[0-9a-f]{40}", spec["commit"]) or not valid_entry(spec["entry"])):
            raise ValueError("invalid_git_script")
        name = None
    else:
        raise ValueError("invalid_execution_fields")
    if name is not None and not valid_name(name):
        raise ValueError("invalid_script_name")
    if "args" in spec and not isinstance(spec["args"], dict):
        raise ValueError("invalid_script_args")
    if "sha256" in spec:
        value = spec["sha256"]
        if value is None and "script_update" in spec:
            return
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("invalid_script_hash")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def feedback(path, code):
    if path.is_file():
        data = path.read_bytes()
        raise ScriptFeedback(code, name=path.name, sha256=digest(data), content=data.decode("utf-8"))
    raise ScriptFeedback(code, name=path.name, sha256=None, content=None)


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
    git_command(["fetch", "--no-tags", REPOSITORY, "refs/heads/" + session], repo, deadline, cancel)
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
    if "git" in spec:
        path = git_snapshot(spec, config, directory, deadline, cancel)
    else:
        name = spec.get("script_update", spec.get("script_read", spec.get("script")))
        root = Path(config["state_dir"]).resolve() / "scripts"
        root.mkdir(exist_ok=True)
        path = root / name
        with LOCK:
            check_stop(deadline, cancel)
            if path.is_symlink():
                raise ScriptFeedback("SCRIPT_NAME_INVALID")
            if "script_read" in spec:
                feedback(path, "" if path.is_file() else "SCRIPT_NOT_FOUND")
            data = path.read_bytes() if path.is_file() else None
            actual = digest(data) if data is not None else None
            if actual is None and "script" in spec:
                feedback(path, "SCRIPT_NOT_FOUND")
            if actual != spec["sha256"]:
                feedback(path, "SCRIPT_HASH_MISMATCH")
            if "script_update" in spec:
                if "content" in spec:
                    content = spec["content"]
                else:
                    if actual is None:
                        feedback(path, "SCRIPT_NOT_FOUND")
                    content = data.decode("utf-8")
                    for replacement in spec["replacements"]:
                        if content.count(replacement["old"]) != 1:
                            feedback(path, "SCRIPT_REPLACEMENT_MISMATCH")
                        content = content.replace(replacement["old"], replacement["new"], 1)
                temporary = directory / "updated-script"
                temporary.write_bytes(content.encode("utf-8"))
                os.replace(temporary, path)
                raise ScriptFeedback("", name=name, sha256=digest(path.read_bytes()), updated=True)
            if actual is None:
                feedback(path, "SCRIPT_NOT_FOUND")
            snapshot = directory / name
            snapshot.write_bytes(data)
            path = snapshot
    check_stop(deadline, cancel)
    args_file = directory / "args.json"
    args_file.write_text(json.dumps(spec.get("args", {}), ensure_ascii=False), encoding="utf-8")
    prefix = {".py": [sys.executable], ".sh": ["bash"],
              ".ps1": ["powershell", "-NoProfile", "-NonInteractive", "-File"]}[path.suffix]
    (directory / "script-source.json").write_text(json.dumps({"sha256": digest(path.read_bytes()),
        "name": spec.get("script", spec.get("entry")), "commit": spec.get("commit")}), encoding="utf-8")
    return [*prefix, str(path), "--args-file", str(args_file)]
