# AIKG Search

[中文文档](README_CN.md)

Search the public [AI Knowledge Graph](https://github.com/AmourSec/aikg) before Huawei WIKI for general knowledge questions. Read `llms.txt`, retrieve relevant Markdown bodies, and cite source paths. If evidence is missing or unavailable, use `wiki-search`; explicit source restrictions take precedence.

Install with `codex plugin add aikg-search@lingqulab`, then invoke `$aikg-search` or ask an AI infrastructure question. See [the skill](skills/aikg-search/SKILL.md). Optional fallback plugins: `wiki-search@lingqulab` and `cross-zone-development@lingqulab`; WIKI commands run only in green.

Dependencies and effects: public retrieval uses an available web reader or Git and `rg` for local Markdown. An existing checkout can be read without network access; optional shallow cloning writes only a temporary checkout. No MkDocs server, upstream router, Python packages, Hooks, or MCP servers are required or bundled. Public requests contact GitHub or GitHub Pages; do not send internal WIKI material to them. Green fallback uses the separately configured HAPI Bridge and authenticated wiki-cli.

This MIT-licensed plugin contains original harness retrieval instructions, without vendored upstream content or code. Upstream documentation is CC-BY-4.0; upstream code/configuration is MIT. Preserve attribution when using its material. Integration reviewed against upstream commit `f4a42b37e4b9c13e829d9ac9800a26684db7de2d`; retrieval should use current sources or identify a local snapshot. See [upstream license](https://github.com/AmourSec/aikg/blob/master/LICENSE).
