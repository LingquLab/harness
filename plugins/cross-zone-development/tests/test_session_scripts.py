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
