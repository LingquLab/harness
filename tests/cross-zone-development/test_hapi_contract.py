from __future__ import annotations

import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "cross-zone-development"
SKILL = PLUGIN / "skills" / "cross-zone-development"
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")
OPEN_ID = re.compile(r"green-open-[0-9a-f]+\Z")
SESSION_URL = re.compile(r"sessions/[A-Za-z0-9][A-Za-z0-9-]{0,127}\Z")


def validate_open(event: object) -> dict[str, object]:
    if not isinstance(event, dict):
        raise ValueError("OPEN must be an object")
    required = {"protocol", "type", "event_id", "target", "session_url"}
    if set(event) != required:
        raise ValueError("OPEN fields do not match")
    if event["protocol"] != "cross-zone/v2" or event["type"] != "OPEN":
        raise ValueError("not an OPEN event")
    if not isinstance(event["event_id"], str) or not OPEN_ID.fullmatch(event["event_id"]):
        raise ValueError("invalid event ID")
    if not isinstance(event["target"], str) or not ID.fullmatch(event["target"]):
        raise ValueError("invalid target")
    if not isinstance(event["session_url"], str) or not SESSION_URL.fullmatch(event["session_url"]):
        raise ValueError("invalid session URL")
    return event


class HapiContractTest(unittest.TestCase):
    def test_open_is_green_originated_and_not_task_bound(self) -> None:
        event = validate_open({
            "protocol": "cross-zone/v2",
            "type": "OPEN",
            "event_id": "green-open-0123456789abcdef",
            "target": "green-dev",
            "session_url": "sessions/01234567-89ab-cdef-0123-456789abcdef",
        })
        self.assertNotIn("task_id", event)
        self.assertNotIn("iteration", event)
        self.assertNotIn("revision", event)

    def test_open_rejects_task_fields_hosts_queries_and_traversal(self) -> None:
        base = {
            "protocol": "cross-zone/v2",
            "type": "OPEN",
            "event_id": "green-open-0123456789abcdef",
            "target": "green-dev",
            "session_url": "sessions/01234567-89ab-cdef-0123-456789abcdef",
        }
        invalid = [
            {**base, "task_id": "task-1"},
            {**base, "event_id": "blue-open-0123"},
            {**base, "session_url": "https://hapi.example/sessions/id"},
            {**base, "session_url": "sessions/id?token=secret"},
            {**base, "session_url": "sessions/../other"},
            {**base, "session_url": "sessions/%2e%2e/other"},
        ]
        for event in invalid:
            with self.subTest(event=event), self.assertRaises(ValueError):
                validate_open(event)

    def test_templates_keep_session_and_state_out_of_configuration(self) -> None:
        for name in ("config.example.json", "config.windows.json"):
            config = json.loads((PLUGIN / name).read_text(encoding="utf-8"))
            self.assertEqual(config["access_key"], "REPLACE_WITH_HAPI_ACCESS_KEY")
            self.assertNotIn("session_id", config)
            self.assertNotIn("session_url", config)
            self.assertNotIn("state_dir", config)
            self.assertNotIn("key_env", config)
            self.assertNotIn("token", config)
            self.assertEqual(config["max_questions"], 3)
            binding = config["task_binding"]
            repository = config["repositories"][binding["repository"]]
            self.assertEqual(repository["remote"], "origin")
            self.assertIn(binding["scope_profile"], repository["profiles"])
            self.assertIn(binding["scope_profile"], config["profiles"])

    def test_skill_routes_open_and_preserves_result_invariants(self) -> None:
        protocol = (SKILL / "references" / "protocol.md").read_text(encoding="utf-8")
        blue = (SKILL / "references" / "blue-zone.md").read_text(encoding="utf-8")
        green = (SKILL / "references" / "green-zone.md").read_text(encoding="utf-8")
        self.assertIn("## Green-originated requests", protocol)
        self.assertIn("never apply TASK validation", protocol)
        self.assertIn("Blue must not create, inject, echo", protocol)
        self.assertIn("send one formal TASK", blue)
        self.assertIn("blue neither requests nor names", blue)
        self.assertIn("./start-bridge.sh open <session-id>", green)
        self.assertIn("not configuration", green)
        self.assertIn("preflighted local binding", green)
        self.assertIn("every requested check", protocol)
        self.assertIn("egress_reviewed=true", protocol)
        self.assertIn("creates a task-owned commit, and pushes", protocol)
        self.assertIn("prepares an isolated clean", protocol)

        task_line = next(
            line for line in protocol.splitlines()
            if line.startswith('{"protocol":"cross-zone/v2","type":"TASK"')
        )
        task = json.loads(task_line)
        self.assertNotIn("repository", task)
        self.assertNotIn("scope_profile", task)
        self.assertEqual(task["revision"], "0123456789012345678901234567890123456789")

    def test_removed_github_transport_is_not_shipped(self) -> None:
        self.assertFalse((SKILL / "references" / "github-access.md").exists())
        self.assertFalse((SKILL / "scripts" / "github_issue.py").exists())


if __name__ == "__main__":
    unittest.main()
