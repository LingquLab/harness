"""Bounded structured export. Pattern checks supplement, not replace, AI review."""

import re

from .protocol import canonical

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "kind": {"type": "string", "enum": ["RESULT", "QUESTION"]},
        "status": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED", "NEEDS_HUMAN"]},
        "summary": {"type": "string", "maxLength": 1000},
        "checks": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": ["PASS", "FAIL", "BLOCKED", "NOT_RUN"]}},
            "required": ["id", "status"],
        }},
        "error_code": {"type": "string", "maxLength": 100},
        "question": {"type": "string", "maxLength": 800},
        "local_modification_tested": {"type": "boolean"},
        "local_modification_outcome": {"type": "string", "enum": ["PASS", "FAIL", "NOT_RUN"]},
        "egress_reviewed": {"type": "boolean"},
    },
    "required": ["kind", "status", "summary", "checks", "error_code", "question",
                 "local_modification_tested", "local_modification_outcome", "egress_reviewed"],
}


def review(value, request, secrets=(), deny_patterns=()):
    if not isinstance(value, dict) or set(value) != set(SCHEMA["required"]):
        raise ValueError("result_schema")
    for key, spec in SCHEMA["properties"].items():
        item = value[key]
        if spec["type"] == "string":
            if not isinstance(item, str) or len(item) > spec.get("maxLength", 100):
                raise ValueError("result_schema")
            if "enum" in spec and item not in spec["enum"]:
                raise ValueError("result_schema")
        elif spec["type"] == "boolean" and type(item) is not bool:
            raise ValueError("result_schema")
    if value["egress_reviewed"] is not True:
        raise ValueError("egress_not_reviewed")
    checks = value["checks"]
    if not isinstance(checks, list) or len(checks) > 20:
        raise ValueError("result_checks")
    wanted = {c["id"] for c in request["checks"]}
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"id", "status"}:
            raise ValueError("result_checks")
        if not isinstance(check["id"], str) or check["id"] not in wanted or check["id"] in seen:
            raise ValueError("result_checks")
        if check["status"] not in ("PASS", "FAIL", "BLOCKED", "NOT_RUN"):
            raise ValueError("result_checks")
        seen.add(check["id"])
    if value["kind"] == "RESULT":
        if seen != wanted or value["question"]:
            raise ValueError("incomplete_result")
        if value["status"] == "PASS" and (
            any(c["status"] != "PASS" for c in checks) or value["local_modification_tested"]
        ):
            raise ValueError("baseline_not_passed")
    elif not value["question"]:
        raise ValueError("empty_question")
    literal = canonical(value)
    if len(literal.encode("utf-8")) > 3200:
        raise ValueError("egress_size_limit")
    # Reject; never partially redact a payload and accidentally change its meaning.
    patterns = [r"```", r"https?://", r"(?i)\b(?:bearer|password|api[_ -]?key|access[_ -]?token)\s*[:= ]\s*\S+",
                r"\b(?:\d{1,3}\.){3}\d{1,3}\b", r"[A-Za-z]:[\\/]", r"\\\\[A-Za-z0-9]",
                r"(?:^|[\s\"'])/(?:home|root|tmp|var|etc|workspace|Users)/",
                r"\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{12,}", *deny_patterns]
    if any(secret and secret in literal for secret in secrets) or any(re.search(p, literal) for p in patterns):
        raise ValueError("egress_content_rejected")
    return {k: v for k, v in value.items() if k not in ("kind", "egress_reviewed")}
