#!/usr/bin/env python3
"""Scan a Chinese draft for phrases that need review."""

import argparse
import json
import re
import sys
from pathlib import Path


BLACKLIST_PATH = Path(__file__).resolve().parents[1] / "references" / "blacklist.json"


def main():
    parser = argparse.ArgumentParser(description="扫描中文草稿中的黑名单词汇。")
    parser.add_argument("file", nargs="?", default="-", help="UTF-8 文件路径，默认从标准输入读取")
    args = parser.parse_args()
    source = "stdin" if args.file == "-" else args.file

    try:
        blacklist = json.loads(BLACKLIST_PATH.read_text(encoding="utf-8"))
        if not isinstance(blacklist, dict) or not blacklist or not all(
            term.strip() and isinstance(hint, str) and hint.strip()
            for term, hint in blacklist.items()
        ):
            raise ValueError(f"{BLACKLIST_PATH}: 黑名单必须包含词汇及对应的改写提示")

        if args.file == "-":
            draft = sys.stdin.buffer.read().decode("utf-8-sig")
        else:
            draft = Path(args.file).read_text(encoding="utf-8-sig")
    except (OSError, ValueError) as error:
        parser.exit(2, f"扫描失败（{source}）：{error}\n")

    terms = sorted(blacklist, key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(term) for term in terms))
    found = False
    for line_number, line in enumerate(draft.splitlines(), start=1):
        for match in pattern.finditer(line):
            term = match.group()
            print(f"{source}:{line_number}:{match.start() + 1}: {term}：{blacklist[term]}")
            found = True

    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
