from __future__ import annotations

import importlib.util
import io
import pathlib
import subprocess
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "plugins/cross-zone-development/skills/cross-zone-development/scripts/github_issue.py"
)
SPEC = importlib.util.spec_from_file_location("cross_zone_github_issue", SCRIPT)
assert SPEC and SPEC.loader
github_issue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(github_issue)


class GitHubIssueTest(unittest.TestCase):
    def test_target_validation_rejects_path_and_issue_injection(self) -> None:
        invalid_targets = [
            ("owner/repo/extra", "1"),
            ("owner/../repo", "1"),
            ("owner/repo?x=y", "1"),
            ("owner/repo", "0"),
            ("owner/repo", "1/comments"),
        ]
        for repository, issue in invalid_targets:
            with self.subTest(repository=repository, issue=issue):
                with self.assertRaises(github_issue.GitHubAccessError):
                    github_issue.validate_target(repository, issue)

    def test_comment_validation_enforces_egress_size_and_controls(self) -> None:
        github_issue.validate_comment("GREEN_RESULT\nStatus: PASS")
        with self.assertRaises(github_issue.GitHubAccessError):
            github_issue.validate_comment("x" * 4_001)
        with self.assertRaises(github_issue.GitHubAccessError):
            github_issue.validate_comment("GREEN_RESULT\x1b[31m")

    def test_missing_credential_helper_has_a_safe_error(self) -> None:
        with mock.patch.object(
            github_issue.subprocess, "run", side_effect=FileNotFoundError
        ):
            with self.assertRaisesRegex(
                github_issue.GitHubAccessError, "credential manager could not start"
            ):
                github_issue.load_token("owner/repo")

    def test_curl_keeps_token_out_of_arguments_and_disables_revocation(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b'{"ok": true}', stderr=b""
        )
        with mock.patch.object(github_issue.shutil, "which", return_value="/curl"), mock.patch.object(
            github_issue.subprocess, "run", return_value=completed
        ) as run:
            result = github_issue.request_json("github_pat_secret", "repos/o/r/issues/1")

        self.assertEqual(result, {"ok": True})
        arguments = run.call_args.args[0]
        self.assertIn("--ssl-no-revoke", arguments)
        self.assertIn("--insecure", arguments)
        self.assertTrue(all("github_pat_secret" not in argument for argument in arguments))
        self.assertIn(b"github_pat_secret", run.call_args.kwargs["input"])

    def test_api_failure_is_not_reported_as_success(self) -> None:
        completed = subprocess.CompletedProcess(
            args=[], returncode=22, stdout=b'{"message":"denied"}', stderr=b"HTTP 403"
        )
        with mock.patch.object(github_issue.shutil, "which", return_value="/curl"), mock.patch.object(
            github_issue.subprocess, "run", return_value=completed
        ):
            with self.assertRaisesRegex(github_issue.GitHubAccessError, "curl exit 22"):
                github_issue.request_json("token", "repos/o/r/issues/1")

    def test_oversized_comment_stops_before_credential_access(self) -> None:
        with mock.patch.object(github_issue.sys, "stdin", io.StringIO("x" * 4_001)), mock.patch.object(
            github_issue, "load_token"
        ) as load_token, mock.patch.object(github_issue.sys, "stderr", io.StringIO()):
            result = github_issue.main(["comment", "owner/repo", "1"])

        self.assertEqual(result, 2)
        load_token.assert_not_called()

    def test_comment_pagination_is_bounded(self) -> None:
        first_page = [
            {"id": index, "user": {"login": "bot"}, "created_at": "now", "body": "x"}
            for index in range(100)
        ]
        with mock.patch.object(
            github_issue, "request_json", side_effect=[first_page, []]
        ) as request:
            result = github_issue.get_comments("token", "owner/repo", 1)

        self.assertEqual(len(result), 100)
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
