"""Bounded structured export. Pattern checks supplement, not replace, AI review."""

import json
import re

from .protocol import PROTOCOL, canonical

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["RESULT", "QUESTION"]},
        "status": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED", "NEEDS_HUMAN"]},
        "summary": {"type": "string", "maxLength": 3000},
        "checks": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED", "NOT_RUN"]}},
            "required": ["id", "status"],
        }},
        "error_code": {"type": "string", "maxLength": 100},
        "question": {"type": "string", "maxLength": 800,
                     "description": "Use an empty string for RESULT; question text for QUESTION."},
        "local_modification_tested": {"type": "boolean"},
        "local_modification_outcome": {"type": "string", "enum": ["PASS", "FAIL", "NOT_RUN"]},
        "egress_reviewed": {"type": "boolean"},
    },
    "required": ["kind", "status", "summary", "checks", "error_code", "question",
                 "local_modification_tested", "local_modification_outcome", "egress_reviewed"],
}


def review(value, request, secrets=(), execution=None):
    if not isinstance(value, dict):
        raise ValueError(f"result_schema: expected object, got {type(value).__name__}")
    missing = set(SCHEMA["required"]) - set(value)
    unexpected = set(value) - set(SCHEMA["required"])
    if missing or unexpected:
        raise ValueError(f"result_schema: missing fields={sorted(missing)}, unexpected field count={len(unexpected)}")
    for key, spec in SCHEMA["properties"].items():
        item = value[key]
        if spec["type"] == "string":
            if not isinstance(item, str):
                raise ValueError(f"result_schema: {key} expected string, got {type(item).__name__}")
            limit = spec.get("maxLength", 100)
            if len(item) > limit:
                raise ValueError(f"result_schema: {key} length={len(item)} exceeds limit={limit}")
            if "enum" in spec and item not in spec["enum"]:
                raise ValueError(f"result_schema: {key} must be one of {spec['enum']}")
        elif spec["type"] == "boolean" and type(item) is not bool:
            raise ValueError(f"result_schema: {key} expected boolean, got {type(item).__name__}")
    direct = request.get("type") == "EXEC" and request.get("ai_review", True) is False
    if direct and (not execution or value["egress_reviewed"] is not False):
        raise ValueError("direct_result: requires execution facts and no AI review claim")
    if not direct and value["egress_reviewed"] is not True:
        raise ValueError("egress_not_reviewed: egress_reviewed must be true after reviewing the export")
    checks = value["checks"]
    if not isinstance(checks, list):
        raise ValueError(f"result_checks: checks expected array, got {type(checks).__name__}")
    if len(checks) > 20:
        raise ValueError(f"result_checks: checks count={len(checks)} exceeds limit=20")
    wanted = {c["id"] for c in request["checks"]}
    seen = set()
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or set(check) != {"id", "status"}:
            raise ValueError(f"result_checks: checks[{index}] must contain only id and status")
        if not isinstance(check["id"], str) or check["id"] not in wanted or check["id"] in seen:
            raise ValueError(f"result_checks: checks[{index}].id must uniquely match a requested check")
        if check["status"] not in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
            raise ValueError(f"result_checks: checks[{index}].status must be PASS, FAIL, BLOCKED or NOT_RUN")
        seen.add(check["id"])
    if value["kind"] == "RESULT" and value["question"].strip().casefold() in {"", "none", "null", "n/a"}:
        value = dict(value, question="")
    if value["kind"] == "RESULT":
        if seen != wanted:
            raise ValueError(f"incomplete_result: missing requested checks={sorted(wanted - seen)}")
        if value["question"]:
            raise ValueError(f"incomplete_result: RESULT question must be empty; length={len(value['question'])}")
        if value["status"] == "PASS" and (
            any(c["status"] != "PASS" for c in checks)
            or ("revision" in request and value["local_modification_tested"])
        ):
            failed = [c["id"] for c in checks if c["status"] != "PASS"]
            raise ValueError(f"baseline_not_passed: non-PASS checks={failed}; "
                             f"local_modification_tested={value['local_modification_tested']}")
    elif not value["question"]:
        raise ValueError("empty_question: QUESTION requires non-empty question text")
    # Scan actual text: JSON-escaped newlines can hide word boundaries.
    literal = "\n".join(item if isinstance(item, str) else canonical({key: item})
                        for key, item in value.items())
    # Reserve the final RESULT envelope, not just the agent's structured fields.
    exported = {k: v for k, v in value.items() if k not in ("kind", "egress_reviewed")}
    envelope = {"protocol": PROTOCOL, "type": "RESULT", "event_id": "green-" + "0" * 32,
                **{k: request[k] for k in ("task_id", "iteration", "target")},
                **exported, "worktree_modified": False}
    if "revision" in request:
        envelope["revision"] = request["revision"]
    if execution:
        envelope["execution"] = execution
        # Reserve the longest bridge-owned terminal status before applying execution facts.
        envelope["status"] = "NEEDS_HUMAN"
    size = len(json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
    if size > 4096:
        raise ValueError(f"egress_size_limit: RESULT JSON bytes={size} exceeds limit=4096; shorten summary")
    # Reject; never partially redact a payload and accidentally change its meaning.
    patterns = [r"(?i)\b(?:bearer|password|api[_ -]?key|access[_ -]?token)\s*[:= ]\s*\S+",
                r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}"]
    if any(secret and secret in literal for secret in secrets) or any(re.search(p, literal) for p in patterns):
        fields = [key for key, item in value.items()
                  if any(secret and secret in canonical({key: item}) for secret in secrets)
                  or any(re.search(p, item if isinstance(item, str) else canonical({key: item})) for p in patterns)]
        raise ValueError(f"egress_content_rejected: credential match in fields={fields}; "
                         "review these fields locally; matching content withheld")
    return exported


def failure_detail(detail, secrets=()):
    """Export a bounded diagnostic excerpt, never the agent's stdout."""
    if not isinstance(detail, str):
        return ""
    for secret in sorted((s for s in secrets if isinstance(s, str) and s), key=len, reverse=True):
        detail = detail.replace(secret, "[REDACTED]")
    credential = r"(?:password|passwd|api[_ -]?key|access[_ -]?(?:key|token)|token|secret)"
    detail = re.sub(
        r"(?i)(?:\b(?:bearer|basic)\s+|--" + credential + r"(?:=|\s+)|\b" + credential
        + r"[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)",
        "[REDACTED]", detail)
    detail = re.sub(r"\b(?:sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]{12,}", "[REDACTED]", detail)
    detail = re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", detail)
    detail = "".join(c if c in "\n\t" or ord(c) >= 32 else "?" for c in detail)
    while len(json.dumps(detail, ensure_ascii=False).encode("utf-8")) > 2000:
        detail = detail[:len(detail) // 2] + "...[truncated]"
    return detail
