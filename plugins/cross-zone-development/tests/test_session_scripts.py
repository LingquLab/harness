import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import test_bridge as fixtures
from test_execution import exec_task
from cross_zone.execution import DirectExecutor
from cross_zone.protocol import parse, wire, ProtocolError
from cross_zone.scripts import prepare, ScriptFeedback


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class SessionScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = fixtures.config(self.tmp.name)
        self.cfg['session_id'] = '42105f72-c4cf-42e5-b4f6-5ffd7b2f59ae'
        Path(self.cfg['state_dir']).mkdir(parents=True, exist_ok=True)
        self.runner = DirectExecutor(self.cfg, fixtures.FakeAgent())
        self.iteration = 0

    def run_spec(self, spec):
        self.iteration += 1
        event = exec_task(iteration=self.iteration, execution=spec, ai_review=False,
                          timeout_seconds=20, execution_timeout_seconds=15)
        parse(wire(event))
        return self.runner.run(event, None, None, time.time()+20, threading.Event(), [])

    def test_create_patch_conflict_read_and_execute(self):
        code = "import argparse,json\np=argparse.ArgumentParser();p.add_argument('--args-file');a=p.parse_args()\nprint(json.load(open(a.args_file))['value'])\n"
        created = self.run_spec({'script_update': 'check.py', 'sha256': None, 'content': code})
        self.assertEqual(created['script_feedback']['sha256'], sha(code))
        result = self.run_spec({'script': 'check.py', 'sha256': sha(code), 'args': {'value': 'EXEC_OK'}})
        self.assertIn('EXEC_OK', result['output']['summary'])
        conflict = self.run_spec({'script_update': 'check.py', 'sha256': '0'*64, 'content': 'bad'})
        self.assertEqual(conflict['script_feedback']['error_code'], 'SCRIPT_HASH_MISMATCH')
        self.assertEqual(conflict['script_feedback']['content'], code)
        self.run_spec({'script_update': 'check.py', 'sha256': sha(code),
                       'replacements': [{'old': "['value']", 'new': "['renamed']"}]})
        read = self.run_spec({'script_read': 'check.py'})['script_feedback']
        self.assertEqual(read['sha256'], sha(code.replace("['value']", "['renamed']")))
        self.assertIn("['renamed']", read['content'])
        conflict = self.run_spec({'script': 'check.py', 'sha256': sha(code), 'args': {}})
        self.assertEqual(conflict['script_feedback']['content'], read['content'])

    def test_full_content_feedback_and_session_isolation(self):
        code = '#' + 'x'*100000 + '\n'
        self.run_spec({'script_update': 'long.py', 'sha256': None, 'content': code})
        reply = self.run_spec({'script': 'long.py', 'sha256': '0'*64, 'args': {}})
        self.assertEqual(reply['script_feedback']['content'], code)
        other = dict(self.cfg, state_dir=str(Path(self.tmp.name)/'other'))
        Path(other['state_dir']).mkdir()
        directory = Path(self.tmp.name)/'read-other'; directory.mkdir()
        with self.assertRaises(ScriptFeedback) as raised:
            prepare({'script_read': 'long.py'}, other, directory, time.time()+10, threading.Event())
        self.assertEqual(raised.exception.payload['error_code'], 'SCRIPT_NOT_FOUND')

    def test_protocol_rejects_paths_mixed_forms_and_bad_hashes(self):
        for spec in ({'script_read':'../secret.py'}, {'script':'a.py','sha256':'bad','args':{}},
                     {'script_read':'a.py','argv':['echo']},
                     {'git':'session','commit':'a'*40,'entry':'../a.py','args':{}},
                     {'script_update':'a.py','sha256':None,'replacements':[]}):
            with self.subTest(spec=spec), self.assertRaises(ProtocolError):
                parse(wire(exec_task(execution=spec)))

    def test_git_pins_commit_and_rejects_other_branch(self):
        repo = Path(self.tmp.name)/'git-source';repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.DEVNULL).decode().strip()
        git('init');git('config','user.name','test');git('config','user.email','test@example.test')
        git('checkout','-b',self.cfg['session_id'])
        (repo/'run.py').write_text("print('PINNED')\n")
        git('add','.');git('commit','-m','first');first=git('rev-parse','HEAD')
        (repo/'run.py').write_text("print('NEW')\n")
        git('commit','-am','second')
        with patch('cross_zone.scripts.REPOSITORY', str(repo)):
            result = self.run_spec({'git':'session','commit':first,'entry':'run.py','args':{}})
            self.assertIn('PINNED',result['output']['summary'])
            self.assertNotIn('NEW',result['output']['summary'])
            git('checkout','--orphan','unrelated');git('add','.');git('commit','-m','other')
            other=git('rev-parse','HEAD')
            result=self.run_spec({'git':'session','commit':other,'entry':'run.py','args':{}})
            self.assertEqual(result['script_feedback']['error_code'],'SCRIPT_GIT_FAILED')

    def test_expired_or_cancelled_preparation_does_not_modify_script(self):
        directory=Path(self.tmp.name)/'stopped';directory.mkdir()
        cancel=threading.Event();cancel.set()
        spec={'script_update':'stopped.py','sha256':None,'content':"print('no')"}
        for deadline, token, code in ((time.time()+10,cancel,'SCRIPT_CANCELLED'),
                                      (time.time()-1,threading.Event(),'SCRIPT_TIMED_OUT')):
            with self.assertRaises(ScriptFeedback) as raised:
                prepare(spec,self.cfg,directory,deadline,token)
            self.assertEqual(raised.exception.payload['error_code'],code)
        self.assertFalse((Path(self.cfg['state_dir'])/'scripts/stopped.py').exists())

    def test_controller_delivers_full_conflict_without_running(self):
        bridge = fixtures.Bridge(self.cfg, fixtures.FakeClient(), fixtures.FakeAgent())
        self.addCleanup(bridge.close)
        bridge.bind()
        root=Path(self.cfg['state_dir'])/'scripts';root.mkdir(exist_ok=True)
        content='#'+'x'*100000+'\n';(root/'large.py').write_text(content)
        event=exec_task(execution={'script':'large.py','sha256':'0'*64,'args':{}},ai_review=False)
        bridge.client.rows.append(fixtures.message(event,1));bridge.catch_up()
        for _ in range(100):
            bridge.work()
            if not bridge.active:break
            time.sleep(.01)
        bridge.flush()
        reply=bridge.client.sent[-1][1]
        self.assertEqual(reply['type'],'REJECTED')
        self.assertEqual(reply['content'],content)
        self.assertEqual(reply['sha256'],sha(content))
