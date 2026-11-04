# AIKG Search

[中文文档](README_CN.md)

Find explanations and references in the public [AI Knowledge Graph](https://github.com/AmourSec/aikg). It covers AI fundamentals, inference and training systems, GPU/NPU architecture, Ascend/CANN, kernels, compilers and performance analysis.

## Use

Install with `codex plugin add aikg-search@lingqulab`, then ask a question such as “Explain KV Cache memory usage” or invoke `$aikg-search`. Answers use relevant document evidence and include source links. You can also supply a local AIKG checkout for offline retrieval.

For general knowledge queries, AIKG is searched first. When more evidence is needed, the agent can continue with `wiki-search@lingqulab`; online WIKI access also requires `cross-zone-development@lingqulab` and a configured green environment. You can explicitly limit a query to a source.

## Requirements and access

Public retrieval uses an available web reader or Git and `rg` for local Markdown. Public requests contact GitHub or GitHub Pages; internal WIKI material stays out of those requests. Existing checkouts are read without modification; optional shallow cloning writes a temporary checkout. No website server is needed. Hooks and MCP: none.

The plugin is MIT-licensed. AIKG documentation is CC-BY-4.0; preserve source attribution when using it. See [third-party notices](../../THIRD_PARTY_NOTICES.md) and [upstream terms](https://github.com/AmourSec/aikg/blob/master/LICENSE).
