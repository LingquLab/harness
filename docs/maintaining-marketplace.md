# Maintaining the Marketplace

## Validate

The validator uses Ruby standard libraries and Node.js 18+ for draw.io shape-search regression tests. Its offline regression checks also run Python 3; persistent-shell tests require Paramiko in the active `python3` environment (`python3 -m pip install paramiko`, preferably in a virtual environment).

```bash
ruby scripts/validate-skills.rb
ruby -c scripts/validate-skills.rb
bash -n scripts/install.sh
```

These checks cover the Codex marketplace catalog and manifests, localized plugin documentation, skill packages, relative documentation links, and plugin behavior scenarios.

Behavioral validation is a fresh-agent evaluation. Give a new agent only the relevant `SKILL.md` files and the request section from one file under `tests/<plugin-name>/scenarios/`, then compare the response with its expected behaviors and failure signals. Do not include the expected result in the agent prompt.

Before publishing a plugin change, also run the current validator supplied by Codex's installed `plugin-creator` skill against that plugin directory. This catches schema changes that may be newer than the repository validator.

## Add a Plugin

Each independently versioned plugin lives under:

```text
plugins/<plugin-name>/
|-- .codex-plugin/plugin.json
|-- README.md
|-- README_CN.md
`-- skills/
```

To add a plugin:

1. Use one normalized lower-case hyphenated name for its directory, manifest, and marketplace entry.
2. Give the plugin its own strict semantic version.
3. Put runtime skills under `plugins/<plugin-name>/skills/`.
4. Register it in `.agents/plugins/marketplace.json` for Codex; catalog order is user-visible.
5. Keep the plugin version synchronized across its supported manifests, catalog entries, and the root README.
6. Include the Codex category, installation and authentication policy fields.
7. Provide semantically equivalent `README.md` and `README_CN.md` files covering invocation, dependencies, network access, commands, file effects, Hooks, MCP, and licensing. Keep provenance in THIRD_PARTY_NOTICES.md or a dedicated source record, linked from the README.
8. Add plugin-specific tests under `tests/<plugin-name>/` and extend repository validation.
9. Document its Codex selector as `<plugin-name>@lingqulab`.

Keep coherent skill series together, but publish unrelated skills as separate plugins instead of expanding one catch-all package.
