"""Strict transport envelopes; assistant prose is never a shell command."""

import hashlib
import json
import re
import uuid

from . import __version__

PROTOCOL = "cross-zone/v3"
MARKER = "CROSS_ZONE\n"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
REVISION = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")


class ProtocolError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def assistant_text(message):
    """Match HAPI's Codex/Claude envelopes, excluding tools and sidechains."""
    envelope = message.get("content")
    if not isinstance(envelope, dict) or envelope.get("role") != "agent":
        return None
    content = envelope.get("content")
    if not isinstance(content, dict):
        return None
    data = content.get("data")
    if not isinstance(data, dict):
        return None
    if any(data.get(k) for k in ("isSidechain", "parentToolUseId", "parent_tool_use_id")):
        return None
    if data.get("scope_role") not in (None, "main", "root", "parent"):
        return None
    scope = data.get("scope")
    if isinstance(scope, dict) and scope.get("role") not in (None, "main", "root", "parent"):
        return None
    if content.get("type") == "codex" and data.get("type") == "message":
        return data.get("message") if isinstance(data.get("message"), str) else None
    if content.get("type") == "output" and data.get("type") == "assistant":
        body = data.get("message", {})
        if not isinstance(body, dict):
            return None
        blocks = body.get("content")
        if isinstance(blocks, str):
            return blocks
        if isinstance(blocks, list) and all(
            isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
            for b in blocks
        ):
            return "\n".join(b["text"] for b in blocks)
    return None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate_json_key")
        result[key] = value
    return result


def read_wire(text):
    if not text or not text.startswith(MARKER):
        return None
    if len(text.encode("utf-8")) > 24000:
        raise ProtocolError("request_too_large")
    body = text[len(MARKER):].strip()
    if body.startswith("```json\n") and body.endswith("\n```"):
        body = body[len("```json\n"):-len("\n```")]
    try:
        return json.loads(body, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError("invalid_json") from exc


def parse(text):
    if not text or not text.startswith(MARKER):
        return None
    event = read_wire(text)
    if not isinstance(event, dict) or event.get("protocol") != PROTOCOL:
        raise ProtocolError("invalid_protocol")
    base = {"protocol", "type", "event_id", "task_id", "iteration"}
    kind = event.get("type")
    if not isinstance(kind, str):
        raise ProtocolError("invalid_type")
    if kind == "OPEN":
        # Green-originated request; blue must not inject it. Green uses open_event().
        raise ProtocolError("invalid_direction")
    extra = {
        "TASK": {"goal", "checks", "timeout_seconds"},
        "EXEC": {"timeout_seconds", "execution", "execution_timeout_seconds"},
        "ANSWER": {"question_id", "answer"},
        "CANCEL": set(),
    }.get(kind)
    fields = set(event)
    optional_revision = {"revision"} if "revision" in fields else set()
    if kind == "EXEC":
        if "ai_review" in fields:
            extra = extra | {"ai_review"}
            if type(event["ai_review"]) is not bool:
                raise ProtocolError("invalid_ai_review")
        # EXEC never carries goal. Only reviewed execution needs check prose;
        # keep supplied direct check IDs for result binding and deduplication.
        if event.get("ai_review", False):
            extra |= {"checks"}
        else:
            extra |= fields & {"checks"}
    if extra is None or fields != base | extra | optional_revision:
        raise ProtocolError("invalid_fields")
    for field in ("event_id", "task_id"):
        if not isinstance(event[field], str) or not ID.fullmatch(event[field]):
            raise ProtocolError("invalid_id")
    if type(event["iteration"]) is not int or not 1 <= event["iteration"] <= 10000:
        raise ProtocolError("invalid_iteration")
    if "revision" in event and (not isinstance(event["revision"], str) or not REVISION.fullmatch(event["revision"])):
        raise ProtocolError("invalid_revision")
    if kind == "EXEC" and "revision" in event:
        raise ProtocolError("exec_revision_not_supported")
    if kind in {"TASK", "EXEC"}:
        if "goal" in event and (not isinstance(event["goal"], str) or not 1 <= len(event["goal"]) <= 6000):
            raise ProtocolError("invalid_goal")
        checks = event.get("checks", [])
        if not isinstance(checks, list) or ("checks" in event and not 1 <= len(checks) <= 20):
            raise ProtocolError("invalid_checks")
        names = set()
        for check in checks:
            if not isinstance(check, dict) or set(check) != {"id", "action", "expected"}:
                raise ProtocolError("invalid_check")
            if not isinstance(check["id"], str) or not ID.fullmatch(check["id"]) or check["id"] in names:
                raise ProtocolError("invalid_check_id")
            names.add(check["id"])
            if any(not isinstance(check[k], str) or not 1 <= len(check[k]) <= 2000 for k in ("action", "expected")):
                raise ProtocolError("invalid_check_text")
        if type(event["timeout_seconds"]) is not int or not 600 <= event["timeout_seconds"] <= 86400:
            raise ProtocolError("invalid_timeout")
        if kind == "EXEC":
            duration = event["execution_timeout_seconds"]
            if type(duration) is not int or not 1 <= duration <= event["timeout_seconds"] - 60:
                raise ProtocolError("invalid_execution_timeout")
            execution = event["execution"]
            if not isinstance(execution, dict):
                raise ProtocolError("invalid_execution")
            if set(execution) == {"argv"}:
                argv = execution["argv"]
                if (not isinstance(argv, list) or not 1 <= len(argv) <= 128
                        or any(not isinstance(arg, str) or len(arg) > 4000 or "\0" in arg for arg in argv)
                        or not argv[0]):
                    raise ProtocolError("invalid_execution_argv")
            elif set(execution) == {"interpreter", "script"}:
                if execution["interpreter"] not in ("bash", "powershell", "python"):
                    raise ProtocolError("invalid_execution_interpreter")
                script = execution["script"]
                if not isinstance(script, str) or not 1 <= len(script) <= 12000 or "\0" in script:
                    raise ProtocolError("invalid_execution_script")
            else:
                raise ProtocolError("invalid_execution_fields")
    elif kind == "ANSWER":
        if not isinstance(event["question_id"], str) or not ID.fullmatch(event["question_id"]):
            raise ProtocolError("invalid_question_id")
        if not isinstance(event["answer"], str) or not 1 <= len(event["answer"]) <= 6000:
            raise ProtocolError("invalid_answer")
    return event


def parse_connection(text):
    """Blue connection controls are consumed only by the discovery supervisor."""
    event = read_wire(text)
    if (not isinstance(event, dict) or not isinstance(event.get("type"), str)
            or event["type"] not in {"OPEN", "CLOSE"}):
        return None
    if (set(event) != {"protocol", "type", "event_id"}
            or event["protocol"] != PROTOCOL
            or not isinstance(event["event_id"], str)
            or not ID.fullmatch(event["event_id"])):
        raise ProtocolError("invalid_connection")
    return event


def wire(event, *, readable=False):
    if readable:
        body = json.dumps(event, ensure_ascii=False, sort_keys=True, indent=2)
        return MARKER + "```json\n" + body + "\n```"
    return MARKER + canonical(event)


def open_event(session_url):
    """Green-originated OPEN envelope announcing a ready connection.

    Not a control command: it carries no task binding and blue never echoes it.
    session_url is the relative `sessions/<UUID>` reference constructed from the
    command-line session ID. It is never read from configuration.
    """
    return {"protocol": PROTOCOL, "type": "OPEN", "event_id": "green-open-" + uuid.uuid4().hex,
            "version": __version__, "session_url": session_url}
