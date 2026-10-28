import json
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_REVIEW_TIMEOUT_SECONDS = 300


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    url = urlsplit(config["hub_url"])
    if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError("hub_url must be an HTTP(S) base URL without credentials/query")
    config["hub_url"] = config["hub_url"].rstrip("/") + "/"
    # Retain an old identity only to verify the existing database binding during upgrade.
    config.pop("_legacy_target", None)
    legacy_target = config.pop("target", None)
    if isinstance(legacy_target, str):
        config["_legacy_target"] = legacy_target
    config.setdefault("access_key", None)
    if config["access_key"] is not None and (not isinstance(config["access_key"], str) or not config["access_key"].strip()):
        raise ValueError("access_key must be a non-empty string or null")
    ignored = {"session_id", "session_url", "state_dir", "workspace_dir", "key_env",
               "task_binding", "repositories", "profiles", "profile",
               "egress_deny_patterns"}
    for field in ignored:
        config.pop(field, None)
    config.setdefault("poll_seconds", 5)
    config.setdefault("sse", True)
    config.setdefault("max_questions", 3)
    config.setdefault("max_task_seconds", 1800)
    config.setdefault("agent_command", ["codeagent"])
    config.setdefault("agent_live_log", True)
    config.setdefault("agent_log_max_chars", 2000)
    if not isinstance(config["agent_command"], list) or not config["agent_command"] or any(
        not isinstance(v, str) or not v for v in config["agent_command"]
    ):
        raise ValueError("agent_command must be an argv array")
    if not isinstance(config["agent_live_log"], bool):
        raise ValueError("agent_live_log must be a boolean")
    if not isinstance(config["agent_log_max_chars"], int) or not 100 <= config["agent_log_max_chars"] <= 20000:
        raise ValueError("agent_log_max_chars out of range")
    if not 0.1 <= config["poll_seconds"] <= 300:
        raise ValueError("poll_seconds out of range")
    if (type(config["max_questions"]) is not int or not 0 <= config["max_questions"] <= 3
            or type(config["max_task_seconds"]) is not int
            or not 600 <= config["max_task_seconds"] <= 86400):
        raise ValueError("task budget out of range")
    settings = config.setdefault("exec_review", {})
    if not isinstance(settings, dict) or set(settings) - {"base_url", "model", "api_key", "timeout_seconds"}:
        raise ValueError("exec_review must be an object with base_url, model, api_key and timeout_seconds")
    settings.setdefault("base_url", "http://techdev.hicomputing.huawei.com:18000/v1")
    settings.setdefault("model", "Qwen3.8")
    settings.setdefault("api_key", None)
    settings.setdefault("timeout_seconds", DEFAULT_REVIEW_TIMEOUT_SECONDS)
    endpoint = urlsplit(settings["base_url"]) if isinstance(settings["base_url"], str) else None
    if (endpoint is None or endpoint.scheme not in ("http", "https") or not endpoint.netloc
            or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
        raise ValueError("exec_review.base_url must be an HTTP(S) API base URL without credentials/query")
    settings["base_url"] = settings["base_url"].rstrip("/")
    if not isinstance(settings["model"], str) or not settings["model"].strip():
        raise ValueError("exec_review.model must be a non-empty string")
    key = settings["api_key"]
    if key is not None and (not isinstance(key, str) or not key.strip()
                            or any(ord(c) < 32 or ord(c) == 127 for c in key)):
        raise ValueError("exec_review.api_key must be a non-empty header-safe string or null")
    if type(settings["timeout_seconds"]) is not int or not 1 <= settings["timeout_seconds"] <= 600:
        raise ValueError("exec_review.timeout_seconds must be an integer between 1 and 600")
    return config
