"""Local deterministic coverage for the multi-worker scheduler."""
from collections import defaultdict
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import test_bridge as fixtures
from test_execution import compact_exec
from cross_zone import agent as agent_module
from cross_zone.agent import CodeAgentCLI
from cross_zone.config import load_config
from cross_zone.controller import Bridge


class GatedAgent:
    def __init__(self):
        self.started = defaultdict(threading.Event)
        self.release = defaultdict(threading.Event)
        self.calls = defaultdict(list)
        self.results = {}
        self.lock = threading.Lock()

    def run(self, request, session, answer, deadline, cancel, recovery):
        name = request['task_id']
        with self.lock:
            self.calls[name].append((cancel, recovery))
        self.started[name].set()
        while not self.release[name].is_set():
            if cancel.wait(0.01):
                return {'failure': 'cancelled', 'status': 'CANCELLED'}
        result = self.results.get(name, {'output': fixtures.output()})
        if isinstance(result, Exception):
            raise result
        return result


class ConcurrentBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = fixtures.config(self.tmp.name)
        self.cfg.pop('max_concurrent_tasks')
        self.cfg['exec_live_log'] = False
        self.client, self.agent = fixtures.FakeClient(), GatedAgent()
        self.bridge = Bridge(self.cfg, self.client, self.agent)
        self.bridge.bind()

    def tearDown(self):
        if self.bridge:
            self.bridge.close()
        self.tmp.cleanup()

    def send(self, event):
        self.client.rows.append(fixtures.message(event, len(self.client.rows) + 1))
        self.bridge.catch_up()

    def task(self, name, **changes):
        return fixtures.general_task(task_id=name, event_id='event-' + name, **changes)

    def state(self, name, iteration=1):
        return self.bridge.store.get_task(name, iteration)['state']

    def until(self, condition):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            self.bridge.work()
            if condition():
                return
            time.sleep(0.01)
        self.fail('workers did not reach expected state')

    def test_new_exec_and_task_finish_while_long_exec_runs(self):
        script = ("import time\nfrom pathlib import Path\nPath('long-started').touch()\n"
                  "while not Path('release-long').exists():time.sleep(0.01)\nprint('long done')\n")
        self.send(compact_exec(task_id='long', event_id='long', execution={'interpreter': 'python', 'script': script}))
        self.until(lambda: (Path(self.cfg['state_dir']) / 'long-started').exists())
        self.assertEqual(self.bridge.max_concurrent_tasks, 4)
        self.send(compact_exec(task_id='short', event_id='short'))
        self.agent.release['short-task'].set()
        self.send(self.task('short-task'))
        self.until(lambda: self.state('short') == self.state('short-task') == 'PASS')
        self.assertEqual(self.state('long'), 'RUNNING')
        self.assertEqual(len(self.bridge.active), 1)
        self.bridge.flush()
        results = [e for _, e in self.client.sent if e['type'] == 'RESULT']
        self.assertEqual({e['task_id'] for e in results}, {'short', 'short-task'})
        (Path(self.cfg['state_dir']) / 'release-long').touch()
        self.until(lambda: not self.bridge.active)
        self.assertEqual(self.state('long'), 'PASS')
        root = Path(self.cfg['state_dir']) / 'runs'
        self.assertEqual((root / 'long/1/execution/stdout.log').read_text(), 'long done\n')
        self.assertEqual((root / 'short/1/execution/stdout.log').read_text(), 'done\n')

    def test_capacity_queue_refill_and_serial_configuration(self):
        for capacity in (2, 1):
            with self.subTest(capacity=capacity):
                self.bridge.close()
                cfg = fixtures.config(Path(self.tmp.name) / str(capacity))
                cfg['max_concurrent_tasks'] = capacity
                self.client, self.agent = fixtures.FakeClient(), GatedAgent()
                self.bridge = Bridge(cfg, self.client, self.agent)
                self.bridge.bind()
                for name in ('a', 'b', 'c', 'd'):
                    self.send(self.task(name))
                self.bridge.work()
                self.assertEqual(len(self.bridge.active), capacity)
                self.assertTrue(self.agent.started['a'].wait(1))
                self.assertEqual(self.state('c'), 'QUEUED')
                self.agent.release['a'].set()
                next_name = 'c' if capacity == 2 else 'b'
                self.until(lambda: self.agent.started[next_name].is_set())
                self.assertEqual(len(self.bridge.active), capacity)
                self.assertEqual(self.state('a'), 'PASS')
                for name in ('a', 'b', 'c', 'd'):
                    self.agent.release[name].set()
                self.until(lambda: all(self.state(n) == 'PASS' for n in ('a', 'b', 'c', 'd')))

    def test_same_id_iterations_and_transport_dedup_stay_serial(self):
        first = self.task('a')
        self.send(first)
        self.until(lambda: self.agent.started['a'].is_set())
        self.send({**first, 'event_id': 'retry-a'})
        self.send(self.task('a', iteration=2) | {'event_id': 'too-early'})
        self.send(self.task('b'))
        self.until(lambda: self.agent.started['b'].is_set())
        self.assertEqual(len(self.agent.calls['a']), 1)
        self.assertIsNone(self.bridge.store.get_task('a', 2))
        self.bridge.flush()
        rejected = [e for _, e in self.client.sent if e['type'] == 'REJECTED']
        self.assertEqual(rejected[-1]['reason'], 'iteration_stale_or_previous_running')
        self.agent.release['a'].set()
        self.until(lambda: self.state('a') == 'PASS')
        self.send(self.task('a', iteration=2) | {'event_id': 'ready-next'})
        self.until(lambda: self.state('a', 2) == 'PASS')
        self.assertEqual(len(self.agent.calls['a']), 2)

    def test_cancel_one_job_does_not_cancel_other_jobs(self):
        for name in ('a', 'b'):
            self.send(self.task(name))
        self.until(lambda: all(self.agent.started[n].is_set() for n in ('a', 'b')))
        self.send({'protocol': 'cross-zone/v3', 'type': 'CANCEL', 'event_id': 'cancel-a', 'task_id': 'a', 'iteration': 1})
        self.until(lambda: self.state('a') == 'CANCELLED')
        self.assertEqual(self.state('b'), 'RUNNING')
        self.assertFalse(self.agent.calls['b'][0][0].is_set())
        self.agent.release['b'].set()
        self.until(lambda: self.state('b') == 'PASS')

    def test_one_exec_timeout_does_not_stop_another_task(self):
        self.send(compact_exec(task_id='timeout', event_id='timeout', execution_timeout_seconds=1,
                               execution={'interpreter': 'python', 'script': 'import time;time.sleep(20)'}))
        self.send(self.task('b'))
        self.until(lambda: self.state('timeout') == 'TIMED_OUT')
        self.assertEqual(self.state('b'), 'RUNNING')
        self.assertFalse(self.agent.calls['b'][0][0].is_set())

    def test_shutdown_cancels_all_active_jobs_and_persists_results(self):
        for name in ('a', 'b', 'c'):
            self.send(self.task(name))
        self.until(lambda: all(self.agent.started[n].is_set() for n in ('a', 'b', 'c')))
        self.bridge.close()
        self.bridge = None
        with sqlite3.connect(Path(self.cfg['state_dir']) / 'bridge.sqlite3') as db:
            states = dict(db.execute('SELECT task_id,state FROM tasks'))
        self.assertEqual(states, {'a': 'CANCELLED', 'b': 'CANCELLED', 'c': 'CANCELLED'})
        self.assertTrue(all(calls[0][0].is_set() for calls in self.agent.calls.values()))

    def test_recovery_result_cannot_clear_new_parallel_interruption(self):
        old = {'task_id': 'old', 'iteration': 1}
        with self.bridge.store.db:
            self.bridge.store.set_meta('recovery_tasks', [old])
            self.bridge.store.set_meta('recovery_required', True)
        self.agent.results['checker'] = {'output': fixtures.output(), 'recovery_checked': True}
        self.agent.results['failure'] = RuntimeError('adapter failed')
        for name in ('checker', 'failure'):
            self.send(self.task(name))
        self.until(lambda: all(self.agent.started[n].is_set() for n in ('checker', 'failure')))
        self.assertEqual(self.agent.calls['checker'][0][1], [old])
        self.agent.release['failure'].set()
        self.until(lambda: self.state('failure') == 'NEEDS_HUMAN')
        self.agent.release['checker'].set()
        self.until(lambda: self.state('checker') == 'PASS')
        self.assertEqual(self.bridge.store.get_meta('recovery_tasks'), [{'task_id': 'failure', 'iteration': 1}])
        self.assertTrue(self.bridge.store.get_meta('recovery_required'))

    def test_restart_marks_every_interrupted_job_without_replay(self):
        for name in ('a', 'b'):
            self.send(self.task(name))
            with self.bridge.store.db:
                self.bridge.store.update(self.bridge.store.get_task(name, 1), state='RUNNING')
        self.assertTrue(self.bridge.store.recover())
        self.assertEqual([self.state(n) for n in ('a', 'b')], ['NEEDS_HUMAN', 'NEEDS_HUMAN'])
        self.assertEqual({r['task_id'] for r in self.bridge.store.get_meta('recovery_tasks')}, {'a', 'b'})
        self.assertEqual(dict(self.agent.calls), {})


