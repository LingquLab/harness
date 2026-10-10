import json
from pathlib import Path
from urllib.parse import urlsplit


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    url = urlsplit(config["hub_url"])
    if url.scheme not in ("http", "https") or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError("hub_url must be an HTTP(S) base URL without credentials/query")
    config["hub_url"] = config["hub_url"].rstrip("/") + "/"
    config.setdefault("access_key", None)
    if config["access_key"] is not None and (not isinstance(config["access_key"], str) or not config["access_key"].strip()):
        raise ValueError("access_key must be a non-empty string or null")
    deprecated = {"session_id", "session_url", "state_dir", "workspace_dir", "key_env"} & set(config)
    if deprecated:
        raise ValueError("remove deprecated config fields: " + ", ".join(sorted(deprecated)))
    config.setdefault("poll_seconds", 5)
    config.setdefault("sse", True)
    config.setdefault("max_questions", 3)
    config.setdefault("max_task_seconds", 1800)
    config.setdefault("egress_deny_patterns", [])
    config.setdefault("agent_command", ["codeagent"])
    config.setdefault("agent_live_log", True)
    config.setdefault("agent_log_max_chars", 2000)
    deprecated_binding = {"task_binding", "repositories", "profiles"} & set(config)
    if deprecated_binding:
        raise ValueError("remove repository binding fields: " + ", ".join(sorted(deprecated_binding)))
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
    if not 0 <= config["max_questions"] <= 10 or not 1 <= config["max_task_seconds"] <= 86400:
        raise ValueError("task budget out of range")
    profile = config.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    if not isinstance(profile.get("allowed_tools"), list) or not profile["allowed_tools"]:
        raise ValueError("profile needs allowed_tools")
    if any(not isinstance(v, str) or not v for v in profile["allowed_tools"]):
        raise ValueError("allowed_tools must contain strings")
    if not isinstance(profile.get("instructions"), str) or not profile["instructions"]:
        raise ValueError("profile needs instructions")
    return config
