#!/usr/bin/env python3
"""Bounded GitHub issue access using an existing HTTPS git credential."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from typing import Any


API_ROOT = "https://api.github.com"
MAX_COMMENT_CHARS = 4_000
MAX_COMMENTS = 200
MAX_RESPONSE_BYTES = 2_000_000
REPOSITORY_PATTERN = re.compile(
    r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?/[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?\Z"
)


class GitHubAccessError(RuntimeError):
    """A safe, user-facing GitHub access failure."""


def validate_target(repository: str, issue_text: str) -> tuple[str, int]:
    if not REPOSITORY_PATTERN.fullmatch(repository) or any(
        part in {".", ".."} for part in repository.split("/")
    ):
        raise GitHubAccessError("repository must use the OWNER/REPO form")
    if not issue_text.isascii() or not issue_text.isdigit() or int(issue_text) <= 0:
        raise GitHubAccessError("issue number must be a positive integer")
    return repository, int(issue_text)


def load_token(repository: str) -> str:
    query = (
        "protocol=https\n"
        "host=github.com\n"
        f"path={repository}.git\n\n"
    )
    try:
        completed = subprocess.run(
            ["git", "credential", "fill"],
            input=query,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        raise GitHubAccessError("the Git credential manager could not start") from None
    if completed.returncode != 0:
        raise GitHubAccessError("the Git credential manager could not supply a credential")

    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            fields[key] = value
    token = fields.get("password", "")
    if not token:
        raise GitHubAccessError(
            "no approved HTTPS credential for github.com is available"
        )
    return token


def request_json(
    token: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, str] | None = None,
) -> Any:
    curl = shutil.which("curl")
    if not curl:
        raise GitHubAccessError("curl is required for GitHub HTTPS access")
    if any(character in token for character in '\r\n"\\'):
        raise GitHubAccessError("the stored credential has an unsupported format")

    config = "\n".join(
        [
            'header = "Accept: application/vnd.github+json"',
            f'header = "Authorization: Bearer {token}"',
            'header = "Content-Type: application/json"',
            'header = "User-Agent: cross-zone-development/0.1"',
            'header = "X-GitHub-Api-Version: 2022-11-28"',
        ]
    )
    arguments = [
        curl,
        "--config",
        "-",
        "--ssl-no-revoke",
        "--insecure",
        "--silent",
        "--show-error",
        "--fail",
        "--connect-timeout",
        "10",
        "--max-time",
        "30",
        "--max-filesize",
        str(MAX_RESPONSE_BYTES),
        "--request",
        method,
    ]

    payload_path: str | None = None
    if payload is not None:
        with tempfile.NamedTemporaryFile(prefix="cross-zone-github-", delete=False) as payload_file:
            payload_file.write(json.dumps(payload).encode("utf-8"))
            payload_path = payload_file.name
        arguments.extend(["--data-binary", f"@{payload_path}"])
    arguments.append(f"{API_ROOT}/{path}")

    try:
        try:
            completed = subprocess.run(
                arguments,
                input=config.encode("utf-8"),
                capture_output=True,
                check=False,
            )
        except OSError:
            raise GitHubAccessError("curl could not start") from None
    finally:
        if payload_path is not None:
            os.unlink(payload_path)

    if completed.returncode != 0:
        detail = "".join(
            character if character.isprintable() else " "
            for character in completed.stderr.decode("utf-8", errors="replace")
        )[:300]
        raise GitHubAccessError(
            f"GitHub HTTPS request failed with curl exit {completed.returncode}: {detail}"
        )
    if len(completed.stdout) > MAX_RESPONSE_BYTES:
        raise GitHubAccessError("GitHub response exceeds the safety limit")

    try:
        return json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GitHubAccessError("GitHub returned a non-JSON response") from error


def get_issue(token: str, repository: str, issue: int) -> dict[str, Any]:
    result = request_json(token, f"repos/{repository}/issues/{issue}")
    if not isinstance(result, dict) or "title" not in result:
        raise GitHubAccessError("GitHub returned an unexpected issue response")
    return {
        "number": result.get("number"),
        "title": result.get("title"),
        "state": result.get("state"),
        "comments": result.get("comments"),
        "body": result.get("body") or "",
    }


def get_comments(token: str, repository: str, issue: int) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for page in range(1, MAX_COMMENTS // 100 + 1):
        query = urllib.parse.urlencode({"per_page": 100, "page": page})
        result = request_json(
            token, f"repos/{repository}/issues/{issue}/comments?{query}"
        )
        if not isinstance(result, list):
            raise GitHubAccessError("GitHub returned an unexpected comments response")
        comments.extend(result)
        if len(result) < 100:
            return [
                {
                    "id": item.get("id"),
                    "author": (item.get("user") or {}).get("login"),
                    "created_at": item.get("created_at"),
                    "body": item.get("body") or "",
                }
                for item in comments
                if isinstance(item, dict)
            ]
    raise GitHubAccessError(
        f"comment history reaches the {MAX_COMMENTS}-comment safety limit"
    )


def validate_comment(body: str) -> None:
    if not body.strip():
        raise GitHubAccessError("comment body must not be empty")
    if len(body) > MAX_COMMENT_CHARS:
        raise GitHubAccessError(
            f"comment body exceeds {MAX_COMMENT_CHARS} Unicode characters"
        )
    if any(ord(character) < 32 and character not in "\n\r\t" for character in body):
        raise GitHubAccessError("comment body contains unsupported control characters")


def post_comment(
    token: str, repository: str, issue: int, body: str
) -> dict[str, Any]:
    validate_comment(body)
    result = request_json(
        token,
        f"repos/{repository}/issues/{issue}/comments",
        method="POST",
        payload={"body": body},
    )
    if not isinstance(result, dict) or not result.get("id") or not result.get("html_url"):
        raise GitHubAccessError("GitHub did not confirm the created comment")
    return {"id": result["id"], "html_url": result["html_url"]}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    get_parser = subparsers.add_parser("get", help="read an issue")
    get_parser.add_argument("repository")
    get_parser.add_argument("issue")
    get_parser.add_argument("--comments", action="store_true")

    comment_parser = subparsers.add_parser("comment", help="post stdin as a comment")
    comment_parser.add_argument("repository")
    comment_parser.add_argument("issue")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repository, issue = validate_target(args.repository, args.issue)
        if args.command == "comment":
            body = sys.stdin.read()
            validate_comment(body)
        token = load_token(repository)
        if args.command == "get":
            result = (
                get_comments(token, repository, issue)
                if args.comments
                else get_issue(token, repository, issue)
            )
        else:
            result = post_comment(token, repository, issue, body)
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    except GitHubAccessError as error:
        print(f"github issue access: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
