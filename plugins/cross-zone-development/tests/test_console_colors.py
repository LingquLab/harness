import errno
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipIf(os.name == 'nt', 'POSIX pseudo-terminal fixture; launcher targets Git Bash')
class LauncherColorTests(unittest.TestCase):
    def test_terminal_plain_file_and_color_opt_out(self):
        import pty
        import select
        for terminal, overrides, colored in [(True, {}, True), (True, {'NO_COLOR': '1'}, False),
                                             (True, {'TERM': 'dumb'}, False), (False, {}, False)]:
            with self.subTest(terminal=terminal, overrides=overrides), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / 'config.json'
                config.write_text('{}', encoding='utf-8')
                lines = ['2026-10-22 10:35:31,922 INFO Task state: 中文 = PASS',
                         '2026-10-22 10:35:31,923 INFO Agent tool Bash: 中文',
                         'tool continuation line',
                         '2026-10-22 10:35:31,924 INFO Agent assistant: 检查完成',
                         'assistant continuation line',
                         '2026-10-22 10:35:31,925 INFO Agent stderr: diagnostic',
                         '2026-10-22 10:35:31,926 INFO Agent session initialized',
                         'program continuation line']
                executable = root / 'py'
                executable.write_text("#!/bin/sh\nprintf '%s\\n' " +
                                      ' '.join("'" + line + "'" for line in lines) + '\n', encoding='utf-8')
                executable.chmod(0o755)
                env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                       'TERM': 'xterm-256color', 'BRIDGE_LOG_DIR': str(root / 'logs')}
                env.pop('NO_COLOR', None)
                env.update(overrides)
                command = ['bash', str(Path(__file__).parents[1] / 'start-bridge.sh'),
                           'doctor', 'color-test', str(config)]
                if terminal:
                    master, slave = pty.openpty()
                    try:
                        result = subprocess.run(command, env=env, stdout=slave, stderr=slave, timeout=10)
                        os.close(slave)
                        slave = None
                        data = bytearray()
                        while select.select([master], [], [], 5)[0]:
                            try:
                                chunk = os.read(master, 4096)
                            except OSError as exc:
                                if exc.errno == errno.EIO:
                                    break
                                raise
                            if not chunk:
                                break
                            data.extend(chunk)
                        screen = data.decode('utf-8')
                    finally:
                        os.close(master)
                        if slave is not None:
                            os.close(slave)
                else:
                    result = subprocess.run(command, env=env, capture_output=True, timeout=10)
                    screen = result.stdout.decode('utf-8')
                self.assertEqual(result.returncode, 0)
                self.assertEqual(screen.count('\x1b[36m'), 2 if colored else 0)
                if colored:
                    self.assertIn('\x1b[36m2026-10-22 10:35:31,922 INFO \x1b[0mTask state: 中文', screen)
                    self.assertIn('\x1b[90m' + lines[1] + '\x1b[0m', screen)
                    self.assertIn('\x1b[90mtool continuation line\x1b[0m', screen)
                    self.assertIn('\x1b[32m' + lines[3] + '\x1b[0m', screen)
                    self.assertIn('\x1b[32massistant continuation line\x1b[0m', screen)
                    self.assertIn('\x1b[33m' + lines[5] + '\x1b[0m', screen)
                    self.assertNotIn('\x1b[33mprogram continuation line', screen)
                else:
                    self.assertNotIn('\x1b', screen)
                self.assertIn(lines[1], screen)
                log = (root / 'logs/bridge-doctor-color-test.log').read_text(encoding='utf-8')
                self.assertNotIn('\x1b', log)
                for line in lines:
                    self.assertIn(line, log)
