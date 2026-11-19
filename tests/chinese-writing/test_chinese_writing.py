import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNER = REPO_ROOT / "plugins/chinese-writing/skills/chinese-writing/scripts/scan.py"


class ChineseWritingScannerTests(unittest.TestCase):
    def test_reports_required_terms_and_positions_from_stdin(self):
        draft = (
            "方案涉及结构性决策、裁决和契约。\n"
            "协调资源、赋能、统一管理、赋能。\n"
            "运行 Host 合同检查。\n"
        )
        result = subprocess.run(
            [sys.executable, str(SCANNER)],
            input=draft,
            capture_output=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        findings = [line.split("：", 1)[0] for line in result.stdout.splitlines()]
        self.assertEqual(
            findings,
            [
                "stdin:1:5: 结构性决策",
                "stdin:1:11: 裁决",
                "stdin:1:14: 契约",
                "stdin:2:1: 协调资源",
                "stdin:2:6: 赋能",
                "stdin:2:9: 统一管理",
                "stdin:2:14: 赋能",
                "stdin:3:9: 合同",
            ],
        )
        self.assertIn("接口约定", result.stdout)

    def test_accepts_concrete_actions_and_english_terms_from_file(self):
        draft = (
            "校验 token 和 rank，再创建 communicator。"
            "调用方通过 opaque handle 引用对象。"
            "等待 stream 完成后调用 cleanup，释放 buffer。\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "draft.md").write_text(draft, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCANNER), "draft.md"],
                cwd=directory,
                capture_output=True,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"")

    def test_reports_invalid_utf8_as_scan_error(self):
        result = subprocess.run(
            [sys.executable, str(SCANNER), "-"],
            input=b"\xff",
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("扫描失败".encode("utf-8"), result.stderr)


if __name__ == "__main__":
    unittest.main()
