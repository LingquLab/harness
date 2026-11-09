from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import test_bridge as fixtures
from test_execution import exec_task
from cross_zone import __version__
from cross_zone.config import load_config
from cross_zone.controller import Bridge
from cross_zone.execution import DirectExecutor
from cross_zone.egress import review
from cross_zone.reviewer import EVIDENCE_LIMIT, OpenAIReviewer


class ReviewAPITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = fixtures.config(self.tmp.name)
        self.calls = []
        self.user_agents = []
        self.request_started = threading.Event()
        self.body = self.response(fixtures.output(summary="中文检查通过"))
        self.status = 200
        self.delay = 0
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                case.user_agents.append(self.headers.get("User-Agent"))
                case.calls.append((self.path, self.headers.get("Authorization"),
                                   json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                case.request_started.set()
                time.sleep(case.delay)
                self.send_response(case.status)
                if case.status == 302:
                    self.send_header("Location", "/redirect-target")
                self.end_headers()
                try:
                    self.wfile.write(case.body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.key = "private-review-credential"
        self.cfg["exec_review"] = {"base_url": f"http://127.0.0.1:{self.server.server_port}/v1", "model": "Qwen3.8",
                                   "api_key": self.key, "timeout_seconds": 3}
        self.reviewer = OpenAIReviewer(self.cfg)
        self.runner = DirectExecutor(self.cfg, self.reviewer)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    @staticmethod
    def response(output, finish_reason="stop", **message):
        return json.dumps({"choices": [{"finish_reason": finish_reason,
                                        "message": {"content": json.dumps(output, ensure_ascii=False), **message}}]},
                          ensure_ascii=False).encode("utf-8")

    def run_exec(self, event=None, cancel=None):
        return self.runner.run(event or exec_task(), None, None, time.time() + 90,
                               cancel or threading.Event(), [])

    def review_path(self):
        return Path(self.cfg["state_dir"]) / "runs/task-1/1/execution/review.json"

    def test_real_exec_requests_one_tool_free_review_and_saves_validated_result(self):
        with self.assertLogs("cross_zone.reviewer", level="INFO") as captured:
            result = self.run_exec()
        self.assertEqual(result["output"]["status"], "PASS")
        self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
        self.assertEqual(len(self.calls), 1)
        path, auth, payload = self.calls[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(auth, "Bearer " + self.key)
        self.assertEqual(self.user_agents, [f"CrossZoneBridge/{__version__}"])
        self.assertEqual(payload["model"], "Qwen3.8")
        self.assertFalse(payload["stream"])
        self.assertNotIn("tools", payload)
        evidence = json.loads(payload["messages"][1]["content"])
        self.assertEqual(evidence["evidence"]["stdout"], "done\n")
        self.assertEqual(evidence["evidence"]["stderr"], "")
        self.assertEqual(json.loads(evidence["evidence"]["receipt"])["status"], "EXITED")
        self.assertNotIn("argv", evidence)
        self.assertNotIn("goal", evidence)
        self.assertNotIn(self.key, json.dumps(payload))
        self.assertEqual(json.loads(self.review_path().read_text()), result["output"])
        self.assertNotIn(self.key, str(captured.output))
        self.assertNotIn("中文检查通过", str(captured.output))

    def test_bridge_uses_api_for_review_without_invoking_cli(self):
        agent = fixtures.FakeAgent()
        client = fixtures.FakeClient()
        bridge = Bridge(self.cfg, client, agent)
        try:
            bridge.bind()
            client.rows.append(fixtures.message(exec_task(), 1))
            bridge.catch_up()
            self.finish(bridge)
            self.assertFalse(agent.calls)
            bridge.flush()
            event = client.sent[-1][1]
            self.assertEqual(event["status"], "PASS")
            self.assertEqual(event["execution"]["exit_code"], 0)
            self.assertNotIn("egress_reviewed", event)
            self.assertNotIn(self.key, json.dumps(event))
        finally:
            bridge.close()

    @staticmethod
    def finish(bridge):
        for _ in range(500):
            bridge.work()
            if not bridge.active:
                return
            time.sleep(0.01)
        raise AssertionError("Bridge did not finish")

    def test_api_cannot_override_nonzero_exit(self):
        agent, client = fixtures.FakeAgent(), fixtures.FakeClient()
        bridge = Bridge(self.cfg, client, agent)
        try:
            bridge.bind()
            event = exec_task(execution={"interpreter": "python", "script": "raise SystemExit(7)"})
            client.rows.append(fixtures.message(event, 1))
            bridge.catch_up()
            self.finish(bridge)
            bridge.flush()
            result = client.sent[-1][1]
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["execution"]["exit_code"], 7)
        finally:
            bridge.close()

    def test_direct_exec_and_task_do_not_call_api(self):
        self.assertEqual(self.run_exec(exec_task(ai_review=False))["output"]["status"], "PASS")
        agent, client = fixtures.FakeAgent(), fixtures.FakeClient()
        bridge = Bridge(self.cfg, client, agent)
        try:
            bridge.bind()
            client.rows.append(fixtures.message(fixtures.general_task(), 1))
            bridge.catch_up()
            self.finish(bridge)
            self.assertEqual(len(agent.calls), 1)
            self.assertEqual(self.calls, [])
        finally:
            bridge.close()

    def test_invalid_model_results_fall_back_to_saved_stdout(self):
        variants = [b"not-json", b'{"choices": []}', self.response(fixtures.output(), finish_reason="length"),
                    self.response(fixtures.output(), tool_calls=[{"name": "anything"}]),
                    self.response(fixtures.output(kind="QUESTION", question="Please run a command")),
                    self.response(fixtures.output(egress_reviewed=False)),
                    self.response(fixtures.output(checks=[])),
                    self.response(fixtures.output(local_modification_tested=True)),
                    self.response(fixtures.output(summary=self.key)),
                    self.response(fixtures.output(summary="password=never-export")),
                    self.response(fixtures.output(summary="sk-testcredential123456789"))]
        for index, body in enumerate(variants):
            with self.subTest(index=index):
                self.body = body
                result = self.run_exec(exec_task(task_id=f"invalid-{index}"))
                self.assertEqual(result["output"]["error_code"], "AI_REVIEW_FALLBACK")
                self.assertIn("done", result["output"]["summary"])
                self.assertTrue(result["ai_review_fallback"])
                self.assertNotIn(self.key, json.dumps(result))
                self.assertNotIn("never-export", json.dumps(result))
                self.assertFalse((Path(self.cfg["state_dir"]) / f"runs/invalid-{index}/1/execution/review.json").exists())
        self.assertEqual(len(self.calls), len(variants))

    def test_review_failure_logs_identify_stage_without_response_content(self):
        cases = [
            (401, self.key.encode(), "HTTP 401"),
            (200, self.key.encode(), "response_json"),
            (200, self.response(fixtures.output(summary=self.key), finish_reason="length"),
             "incomplete_response"),
            (200, self.response(fixtures.output(summary=self.key)), "result_validation"),
        ]
        for index, (status, body, expected) in enumerate(cases):
            with self.subTest(expected=expected):
                self.status, self.body = status, body
                with self.assertLogs("cross_zone.reviewer", level="WARNING") as captured:
                    result = self.run_exec(exec_task(task_id=f"diagnostic-{index}"))
                logs = "\n".join(captured.output)
                self.assertIn(expected, logs)
                self.assertNotIn(self.key, logs)
                self.assertEqual(result["output"]["error_code"], "AI_REVIEW_FALLBACK")
        self.assertEqual(len(self.calls), len(cases))

    def test_http_errors_and_redirect_fall_back_without_retrying_api(self):
        for index, status in enumerate((401, 500, 302)):
            self.status = status
            self.body = ("unsafe server diagnostic " + self.key).encode()
            result = self.run_exec(exec_task(task_id=f"http-{index}"))
            self.assertEqual(result["output"]["error_code"], "AI_REVIEW_FALLBACK")
            self.assertFalse(result["output"]["egress_reviewed"])
            self.assertIn("done", result["output"]["summary"])
            self.assertNotIn(self.key, json.dumps(result))
        self.assertEqual(len(self.calls), 3)

    def test_missing_or_placeholder_key_uses_direct_fallback_without_request(self):
        for index, key in enumerate((None, "REPLACE_WITH_REVIEW_API_KEY")):
            self.cfg["exec_review"]["api_key"] = key
            result = self.run_exec(exec_task(task_id=f"key-{index}"))
            self.assertEqual(result["output"]["error_code"], "AI_REVIEW_FALLBACK")
            self.assertEqual(result["execution"]["exit_code"], 0)
        self.assertEqual(self.calls, [])

    def test_evidence_is_never_silently_truncated_or_repaired(self):
        scripts = [f"print('x'*{EVIDENCE_LIMIT})", "import sys;sys.stdout.buffer.write(bytes([255]))"]
        for index, script in enumerate(scripts):
            result = self.run_exec(exec_task(task_id=f"evidence-{index}", execution={"interpreter": "python", "script": script}))
            self.assertEqual(result["status"], "NEEDS_HUMAN")
        self.assertEqual(self.calls, [])

    def test_oversized_model_response_falls_back_to_saved_stdout(self):
        self.body = b"x" * (64 * 1024 + 1)
        result = self.run_exec()
        self.assertEqual(result["output"]["error_code"], "AI_REVIEW_FALLBACK")
        self.assertFalse(self.review_path().exists())

    def test_cancel_and_deadline_drop_late_responses(self):
        # A cancelled request may still finish server-side; it must never publish
        # or persist a late result, nor replay the already-completed command.
        self.delay = 0.3
        cancel = threading.Event()
        def cancel_when_started():
            self.request_started.wait(3)
            cancel.set()
        timer = threading.Thread(target=cancel_when_started)
        timer.start()
        start = time.monotonic()
        result = self.run_exec(cancel=cancel)
        timer.join()
        self.assertEqual(result["status"], "CANCELLED")
        self.assertLess(time.monotonic() - start, 1)
        context = {"receipt": str(self.review_path().with_name("execution.json")),
                   "stdout": str(self.review_path().with_name("stdout.log")),
                   "stderr": str(self.review_path().with_name("stderr.log")),
                   "execution": {"status": "EXITED", "exit_code": 0}}
        result = self.reviewer.run(exec_task(), None, None, time.time() + 0.1, threading.Event(), [], context)
        self.assertEqual(result["status"], "TIMED_OUT")
        time.sleep(0.4)
        self.assertFalse(self.review_path().exists())
        self.assertEqual(len(self.calls), 2)

    def test_review_failure_does_not_repeat_command(self):
        self.body = b"invalid"
        event = exec_task(execution={"interpreter": "python", "script": "from pathlib import Path\np=Path('counter'); p.write_text(p.read_text()+'x' if p.exists() else 'x')"})
        first = self.run_exec(event)
        second = self.run_exec(event)
        self.assertEqual(first["execution"]["exit_code"], 0)
        self.assertEqual(first["output"]["error_code"], "AI_REVIEW_FALLBACK")
        self.assertTrue(first["ai_review_fallback"])
        self.assertEqual(second["failure"], "execution_already_attempted")
        self.assertEqual((Path(self.cfg["state_dir"]) / "counter").read_text(), "x")
        self.assertEqual(len(self.calls), 1)

    def test_local_review_timeout_falls_back_without_reexecuting_or_late_save(self):
        self.delay = 0.3
        self.cfg["exec_review"]["timeout_seconds"] = 0.05
        event = exec_task(execution={"interpreter": "python", "script":
            "from pathlib import Path\np=Path('timeout-counter');p.write_text(p.read_text()+'x' if p.exists() else 'x');print('done')"})
        result = self.run_exec(event)
        self.assertEqual(result["output"]["error_code"], "AI_REVIEW_FALLBACK")
        self.assertFalse(result["output"]["egress_reviewed"])
        self.assertEqual((Path(self.cfg["state_dir"]) / "timeout-counter").read_text(), "x")
        time.sleep(0.35)
        self.assertFalse(self.review_path().exists())
        self.assertEqual(len(self.calls), 1)

    def test_valid_negative_review_is_not_replaced_by_direct_success(self):
        for index, status in enumerate(("FAIL", "BLOCKED", "NEEDS_HUMAN")):
            value = fixtures.output(status=status, checks=[{"id": "regression", "status": "FAIL"}])
            self.body = self.response(value)
            result = self.run_exec(exec_task(task_id=f"negative-{index}"))
            self.assertEqual(result["output"]["status"], status)
            self.assertNotIn("ai_review_fallback", result)
            self.assertTrue(result["output"]["egress_reviewed"])

    def test_fallback_uses_final_direct_egress_and_preserves_request_identity(self):
        self.status = 500
        agent, client = fixtures.FakeAgent(), fixtures.FakeClient()
        bridge = Bridge(self.cfg, client, agent)
        try:
            bridge.bind()
            texts = ("safe-result", client.access_key, client.token, self.key, "password=hidden")
            for iteration, text in enumerate(texts, 1):
                event = exec_task(iteration=iteration, event_id=f"fallback-{iteration}",
                                 execution={"interpreter": "python", "script": f"print({text!r})"})
                client.rows.append(fixtures.message(event, len(client.rows) + 1))
                bridge.catch_up()
                self.finish(bridge)
                bridge.flush()
                result = client.sent[-1][1]
                self.assertEqual(result["status"], "PASS" if iteration == 1 else "NEEDS_HUMAN")
                saved = json.loads(bridge.store.get_task(event["task_id"], iteration)["request"])
                self.assertTrue(saved["ai_review"])
                self.assertNotIn("ai_review_fallback", result)
                self.assertNotIn("egress_reviewed", result)
                if iteration == 1:
                    self.assertEqual(result["error_code"], "AI_REVIEW_FALLBACK")
                    self.assertIn("no AI review", result["summary"])
                else:
                    self.assertNotIn(text, json.dumps(result))
            self.assertFalse(agent.calls)
            self.assertTrue(all(value["type"] == "RESULT" for _, value in client.sent))
        finally:
            bridge.close()

    def test_failed_review_fallback_accepts_expanded_output_budget(self):
        self.status = 500
        event = exec_task(execution={"interpreter": "python", "script":
                                    "import sys;sys.stdout.write('x'*65536)"})
        result = self.run_exec(event)
        self.assertTrue(result["ai_review_fallback"])
        exported = review(result["output"], {**event, "ai_review": False}, execution=result["execution"])
        self.assertEqual(exported["error_code"], "AI_REVIEW_FALLBACK")
        self.assertIn("x" * 65536, exported["summary"])

    def test_review_failure_direct_fallback_retains_output_limits_and_exit_facts(self):
        self.status = 500
        scripts = (("print('x'*65537)", "NEEDS_HUMAN"),
                   ("import sys;sys.stderr.write('private');print('done')", "NEEDS_HUMAN"),
                   ("import sys;sys.stdout.buffer.write(bytes([255]))", "NEEDS_HUMAN"),
                   ("import sys;sys.stdout.buffer.write(bytes([1]))", "NEEDS_HUMAN"),
                   ("raise SystemExit(7)", "FAIL"))
        for index, (script, status) in enumerate(scripts):
            result = self.run_exec(exec_task(task_id=f"guard-{index}",
                                   execution={"interpreter": "python", "script": script}))
            self.assertEqual(result["status"], status)
            self.assertNotIn("output", result)
            self.assertEqual(result["execution"]["status"], "EXITED")
            self.assertEqual(result["execution"]["exit_code"], 7 if status == "FAIL" else 0)

    def test_review_key_is_excluded_from_child_environment_and_direct_export(self):
        event = exec_task(ai_review=False, execution={"interpreter": "python", "script":
                          "import os; print('PRIVATE_ALIAS' in os.environ)"})
        with patch.dict("os.environ", {"PRIVATE_ALIAS": self.key}):
            self.assertIn("False", self.run_exec(event)["output"]["summary"])
        agent, client = fixtures.FakeAgent(), fixtures.FakeClient()
        bridge = Bridge(self.cfg, client, agent)
        try:
            bridge.bind()
            event = exec_task(ai_review=False, iteration=2, event_id="key-export", execution={"interpreter": "python", "script": f"print({self.key!r})"})
            client.rows.append(fixtures.message(event, 1))
            bridge.catch_up()
            self.finish(bridge)
            bridge.flush()
            result = client.sent[-1][1]
            self.assertEqual(result["status"], "NEEDS_HUMAN")
            self.assertNotIn(self.key, json.dumps(result))
        finally:
            bridge.close()


class ReviewConfigTests(unittest.TestCase):
    def load(self, settings=None):
        with tempfile.TemporaryDirectory() as directory:
            value = {"hub_url": "https://example.invalid"}
            if settings is not None:
                value["exec_review"] = settings
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(value))
            return load_config(path)

    def test_defaults_and_template_placeholders(self):
        cfg = self.load()["exec_review"]
        self.assertEqual(cfg["model"], "Qwen3.8")
        self.assertEqual(cfg["timeout_seconds"], 300)
        self.assertEqual(self.load({"timeout_seconds": 60})["exec_review"]["timeout_seconds"], 60)
        self.assertEqual(cfg["base_url"], "http://techdev.hicomputing.huawei.com:18000/v1")
        self.assertIsNone(cfg["api_key"])
        root = Path(__file__).resolve().parents[1]
        for name in ("config.example.json", "config.windows.json"):
            cfg = load_config(root / name)["exec_review"]
            self.assertEqual(cfg["api_key"], "REPLACE_WITH_REVIEW_API_KEY")
            self.assertEqual(cfg["timeout_seconds"], 300)

    def test_invalid_config_is_rejected_without_disclosing_key(self):
        invalid = [[], {"extra": True}, {"base_url": "file:///tmp"}, {"base_url": "http://user:private@host/v1"},
                   {"base_url": "http://host/v1?api_key=private"}, {"model": ""}, {"api_key": "private\nvalue"},
                   {"api_key": 2}, {"timeout_seconds": True}, {"timeout_seconds": 0}]
        for settings in invalid:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError) as caught:
                    self.load(settings)
                self.assertNotIn("private", str(caught.exception))
