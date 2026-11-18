# Chinese Technical Writing

[中文文档](README_CN.md)

Write or review Chinese technical documents, code comments, PR descriptions, and replies. Describe concrete actions supported by the implementation and keep English technical terms and identifiers such as `communicator` and `opaque handle`.

## Use

Install `chinese-writing@lingqulab` with `codex plugin add chinese-writing@lingqulab`, open a new Codex task, and ask it to review a Chinese draft or invoke `$chinese-writing`.

The [skill instructions](skills/chinese-writing/SKILL.md) show how to scan a UTF-8 file or standard input. The scanner uses Python 3 and reads the [vocabulary blacklist](skills/chinese-writing/references/blacklist.json) locally. It prints each match with a position and a rewrite hint, leaves the draft intact, and needs no network access. Hooks and MCP: none.

Licensed under [MIT](../../LICENSE).
