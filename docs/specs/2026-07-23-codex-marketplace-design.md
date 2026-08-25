# LingquLab Skills Codex Marketplace Design

Date: 2026-07-23

Status: Approved

Amended 2026-08-25: Superpowers Neo now publishes eleven skills at version `0.3.0`, including code simplification before final review and delivery. The updated inventory and validation counts below supersede the original ten-skill baseline.

## 1. Context

The original marketplace migration began from ten Superpowers Neo skill directories at the repository root and a repository script that copied them directly into `CODEX_HOME`.

The repository is expected to host additional skills and skill series over time. A flat source layout and one product-specific installer do not provide a catalog boundary, independent plugin versioning, or native installation through the Codex plugin CLI.

The repository will therefore become a Git-backed Codex marketplace. Superpowers Neo will be its first plugin, while future unrelated skills or coherent skill series can be added as separate plugins.

## 2. Goals

- Make `LingquLab/skills` installable as a Codex Git marketplace.
- Publish all eleven Superpowers Neo skills as one installable `superpowers-neo` plugin.
- Preserve independent skill discovery and the absence of a global entry skill.
- Establish a repository structure that supports multiple independently versioned plugins.
- Keep plugin metadata, installation documentation, and validation aligned with the current Codex marketplace schema.
- Preserve a manual installation path for Superpowers Neo as a fallback.

## 3. Non-Goals

- The original marketplace conversion does not add, remove, or redesign Superpowers Neo behavior; later behavior changes use normal versioned plugin updates and their own approved design boundary.
- Do not add a `using-superpowers` or other global entry skill.
- Do not combine all future LingquLab skills into one permanently growing plugin.
- Do not create MCP servers, apps, hooks, authentication flows, icons, or screenshots in this change.
- Do not add Codex product gating to the marketplace entry.
- Do not remove or rewrite currently installed personal copies under `CODEX_HOME`.
- Do not automatically configure the marketplace in a user's Codex installation.
- Do not change Git delivery authority as part of marketplace packaging; it remains governed by the Superpowers Neo delivery skill.

## 4. Architectural Decision

The repository will use one marketplace containing multiple plugins. A plugin is the installation and versioning boundary.

Superpowers Neo is one plugin because its eleven skills form one coherent development workflow series, are designed and tested together, and should be installed and upgraded atomically. This packaging decision does not create a global entry skill: Codex still discovers and loads each `superpowers-neo-*` skill through its own description and trigger.

Future additions follow these rules:

- A coherent skill series is one plugin containing all skills in that series.
- A standalone skill may be a one-skill plugin.
- Unrelated skills do not enter the `superpowers-neo` plugin.
- Every plugin owns its manifest, semantic version, skills, and optional plugin-local assets or integrations.
- Every plugin appears as a separate ordered entry in the marketplace catalog.

## 5. Repository Layout

The target layout is:

