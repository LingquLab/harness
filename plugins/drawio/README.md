# draw.io

[中文文档](README_CN.md)

Create editable `.drawio` diagrams from a description, Mermaid or draw.io XML.
Optionally export PNG, SVG or PDF with embedded diagram XML, or generate a URL
that opens the diagram in the browser editor.

## Install and use

In ZCode, add `LingquLab/harness` as a marketplace and install `drawio`.
In Codex:

```bash
codex plugin marketplace add LingquLab/harness
codex plugin add drawio@lingqulab
```

Start a new task, then ask: “Use drawio to draw our login flow as an editable
.drawio file.” Or: “Use drawio to export this architecture as SVG.” Explicitly
select `archify` when you want its interactive HTML diagrams instead.

## Requirements and access

- Writing native XML `.drawio` files needs no draw.io installation or MCP setup.
- Mermaid conversion, ELK layout and PNG/SVG/PDF export require draw.io Desktop
  and its CLI. On Linux without a display, exports may also need Xvfb. Without
  Desktop, the skill writes XML `.drawio` files or a browser URL.
- Node.js 18+ and network access are needed for the bundled shape search;
  Node.js is also used to compress browser URLs. References are fetched from
  GitHub, shapes from jsDelivr, and icons from `icons.diagrams.net`. Icon search
  sends the shape query to that service. Browser URLs contain the diagram and
  open `app.diagrams.net`.
- The skill writes diagram and temporary source files, runs shell commands and
  may launch draw.io or the default browser. Its export workflow removes the
  intermediate `.drawio` source after creating an editable export.
- No hooks, MCP servers, accounts or credentials are configured by this plugin.

Licensed under [Apache-2.0](LICENSE). See the [vendor record](VENDORED.md) for
upstream attribution and marketplace adaptations.
