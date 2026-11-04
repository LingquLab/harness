# WIKI Search

[中文文档](./README_CN.md)

Search Huawei WIKI using `wiki-cli`. A user-provided local library is searched through its `_index.md` files first; online search is used when no relevant local result is found.

For general knowledge queries, use `aikg-search` first; enter the WIKI stage only when AIKG evidence is insufficient or the user explicitly requests WIKI.

Install with `codex plugin add wiki-search@lingqulab`, then ask to search Huawei WIKI or invoke `$wiki-search`. See [the skill](skills/wiki-search/SKILL.md) for ranges, parameters, examples, and result handling.

Dependencies: install `cross-zone-development@lingqulab` and establish its HAPI connection (OPEN/READY or a valid green OPEN). Online commands run only in the green zone through bounded EXEC; TASK requires an explicit user request. Install `wiki-cli` separately in the green zone; online searches require `wiki auth status` to return `✓ 已认证`. This plugin does not install the CLI or authenticate for you. Local search needs a text search tool such as `rg`, without network access or authentication.

Commands: `wiki auth status` and `wiki doc search`, optionally `wiki doc search --help`. Online search sends keywords and reference URLs to Huawei WIKI through the CLI and needs access to that service. Local searches read the supplied library in its own zone. Protected responses use AI-reviewed cross-zone results; raw search JSON and full documents stay in green. The skill does not request document writes or create local files; CLI credential/cache behavior belongs to the separately installed CLI. No Hooks, MCP servers, or background services are bundled; cross-zone execution uses the separately configured HAPI Bridge.

The guidance is based on user-supplied wiki-cli search instructions, including the local `wiki-doc.md` search reference. The CLI and Huawei service are not bundled. This plugin is licensed under the repository's MIT license.
