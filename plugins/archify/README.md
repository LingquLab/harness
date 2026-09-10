# Archify

[中文文档](./README_CN.md)

This ZCode and Codex plugin turns codebases or system descriptions into
validated, interactive architecture, workflow, sequence, data-flow, and
lifecycle diagrams. It produces self-contained HTML with inline SVG and
supports static image and WebM export.

## Use

Ask the agent to use Archify and describe the system or diagram you need. For
example: `Use Archify to map Browser -> API -> Redis -> PostgreSQL.` The skill
can inspect repository evidence when the diagram must reflect real code.

## Dependencies and effects

- Runtime: Node.js 18 or newer.
- Network: the packaged update checker may fetch Archify's fixed stable update
  manifest; set `ARCHIFY_UPDATE_CHECK_DISABLED=1` to disable it. Diagram
  generation itself is local.
- Commands: invokes the vendored Node.js renderer, validator, preview, and
  export utilities.
- Files: writes requested JSON specifications and generated HTML or export
  artifacts. Preview mode opens a loopback-only local server.
- Hooks and MCP: none.

The upstream release artifact is vendored at the commit recorded in
[VENDORED.md](./VENDORED.md). Archify is MIT-licensed; bundled brand marks and
fonts retain the terms documented in
[`skills/archify/THIRD_PARTY_NOTICES.md`](./skills/archify/THIRD_PARTY_NOTICES.md).
