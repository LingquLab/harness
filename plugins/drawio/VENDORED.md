# Vendored draw.io plugin

- Source: https://github.com/jgraph/drawio-mcp
- Commit: `fee698bdac5ef5b3adb5be3c99754a367370d2ff`
- Upstream path: `plugins/codex/drawio/`
- Version: `1.2.6`
- License: Apache-2.0; see [LICENSE](LICENSE).

The runtime skill, shape-search script, Codex manifest and logo are copied from
this snapshot. Local changes narrow the skill discovery description to respect
explicit selection of other diagram tools, add `agents/openai.yaml`, ZCode
metadata, and replace the upstream README with marketplace user guides.
No MCP server or hooks are bundled.

To refresh, replace the upstream files, reapply these adaptations, synchronize
both manifests and catalog versions, and run the repository validator and
`node --test tests/drawio/test-find-shapes.cjs`.
