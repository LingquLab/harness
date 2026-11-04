# WIKI Search

[中文文档](README_CN.md)

Find Huawei WIKI documents by keyword, title or body text. Search the whole platform, a knowledge base, a category, or a document and its children. Results include relevant document links and short matching summaries.

## Use

Install with `codex plugin add wiki-search@lingqulab`, then ask to search Huawei WIKI or invoke `$wiki-search`. Provide a document URL when limiting the search to a knowledge base, category or subtree. A supplied local WIKI library is searched first.

General knowledge questions start with `aikg-search`; explicitly requesting WIKI takes you directly to this plugin. See [the search guide](skills/wiki-search/SKILL.md) for parameters and examples.

## Requirements and access

Online search requires `cross-zone-development@lingqulab`, a connected green Bridge, and `wiki-cli` installed and authenticated in green (`wiki auth status` returns `✓ 已认证`). The agent checks authentication and runs `wiki doc search` in green. Local-library retrieval needs a text search tool such as `rg`, without WIKI authentication.

Online queries send keywords and reference URLs to Huawei WIKI through the CLI. Local queries read the supplied library in its own zone. Protected results return through cross-zone review; raw responses and full documents stay in green. Search does not edit documents. Credentials and caches are managed by wiki-cli. Hooks and MCP: none; cross-zone execution uses the separately configured HAPI Bridge.

Licensed under MIT. The CLI and Huawei service are provided separately.
