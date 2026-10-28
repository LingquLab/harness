import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import test_bridge as fixtures
from cross_zone.agent import CodeAgentCLI
from cross_zone.controller import Bridge
from cross_zone.egress import review
from cross_zone.execution import DirectExecutor
from cross_zone.protocol import ProtocolError, parse, read_wire, wire


def exec_task(**changes):
    event = fixtures.general_task(type="EXEC", execution={"argv": [sys.executable, "-c", "print('done')"]},
                                  execution_timeout_seconds=10, ai_review=True)
    event.update(changes)
    return event


class ExecutionProtocolTests(unittest.TestCase):
    def test_accepts_both_forms_and_legacy_task(self):
        for event in (exec_task(), exec_task(execution={"interpreter": "bash", "script": "printf done\\n"}),
                      fixtures.task()):
            self.assertEqual(parse(wire(event, readable=True)), event)

    def test_ai_review_is_optional_exec_only_boolean(self):
        for flag in (True, False):
            event = exec_task(ai_review=flag)
            self.assertEqual(parse(wire(event)), event)
        for flag in (None, 0, 1, "false"):
            with self.assertRaises(ProtocolError):
                parse(wire(exec_task(ai_review=flag)))
        with self.assertRaises(ProtocolError):
            parse(wire(fixtures.general_task(ai_review=False)))

    def test_exec_inherits_session_target(self):
        event = exec_task()
        compact = {k: v for k, v in event.items() if k != "target"}
        self.assertEqual(parse(wire(compact, readable=True)), event)

    def test_rejects_ambiguous_or_unbounded_execution(self):
        invalid = [{}, {"argv": []}, {"argv": [""]}, {"argv": ["echo", "a\0b"]},
                   {"argv": ["echo"] * 129}, {"argv": "echo done"},
                   {"interpreter": "sh", "script": "echo done"},
                   {"interpreter": "bash", "script": "x" * 12001},
                   {"interpreter": "bash", "script": "a\0b"},
                   {"interpreter": "bash", "script": "echo done", "argv": ["echo"]},
                   {"argv": ["echo"], "cwd": "/tmp"}]
        for execution in invalid:
            with self.subTest(execution=str(execution)[:60]), self.assertRaises(ProtocolError):
                parse(wire(exec_task(execution=execution)))
        for changes in ({"revision": "a" * 40}, {"execution_timeout_seconds": 0},
                        {"execution_timeout_seconds": True}, {"execution_timeout_seconds": 541}):
            with self.subTest(changes=changes), self.assertRaises(ProtocolError):
                parse(wire(exec_task(**changes)))


class DirectExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = fixtures.config(self.tmp.name)
        self.reviewer = fixtures.FakeAgent()
        self.runner = DirectExecutor(self.cfg, self.reviewer)

    def tearDown(self):
        self.tmp.cleanup()

    def run_command(self, event=None, cancel=None, recovery=None):
        return self.runner.run(event or exec_task(), None, None, time.time() + 90,
                               cancel or threading.Event(), recovery or [])

    def receipt(self):
        return Path(self.cfg["state_dir"]) / "runs/task-1/1/execution/execution.json"

    def test_direct_python_stdout_is_utf8_under_legacy_parent_encoding(self):
        text = "检查成功，服务器可访问"
        event = exec_task(ai_review=False, execution={"interpreter": "python", "script": f"print({text!r})"})
        with patch.dict(os.environ, {"PYTHONIOENCODING": "gbk", "PYTHONUTF8": "0"}):
            result = self.run_command(event)
        self.assertIn(text, result["output"]["summary"])
        self.assertEqual((self.receipt().parent / "stdout.log").read_bytes(), (text + os.linesep).encode("utf-8"))

    def test_omitted_ai_review_skips_ai_and_uses_machine_egress(self):
        event = exec_task()
        event.pop("ai_review")
        self.assertEqual(parse(wire(event)), event)
        result = self.run_command(event)
        self.assertEqual(self.reviewer.calls, [])
        self.assertFalse(result["output"]["egress_reviewed"])
        self.assertEqual(review(result["output"], event, execution=result["execution"])["status"], "PASS")

    def test_direct_output_skips_ai_and_passes_machine_egress(self):
        event = exec_task(ai_review=False)
        result = self.run_command(event)
        self.assertEqual(self.reviewer.calls, [])
        self.assertFalse(result["output"]["egress_reviewed"])
        fields = review(result["output"], event, execution=result["execution"])
        self.assertIn("done", fields["summary"])
        self.assertEqual(fields["status"], "PASS")

    def test_direct_output_rejects_known_secrets_at_egress(self):
        event = exec_task(ai_review=False,
                          execution={"argv": [sys.executable, "-c", "print('private-value')"]})
        result = self.run_command(event)
        with self.assertRaisesRegex(ValueError, "egress_content_rejected"):
            review(result["output"], event, secrets=("private-value",), execution=result["execution"])
        self.assertEqual(self.reviewer.calls, [])

    def test_direct_output_withholds_failures_and_unexpected_output(self):
        scripts = ["print('x'*2001)", "import sys;sys.stderr.write('private')",
                   "import sys;sys.stdout.buffer.write(bytes([255]))", "print(chr(1))", "print(chr(11))", "print(chr(127))",
                   "import sys;print('private');sys.exit(1)"]
        for index, script in enumerate(scripts):
            event = exec_task(ai_review=False, task_id='direct-' + str(index),
                              execution={"argv": [sys.executable, "-c", script]})
            result = self.run_command(event)
            self.assertIn("failure", result)
            self.assertNotIn("private", json.dumps(result))
            self.assertNotIn("output", result)
        self.assertEqual(self.reviewer.calls, [])

    def test_literal_argv_cwd_environment_and_receipt_precede_review(self):
        literal = '空 格;$(echo wrong) `echo wrong` "quoted"'
        script = "import os,sys;print(sys.argv[1]);print(os.getcwd());print('HAPI_ACCESS_KEY' in os.environ)"
        with patch.dict(os.environ, {"HAPI_ACCESS_KEY": "private-value"}):
            result = self.run_command(exec_task(execution={"argv": [sys.executable, "-c", script, literal]}))
        self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
        context = self.reviewer.calls[0][6]
        lines = Path(context["stdout"]).read_text().splitlines()
        self.assertEqual(lines, [literal, str(Path(self.cfg["state_dir"]).resolve()), "False"])
        saved = json.loads(self.receipt().read_text())
        self.assertEqual(saved["status"], "EXITED")
        self.assertIsInstance(saved["pid"], int)
        self.assertNotIn("private-value", json.dumps(result))
        self.assertIsNone(self.reviewer.calls[0][1])  # Never resume/re-execute an EXEC through an AI session.

    def test_script_is_saved_unchanged_and_executed_once(self):
        script = "from pathlib import Path\np=Path('count');p.write_text('once')\nprint('done')\n"
        event = exec_task(execution={"interpreter": "python", "script": script})
        self.assertEqual(self.run_command(event)["execution"]["exit_code"], 0)
        self.assertEqual((self.receipt().parent / "script.py").read_bytes(), script.encode())
        result = self.run_command(event)
        self.assertEqual(result["failure"], "execution_already_attempted")
        self.assertTrue(result["pause"])
        self.assertEqual(len(self.reviewer.calls), 1)

    def test_bash_script(self):
        result = self.run_command(exec_task(execution={"interpreter": "bash", "script": "printf 'bash done\\n'\n"}))
        self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
        self.assertEqual((self.receipt().parent / "stdout.log").read_text(), "bash done\n")

    def test_windows_powershell_command_and_utf8_script(self):
        from types import SimpleNamespace
        process = Mock(pid=12345, returncode=0)
        process.poll.return_value = 0
        with patch("cross_zone.execution.os", SimpleNamespace(name="nt", environ=os.environ)), \
                patch("cross_zone.execution.subprocess.CREATE_NEW_PROCESS_GROUP", 512, create=True), \
                patch("cross_zone.execution.subprocess.Popen", return_value=process) as launch:
            result = self.run_command(exec_task(execution={"interpreter": "powershell", "script": "Write-Output '你好'"}))
        script = self.receipt().parent / "script.ps1"
        self.assertEqual(launch.call_args.args[0], ["powershell", "-NoProfile", "-NonInteractive", "-File", str(script)])
        self.assertFalse(launch.call_args.kwargs["shell"])
        self.assertEqual(script.read_bytes(), "Write-Output '你好'".encode("utf-8-sig"))
        self.assertEqual(result["execution"]["exit_code"], 0)

    def test_windows_batch_file_requires_explicit_interpreter(self):
        from types import SimpleNamespace
        with patch("cross_zone.execution.os", SimpleNamespace(name="nt", environ=os.environ)), \
                patch("cross_zone.execution.shutil.which", return_value="launcher.CMD"), \
                patch("cross_zone.execution.subprocess.Popen") as launch:
            result = self.run_command(exec_task(execution={"argv": ["launcher", "a&b"]}))
        launch.assert_not_called()
        self.assertEqual(result["execution"]["status"], "START_FAILED")

    def test_timeout_and_output_limit_keep_facts_for_review(self):
        for iteration, code, limit, expected in ((1, "import time;print('started',flush=True);time.sleep(20)", 10000, "TIMED_OUT"),
                                                 (2, "print('x'*1000)", 64, "OUTPUT_LIMIT")):
            event = exec_task(iteration=iteration, execution={"argv": [sys.executable, "-c", code]},
                              execution_timeout_seconds=1)
            with patch("cross_zone.execution.OUTPUT_LIMIT", limit):
                result = self.run_command(event)
            self.assertEqual(result["execution"]["status"], expected)
            self.assertIsInstance(result["execution"]["exit_code"], int)
        self.assertEqual(len(self.reviewer.calls), 2)

    def test_cancel_stops_command_and_does_not_launch_reviewer(self):
        cancel = threading.Event()
        timer = threading.Timer(0.2, cancel.set)
        timer.start()
        try:
            result = self.run_command(exec_task(execution={"argv": [sys.executable, "-c", "import time;time.sleep(20)"]}), cancel)
        finally:
            timer.cancel()
            timer.join()
        self.assertEqual(result["execution"]["status"], "CANCELLED")
        self.assertEqual(result["status"], "CANCELLED")
        self.assertFalse(self.reviewer.calls)

    def test_pending_recovery_and_prelaunch_cancel_do_not_execute(self):
        result = self.run_command(recovery=[{"task_id": "old", "iteration": 1}])
        self.assertEqual(result["failure"], "execution_recovery_pending")
        self.assertFalse(self.receipt().exists())
        cancel = threading.Event()
        cancel.set()
        result = self.run_command(cancel=cancel)
        self.assertEqual(result["execution"]["status"], "NOT_STARTED")
        self.assertFalse(self.receipt().exists())

    def test_start_and_review_failures_preserve_execution_facts(self):
        result = self.run_command(exec_task(execution={"argv": ["/missing/exec-test-command"]}))
        self.assertEqual(result["execution"], {"status": "START_FAILED", "exit_code": None})
        def broken(*args):
            raise RuntimeError("sensitive raw log contents")
        self.reviewer.run = broken
        result = self.run_command(exec_task(iteration=2))
        self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
        self.assertEqual(result["failure"], "execution_review_failed")
        self.assertNotIn("sensitive", json.dumps(result))

    def test_receipt_write_failure_keeps_exit_facts_and_prevents_replay(self):
        original = Path.replace
        calls = []
        def fail_final_save(path, target):
            calls.append(path)
            if len(calls) == 2:
                raise OSError("disk full")
            return original(path, target)
        with patch.object(Path, "replace", fail_final_save):
            result = self.run_command()
        self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
        self.assertEqual(result["failure"], "execution_receipt_write_failed")
        self.assertTrue(result["pause"])
        self.assertFalse(self.reviewer.calls)
        self.assertEqual(self.run_command()["failure"], "execution_already_attempted")

    def test_termination_failure_marks_unknown_and_skips_review(self):
        process = Mock(pid=12345, returncode=None)
        process.poll.return_value = None
        with patch("cross_zone.execution.subprocess.Popen", return_value=process), \
                patch("cross_zone.execution.terminate_tree", side_effect=RuntimeError("termination_unconfirmed")):
            result = self.run_command(exec_task(execution_timeout_seconds=1))
        self.assertEqual(result["execution"], {"status": "TERMINATION_UNCONFIRMED", "exit_code": None})
        self.assertTrue(result["pause"])
        self.assertFalse(self.reviewer.calls)



class ExecutionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = fixtures.config(self.tmp.name)
        self.client = fixtures.FakeClient()
        self.reviewer = fixtures.FakeAgent()
        self.bridge = Bridge(self.cfg, self.client, self.reviewer)
        self.bridge.bind()

    def tearDown(self):
        self.bridge.close()
        self.tmp.cleanup()

    def ingest(self, event):
        self.client.rows.append(fixtures.message(event, len(self.client.rows) + 1))
        self.bridge.catch_up()

    def finish(self):
        deadline = time.time() + 5
        while time.time() < deadline:
            self.bridge.work()
            if self.bridge.current is None:
                self.bridge.flush()
                return self.client.sent[-1][1]
            time.sleep(0.01)
        self.fail("executor did not settle")

    def test_omitted_ai_review_returns_direct_result_and_keeps_secret_checks(self):
        for iteration, text in enumerate(("42", self.client.access_key), 1):
            event = exec_task(iteration=iteration, event_id=f"default-{iteration}",
                              execution={"argv": [sys.executable, "-c", f"print({text!r})"]})
            event.pop("ai_review")
            self.ingest(event)
            result = self.finish()
            self.assertEqual(result["status"], "PASS" if iteration == 1 else "NEEDS_HUMAN")
            self.assertNotIn("target", result)
            self.assertNotIn("egress_reviewed", result)
            if iteration == 1:
                self.assertIn("no AI review", result["summary"])
            else:
                self.assertNotIn(text, json.dumps(result))
        self.assertEqual(self.reviewer.calls, [])

    def test_direct_results_reach_hapi_and_secrets_are_withheld(self):
        for iteration, text in enumerate(("42", self.client.access_key, "password=private"), 1):
            self.ingest(exec_task(ai_review=False, iteration=iteration, event_id=f"direct-{iteration}",
                                 execution={"argv": [sys.executable, "-c", f"print({text!r})"]}))
            result = self.finish()
            self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
            self.assertEqual(result["status"], "PASS" if iteration == 1 else "NEEDS_HUMAN")
            if iteration == 1:
                self.assertIn("42", result["summary"])
            else:
                self.assertNotIn(text, json.dumps(result))
        self.assertEqual(self.reviewer.calls, [])

    def test_failed_command_cannot_become_pass_and_duplicates_do_not_replay(self):
        event = exec_task(execution={"argv": [sys.executable, "-c", "print('private raw output');raise SystemExit(7)"]})
        self.ingest(event)
        result = self.finish()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 7})
        self.assertNotIn("private raw output", json.dumps(result))
        self.ingest(dict(event, event_id="retry"))
        self.bridge.work()
        self.assertEqual(len(self.reviewer.calls), 1)

    def test_success_and_unsafe_or_question_reviews(self):
        outputs = [fixtures.output(), fixtures.output(summary="password=not-for-export"),
                   fixtures.output(kind="QUESTION", status="BLOCKED", question="Rerun?")]
        self.reviewer.outputs = [{"output": value} for value in outputs]
        for iteration in range(1, 4):
            self.ingest(exec_task(iteration=iteration, event_id=f"exec-{iteration}"))
            result = self.finish()
            self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
            self.assertEqual(result["status"], "PASS" if iteration == 1 else "NEEDS_HUMAN")
            self.assertNotIn("not-for-export", json.dumps(result))
        self.ingest({"protocol": "cross-zone/v3", "type": "ANSWER", "event_id": "answer", "iteration": 3,
                     "task_id": "task-1", "question_id": "q", "answer": "yes"})
        self.bridge.flush()
        self.assertEqual(self.client.sent[-1][1]["reason"], "question_not_pending")
        self.assertEqual(len(self.reviewer.calls), 3)

    def test_timeout_overrides_ai_pass(self):
        self.ingest(exec_task(execution={"argv": [sys.executable, "-c", "import time;time.sleep(20)"]},
                              execution_timeout_seconds=1))
        result = self.finish()
        self.assertEqual(result["status"], "TIMED_OUT")
        self.assertEqual(result["execution"]["status"], "TIMED_OUT")

    def test_failed_review_keeps_exit_code(self):
        self.reviewer.outputs = [{"failure": "timed_out", "status": "TIMED_OUT", "detail": "Output review deadline."}]
        self.ingest(exec_task())
        result = self.finish()
        self.assertEqual(result["execution"], {"status": "EXITED", "exit_code": 0})
        self.assertEqual(result["status"], "TIMED_OUT")

    def test_recovery_does_not_replay_and_queued_cancel_has_no_execution(self):
        self.ingest(exec_task())
        task = self.bridge.store.get_task("task-1", 1)
        with self.bridge.store.db:
            self.bridge.store.update(task, state="RUNNING")
        self.bridge.store.recover()
        self.bridge.work()
        self.assertFalse(self.reviewer.calls)
        self.ingest(exec_task(iteration=2, event_id="next"))
        self.ingest({"protocol": "cross-zone/v3", "type": "CANCEL", "event_id": "cancel",
                     "task_id": "task-1", "iteration": 2})
        self.bridge.flush()
        self.assertEqual(self.client.sent[-1][1]["execution"]["status"], "NOT_STARTED")

    def test_execution_metadata_counts_toward_egress_budget(self):
        event = exec_task()
        value = fixtures.output(summary="中" * 1000)
        # Find a valid near-limit summary, then prove the execution envelope is included.
        while True:
            try:
                review(value, event)
                break
            except ValueError:
                value["summary"] = value["summary"][:-1]
        while True:
            larger = dict(value, summary=value["summary"] + "a")
            try:
                review(larger, event)
                value = larger
            except ValueError:
                break
        with self.assertRaisesRegex(ValueError, "egress_size_limit"):
            review(value, event, execution={"status": "EXITED", "exit_code": 0})


class ExecutionReviewerTests(unittest.TestCase):
    def test_real_cli_prompt_only_reviews_saved_files(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = fixtures.config(directory)
            script = Path(directory) / "reviewer.py"
            script.write_text("import sys,json\np=sys.stdin.read()\n"
                              "assert 'EXEC OUTPUT REVIEW ONLY' in p\n"
                              "assert 'Do not execute or repeat' in p\n"
                              "assert 'never QUESTION' in p\n"
                              + "print(" + repr(json.dumps({"structured_output": fixtures.output()})) + ")\n")
            cfg["agent_command"] = [sys.executable, str(script)]
            result = DirectExecutor(cfg, CodeAgentCLI(cfg)).run(exec_task(), None, None,
                                                               time.time() + 90, threading.Event(), [])
            self.assertEqual(result["execution"]["exit_code"], 0)
            self.assertEqual(result["output"]["status"], "PASS")
