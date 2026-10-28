import json
from pathlib import Path
import tempfile
import time
import unittest

import test_bridge as fixtures
from cross_zone.controller import Bridge
from cross_zone.protocol import canonical, fingerprint, read_wire
from cross_zone.store import Store


class V2MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = fixtures.config(self.tmp.name)
        self.binding = {k: self.cfg[k] for k in ('hub_url', 'session_id', 'workspace_dir')}
        self.path = Path(self.cfg['state_dir']) / 'bridge.sqlite3'
        self.originals = {}

    def tearDown(self):
        self.tmp.cleanup()

    def legacy(self, states=('PASS', 'QUEUED', 'RUNNING', 'CANCELLING', 'WAITING_ANSWER'), kind="TASK"):
        store = Store(self.path, self.binding)
        with store.db:
            store.set_meta('binding', fingerprint({**self.binding, 'target': 'old-worker'}))
            store.set_meta('protocol', 'cross-zone/v2')
            store.set_meta('cursor', {'at': 1000, 'seq': 1, 'epoch': 0})
            for index, state in enumerate(states):
                task_id = 'old-' + state.lower()
                request = fixtures.general_task(task_id=task_id, event_id='old-event-' + str(index),
                                                protocol='cross-zone/v2', target='old-worker', type=kind)
                if kind == "EXEC":
                    request.update(execution={"interpreter": "python", "script": "raise RuntimeError(\"must not run\")"}, execution_timeout_seconds=10)
                self.originals[task_id] = canonical(request)
                store.db.execute('INSERT INTO tasks(task_id,iteration,request,digest,state) VALUES (?,?,?,?,?)',
                                 (task_id, 1, canonical(request), fingerprint({k: v for k, v in request.items() if k != 'event_id'}), state))
                store.db.execute('INSERT INTO inbox VALUES (?,?)', (request['event_id'], fingerprint(request)))
            event = {'protocol': 'cross-zone/v2', 'type': 'RESULT', 'event_id': 'pending-v2-result',
                     'task_id': 'old-pass', 'iteration': 1, 'target': 'old-worker', 'status': 'PASS'}
            store.db.execute('INSERT INTO outbox(id,text,created) VALUES (?,?,?)',
                             (event['event_id'], 'CROSS_ZONE_V2\n' + canonical(event), time.time()))
        store.close()
        receipt = self.path.parent / 'runs/old-pass/1/execution/execution.json'
        receipt.parent.mkdir(parents=True)
        receipt.write_text('{"status":"EXITED","exit_code":0}', encoding='utf-8')
        return receipt

    def test_upgrade_keeps_facts_and_blocks_legacy_execution(self):
        receipt = self.legacy()
        before = receipt.read_bytes()
        client, agent = fixtures.FakeClient(), fixtures.FakeAgent()
        bridge = Bridge(self.cfg, client, agent)
        try:
            self.assertEqual(bridge.store.get_meta('binding'), fingerprint(self.binding))
            self.assertEqual(bridge.store.get_meta('protocol'), 'cross-zone/v3')
            self.assertEqual(bridge.store.get_task('old-pass', 1)['state'], 'PASS')
            self.assertEqual(bridge.store.get_task('old-queued', 1)['state'], 'BLOCKED')
            for state in ('running', 'cancelling', 'waiting_answer'):
                self.assertEqual(bridge.store.get_task('old-' + state, 1)['state'], 'NEEDS_HUMAN')
            self.assertEqual(len(bridge.store.get_meta('recovery_tasks')), 3)
            for task_id, request in self.originals.items():
                self.assertEqual(bridge.store.get_task(task_id, 1)['request'], request)
            self.assertEqual(bridge.store.db.execute('SELECT count(*) FROM inbox').fetchone()[0], 5)
            bridge.work()
            self.assertEqual(agent.calls, [])
            bridge.flush()
            pending = next(event for event_id, event in client.sent if event_id == 'pending-v2-result')
            self.assertEqual(pending['protocol'], 'cross-zone/v3')
            self.assertNotIn('target', pending)
            self.assertEqual(receipt.read_bytes(), before)
            self.assertTrue(all('target' not in event for _, event in client.sent))
        finally:
            bridge.close()
        reopened = Bridge(self.cfg, client, agent)
        try:
            reopened.work()
            self.assertEqual(agent.calls, [])
        finally:
            reopened.close()

    def test_terminal_v2_task_does_not_export_an_old_pending_question(self):
        self.legacy(states=('PASS',))
        import sqlite3
        connection = sqlite3.connect(self.path)
        event = {'protocol': 'cross-zone/v2', 'type': 'QUESTION', 'event_id': 'expired-question',
                 'task_id': 'old-pass', 'iteration': 1, 'target': 'old-worker', 'question': 'Old question'}
        with connection:
            connection.execute('INSERT INTO outbox(id,text,created) VALUES (?,?,?)',
                               ('expired-question', 'CROSS_ZONE_V2\n' + canonical(event), time.time()))
        connection.close()
        store = Store(self.path, self.binding)
        try:
            self.assertFalse(any(read_wire(row['text']).get('type') == 'QUESTION'
                                 for row in store.db.execute('SELECT text FROM outbox WHERE sent=0')))
            self.assertEqual(store.get_task('old-pass', 1)['state'], 'PASS')
        finally:
            store.close()

    def test_old_exec_is_never_dispatched(self):
        self.legacy(states=('QUEUED', 'RUNNING'), kind='EXEC')
        from unittest.mock import patch
        bridge = Bridge(self.cfg, fixtures.FakeClient(), fixtures.FakeAgent())
        try:
            with patch.object(bridge.direct_executor, 'run') as run:
                bridge.work()
                run.assert_not_called()
            self.assertEqual(bridge.store.get_task('old-queued', 1)['state'], 'BLOCKED')
            self.assertEqual(bridge.store.get_task('old-running', 1)['state'], 'NEEDS_HUMAN')
        finally:
            bridge.close()

    def test_old_config_identity_is_used_only_for_database_migration(self):
        from cross_zone.config import load_config
        path = Path(self.tmp.name) / 'config.json'
        path.write_text(json.dumps({'hub_url': self.cfg['hub_url'], 'target': 'old-worker'}), encoding='utf-8')
        config = load_config(path)
        self.assertNotIn('target', config)
        self.assertEqual(config['_legacy_target'], 'old-worker')
        self.legacy(states=())
        migrated = Store(self.path, self.binding, legacy_target=config['_legacy_target'])
        migrated.close()

    def test_queued_answer_continuation_requires_recovery(self):
        self.legacy(states=('QUEUED',))
        import sqlite3
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute("UPDATE tasks SET session_id=?, answer=?, questions=1 WHERE task_id=?",
                               ('prior-agent-session', 'approved fixture', 'old-queued'))
        connection.close()
        bridge = Bridge(self.cfg, fixtures.FakeClient(), fixtures.FakeAgent())
        try:
            self.assertEqual(bridge.store.get_task('old-queued', 1)['state'], 'NEEDS_HUMAN')
            self.assertTrue(bridge.store.get_meta('recovery_required'))
            self.assertIn({'task_id': 'old-queued', 'iteration': 1}, bridge.store.get_meta('recovery_tasks'))
            bridge.work()
            self.assertEqual(bridge.agent.calls, [])
        finally:
            bridge.close()

    def test_stale_pending_question_is_not_delivered_after_upgrade(self):
        self.legacy(states=('WAITING_ANSWER',))
        import sqlite3
        connection = sqlite3.connect(self.path)
        event = {'protocol': 'cross-zone/v2', 'type': 'QUESTION', 'event_id': 'old-question',
                 'task_id': 'old-waiting_answer', 'iteration': 1, 'target': 'old-worker',
                 'question_id': 'q-old', 'question': 'Continue?'}
        with connection:
            connection.execute('INSERT INTO outbox(id,text,created) VALUES (?,?,?)',
                               ('old-question', 'CROSS_ZONE_V2\n' + canonical(event), time.time()))
        connection.close()
        store = Store(self.path, self.binding)
        try:
            self.assertFalse(any(read_wire(row['text']).get('type') == 'QUESTION'
                                 for row in store.db.execute('SELECT text FROM outbox WHERE sent=0')))
            self.assertTrue(store.get_meta('recovery_required'))
        finally:
            store.close()

    def test_legacy_completed_identity_cannot_be_replayed_as_v3(self):
        self.legacy(states=('PASS',))
        client, agent = fixtures.FakeClient(), fixtures.FakeAgent()
        bridge = Bridge(self.cfg, client, agent)
        try:
            request = fixtures.general_task(task_id='old-pass', event_id='new-v3-event')
            with bridge.store.db:
                bridge._accept(request)
            bridge.work()
            self.assertEqual(agent.calls, [])
            bridge.flush()
            self.assertTrue(any(event.get('reason') == 'task_content_conflict' for _, event in client.sent))
        finally:
            bridge.close()

    def test_changed_session_cannot_migrate_binding(self):
        self.legacy(states=('PASS',))
        with self.assertRaisesRegex(ValueError, 'different session'):
            Store(self.path, {**self.binding, 'session_id': 'other-session'}, legacy_target='old-worker')
        store = Store(self.path, self.binding)
        self.assertEqual(store.get_task('old-pass', 1)['state'], 'PASS')
        store.close()

    def test_empty_v2_database_can_use_original_config_identity(self):
        self.legacy(states=())
        with self.assertRaisesRegex(ValueError, 'different session'):
            Store(self.path, self.binding)
        store = Store(self.path, self.binding, legacy_target='old-worker')
        self.assertEqual(store.get_meta('protocol'), 'cross-zone/v3')
        store.close()

    def test_existing_v3_queued_work_and_outbox_are_unchanged(self):
        bridge = Bridge(self.cfg, fixtures.FakeClient(), fixtures.FakeAgent())
        with bridge.store.db:
            bridge._accept(fixtures.general_task())
        pending = [tuple(row) for row in bridge.store.db.execute('SELECT * FROM outbox')]
        bridge.close()
        reopened = Bridge(self.cfg, fixtures.FakeClient(), fixtures.FakeAgent())
        try:
            self.assertEqual(reopened.store.get_task('task-1', 1)['state'], 'QUEUED')
            self.assertEqual(pending, [tuple(row) for row in reopened.store.db.execute('SELECT * FROM outbox')])
        finally:
            reopened.close()
