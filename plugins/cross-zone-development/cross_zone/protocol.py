"""Strict transport envelopes; assistant prose is never a shell command."""

import hashlib
import json
import re
import uuid

PROTOCOL = "cross-zone/v2"
MARKER = "CROSS_ZONE_V2\n"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
REVISION = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
# HAPI session URLs look like <hub origin>/sessions/<UUID>; only the session
# part is used, never the hub origin, credentials or query string.
SESSION_URL = re.compile(r"^\S{1,300}$")


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


def parse(text, target):
    if not text or not text.startswith(MARKER):
        return None
    if len(text.encode("utf-8")) > 24000:
        raise ProtocolError("request_too_large")
    try:
        event = json.loads(text[len(MARKER):], object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise ProtocolError("invalid_json") from exc
    if not isinstance(event, dict) or event.get("protocol") != PROTOCOL:
        raise ProtocolError("invalid_protocol")
    if event.get("target") != target:
        return None
    base = {"protocol", "type", "event_id", "task_id", "iteration", "target"}
    kind = event.get("type")
    if not isinstance(kind, str):
        raise ProtocolError("invalid_type")
    if kind == "OPEN":
        # Green-originated request; blue must not inject it. Green uses open_event().
        raise ProtocolError("invalid_direction")
    extra = {
        "TASK": {"goal", "checks", "timeout_seconds"},
        "ANSWER": {"question_id", "answer"},
        "CANCEL": set(),
    }.get(kind)
    fields = set(event)
    optional_revision = {"revision"} if "revision" in fields else set()
    valid_fields = fields == base | extra | optional_revision
    if extra is None or not valid_fields:
        raise ProtocolError("invalid_fields")
    for field in ("event_id", "task_id", "target"):
        if not isinstance(event[field], str) or not ID.fullmatch(event[field]):
            raise ProtocolError("invalid_id")
    if type(event["iteration"]) is not int or not 1 <= event["iteration"] <= 10000:
        raise ProtocolError("invalid_iteration")
    if "revision" in event and (not isinstance(event["revision"], str) or not REVISION.fullmatch(event["revision"])):
        raise ProtocolError("invalid_revision")
    if kind == "TASK":
        if not isinstance(event["goal"], str) or not 1 <= len(event["goal"]) <= 6000:
            raise ProtocolError("invalid_goal")
        checks = event["checks"]
        if not isinstance(checks, list) or not 1 <= len(checks) <= 20:
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
        if type(event["timeout_seconds"]) is not int or not 1 <= event["timeout_seconds"] <= 86400:
            raise ProtocolError("invalid_timeout")
    elif kind == "ANSWER":
        if not isinstance(event["question_id"], str) or not ID.fullmatch(event["question_id"]):
            raise ProtocolError("invalid_question_id")
        if not isinstance(event["answer"], str) or not 1 <= len(event["answer"]) <= 6000:
            raise ProtocolError("invalid_answer")
    return event


def wire(event):
    return MARKER + canonical(event)


def open_event(target, session_url):
    """Green-originated OPEN envelope requesting blue to start cross-zone work.

    Not a control command: it carries no task binding and blue never echoes it.
    session_url is the relative `sessions/<UUID>` reference constructed from the
    command-line session ID. It is never read from configuration.
    """
    return {"protocol": PROTOCOL, "type": "OPEN", "event_id": "green-open-" + uuid.uuid4().hex,
            "target": target, "session_url": session_url}