class ConfigAndCheckoutConcurrencyTests(unittest.TestCase):
    def test_default_and_configuration_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            base = {'hub_url': 'https://example.invalid'}
            path.write_text(json.dumps(base))
            self.assertEqual(load_config(path)['max_concurrent_tasks'], 4)
            for value in (1, 16):
                path.write_text(json.dumps({**base, 'max_concurrent_tasks': value}))
                self.assertEqual(load_config(path)['max_concurrent_tasks'], value)
            for value in (0, 17, True, '4'):
                path.write_text(json.dumps({**base, 'max_concurrent_tasks': value}))
                with self.assertRaises(ValueError):
                    load_config(path)

    def test_cancel_and_deadline_while_waiting_for_git(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = CodeAgentCLI(fixtures.config(directory))
            for cause in ('cancel', 'deadline'):
                results, cancel = [], threading.Event()
                deadline = time.time() + (0.05 if cause == 'deadline' else 5)
                agent_module._CHECKOUT_LOCK.acquire()
                try:
                    with patch('cross_zone.agent.prepare_checkout') as prepare:
                        worker = threading.Thread(target=lambda: results.append(runner.run(fixtures.task(), None, None, deadline, cancel, [])))
                        worker.start()
                        if cause == 'cancel':
                            cancel.set()
                        worker.join(2)
                        self.assertFalse(worker.is_alive())
                        prepare.assert_not_called()
                    self.assertEqual(results[0]['status'], 'CANCELLED' if cause == 'cancel' else 'TIMED_OUT')
                finally:
                    agent_module._CHECKOUT_LOCK.release()

    def test_candidate_preparation_is_serialized(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = CodeAgentCLI(fixtures.config(directory))
            first, second, release = threading.Event(), threading.Event(), threading.Event()
            calls = []

            def prepare(source, revision, destination):
                calls.append(str(destination))
                if len(calls) == 1:
                    first.set()
                    release.wait(3)
                else:
                    second.set()
                raise ValueError('stop after mock preparation')

            args = (None, None, time.time() + 10, threading.Event(), [])
            with patch('cross_zone.agent.prepare_checkout', side_effect=prepare):
                a = threading.Thread(target=runner.run, args=(fixtures.task(task_id='a'), *args))
                b = threading.Thread(target=runner.run, args=(fixtures.task(task_id='b'), *args))
                try:
                    a.start()
                    self.assertTrue(first.wait(1))
                    b.start()
                    self.assertFalse(second.wait(0.1))
                finally:
                    release.set()
                    a.join(3)
                    if b.ident is not None:
                        b.join(3)
            self.assertEqual(len(calls), 2)
            self.assertTrue(second.is_set())