```text
skills/
|-- .agents/
|   `-- plugins/
|       `-- marketplace.json
|-- plugins/
|   `-- superpowers-neo/
|       |-- .codex-plugin/
|       |   `-- plugin.json
|       `-- skills/
|           |-- superpowers-neo-designing-complex-changes/
|           |-- superpowers-neo-executing-plans/
|           |-- superpowers-neo-code-simplification/
|           |-- superpowers-neo-git-delivery/
|           |-- superpowers-neo-handling-code-review-feedback/
|           |-- superpowers-neo-requesting-code-review/
|           |-- superpowers-neo-systematic-debugging/
|           |-- superpowers-neo-validation-strategy/
|           |-- superpowers-neo-using-git-worktrees/
|           |-- superpowers-neo-verification-before-completion/
|           `-- superpowers-neo-writing-plans/
|-- docs/
|   `-- specs/
|-- scripts/
|   |-- install.sh
|   `-- validate-skills.rb
|-- tests/
|   `-- superpowers-neo/
|       `-- scenarios/
|-- LICENSE
|-- README.md
`-- THIRD_PARTY_NOTICES.md
```

Repository-level documentation, licensing, cross-plugin tooling, and tests remain outside plugin packages. Runtime skill content lives only under its owning plugin; it is not duplicated at the repository root.

## 6. Marketplace Contract

The marketplace manifest is `.agents/plugins/marketplace.json`.

Its identity is:

- Marketplace name: `lingqulab`
- Display name: `LingquLab Skills`

The initial catalog contains one entry:

```json
{
  "name": "lingqulab",
  "interface": {
    "displayName": "LingquLab Skills"
  },
  "plugins": [
    {
      "name": "superpowers-neo",
      "source": {
        "source": "local",
        "path": "./plugins/superpowers-neo"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Developer Tools"
    }
  ]
}
```

The `source.path` is relative to the marketplace repository root. `policy.products` is intentionally omitted because no product override was requested. New plugins are appended to `plugins[]` unless an explicit catalog reordering decision is made.

## 7. Superpowers Neo Plugin Contract

The plugin root is `plugins/superpowers-neo`. Its folder name and manifest name must remain identical.

The manifest is `plugins/superpowers-neo/.codex-plugin/plugin.json` and has these semantic values:

- Name: `superpowers-neo`
- Initial version: `0.1.0`
- Developer: `LingquLab`
- License: `MIT`
- Repository: `https://github.com/LingquLab/skills`
- Skills path: `./skills/`
- Display name: `Superpowers Neo`
- Category: `Developer Tools`
- Capabilities limited to behavior actually supplied by the skills

The manifest must contain valid non-placeholder descriptions and required Codex interface metadata. It must not declare apps, MCP servers, hooks, or asset paths unless their companion artifacts are added later.

The plugin version is independent of the marketplace repository. A future behavioral or packaging release bumps the plugin semantic version deliberately; unrelated plugin releases do not force a Superpowers Neo version change.

## 8. Migration

Implementation will perform these path migrations without changing skill content:

1. Move `skills/superpowers-neo-*` to `plugins/superpowers-neo/skills/`.
2. Move `tests/scenarios/` to `tests/superpowers-neo/scenarios/` so future plugins have an unambiguous test namespace.
3. Add the marketplace manifest and the Superpowers Neo plugin manifest.
4. Update `scripts/install.sh` to copy from `plugins/superpowers-neo/skills/` while preserving its current refusal to overwrite targets and its transactional failure behavior.
5. Update `scripts/validate-skills.rb` to validate the new paths plus the marketplace and plugin contracts.
6. Update README installation, validation, layout, and contribution guidance.

The existing approved Superpowers Neo design spec remains at its current repository path. Documentation links to runtime skill paths must be updated if any exist.

No duplicate compatibility copy remains under the old top-level `skills/` path. Keeping two authoritative copies would allow marketplace and manual installations to drift.

## 9. Installation Interface

The primary public installation flow is:

```bash
codex plugin marketplace add LingquLab/skills
codex plugin add superpowers-neo@lingqulab
```

After installation, a new Codex task is required for reliable discovery of newly installed skills.

The manual fallback remains:

```bash
scripts/install.sh --dry-run
scripts/install.sh
```

The manual installer remains explicitly scoped to Superpowers Neo. Future plugins are installed through the marketplace by default and do not silently become part of this fallback script.

## 10. Future Plugin Addition Contract

Adding a future plugin requires all of the following:

1. Create `plugins/<plugin-name>/.codex-plugin/plugin.json`.
2. Place runtime skills under `plugins/<plugin-name>/skills/`.
3. Append one matching entry to `.agents/plugins/marketplace.json`.
4. Use a normalized lower-case hyphenated name consistently for the directory, manifest, and marketplace entry.
5. Assign an independent strict semantic version.
6. Add plugin-specific tests under `tests/<plugin-name>/` when tests are needed.
7. Extend repository validation so the new entry, manifest, paths, and skill metadata are checked.
8. Document the plugin and its installation selector in README.

Marketplace order is user-visible render order. Existing entries are not reordered as a side effect of adding a plugin.

## 11. Validation Strategy

Implementation is accepted only with fresh evidence from the final layout.

### 11.1 Repository validation

`scripts/validate-skills.rb` must verify:

- The marketplace JSON parses and has the expected name and display name.
- Every marketplace entry contains `name`, `source`, `policy`, and `category`.
- Every local source path exists and resolves inside `plugins/`.
- Every plugin folder contains a matching `.codex-plugin/plugin.json`.
- Plugin manifests use strict semantic versions and valid relative component paths.
- Declared skills directories exist and contain structurally valid skill packages.
- Superpowers Neo contains exactly the eleven approved skills.
- The ten Superpowers Neo behavior scenario definitions remain structurally valid.
- No placeholder metadata remains.

### 11.2 Plugin schema validation

Run the current Codex plugin validation helper against `plugins/superpowers-neo`. The implementation should use the helper supplied by the installed `plugin-creator` skill instead of copying its schema into the repository.

### 11.3 Installer validation

- Run shell syntax validation.
- Run a dry-run installation.
- Install to a temporary empty target and compare installed skill content with the plugin source.
- Retain failure and rollback checks for partial copy, interruption, and pre-existing targets.

### 11.4 Marketplace smoke test

Use an isolated temporary Codex home or equivalent disposable configuration to:

1. Add the local repository as a marketplace.
2. Confirm the marketplace is identified as `lingqulab`.
3. Install `superpowers-neo@lingqulab`.
4. Confirm all eleven skills are present in the installed plugin artifact.

This smoke test must not replace or overwrite the user's configured marketplaces or installed personal skill copies.

## 12. Compatibility and Risk

### 12.1 Existing manual installations

Previously copied skills under `CODEX_HOME/skills` are not migrated automatically. They may coexist with the marketplace plugin during validation, but duplicate skill names can make the active source ambiguous. README must explain that users should deliberately remove or archive the manual copies after confirming the marketplace installation.

### 12.2 Path-sensitive tooling

The primary migration risk is a stale assumption that skills live at repository-root `skills/`. Repository search, validation, installer tests, and documentation checks must cover this boundary.

### 12.3 Marketplace schema drift

Codex marketplace and plugin schemas can evolve. Repository validation covers stable local invariants, while the installed Codex `plugin-creator` validator and CLI smoke test are the authoritative compatibility checks for the current environment.

### 12.4 Source branch availability

Until marketplace changes are merged into the repository's default branch, `codex plugin marketplace add LingquLab/skills` will not see them without an explicit ref. Public documentation must show the default command only after the marketplace structure is available on the default branch.

## 13. Acceptance Criteria

- `LingquLab/skills` has a valid `.agents/plugins/marketplace.json` named `lingqulab`.
- The marketplace exposes an available `superpowers-neo` plugin in `Developer Tools`.
- The plugin has a valid `.codex-plugin/plugin.json` at version `0.3.0`.
- All eleven Neo skills exist only under `plugins/superpowers-neo/skills/` and follow the approved workflow behavior.
- The ten behavior scenario definitions remain valid under their plugin-specific test namespace.
- The repository validator, plugin validator, installer checks, and isolated marketplace smoke test pass.
- README documents marketplace installation, manual fallback, duplicate-installation cleanup, validation, and future plugin structure.
- No global entry skill, new runtime integration, product gate, or unrelated skill is introduced.
- The spec is committed with the implementation rather than as a spec-only commit.

## 14. Approval Boundary

This spec governs the marketplace conversion only. Implementation may refine file-level mechanics while preserving the architecture, interfaces, scope, and acceptance criteria above.

User approval is required again before implementation if the work would:

- package each Neo skill as a separate plugin;
- place unrelated future skills inside `superpowers-neo`;
- change the marketplace or plugin names;
- add product gating, authentication, MCP servers, apps, hooks, or assets;
- remove the manual installation fallback;
- change approved Superpowers Neo behavior; or
- require a destructive migration of installed user state.
