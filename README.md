# LingquLab Skills

LingquLab Skills is a Git-backed Codex marketplace for independently installable skills and skill series.

## Install the Marketplace

Add this repository as a Codex marketplace:

```bash
codex plugin marketplace add LingquLab/skills
```

Then install a plugin from the catalog:

```bash
codex plugin add superpowers-neo@lingqulab
```

Start a new Codex task after installation so newly installed skills are discovered reliably.

## Plugins

| Plugin | Description | Version |
|---|---|---|
| `superpowers-neo` | Pragmatic software-development workflows with rigor scaled to task complexity and risk | `0.2.1` |
| `ascendc-development` | Version-aware Ascend C operator development, API guidance, review, diagnostics, and CANN setup workflows | `0.2.0` |

## Ascend C Development

Install the plugin from the marketplace:

```bash
codex plugin add ascendc-development@lingqulab
```

The plugin contains seven independently triggered skills:

| Skill | Use when |
|---|---|
| `ascendc-api-best-practices` | Implementing or debugging Ascend C API usage and alignment, buffer, precision, or pipeline behavior |
| `ascendc-code-review` | Reviewing Host, Tiling, Kernel, SIMT, build, or operator changes |
| `ascendc-docs-search` | Locating version-matched local or official Ascend C documentation and examples |
| `ascendc-env-check` | Performing read-only CANN environment and NPU visibility diagnostics |
| `ascendc-operator-development` | Developing or migrating a complete registered or direct-launch Ascend C operator through layered validation |
| `ascendc-runtime-debug` | Diagnosing runtime, Tiling, launch, device-exception, hang, precision, or performance failures from bounded evidence |
| `cann-env-setup` | Planning or carrying out a guarded, version-matched CANN installation or repair |

The original five skills are adapted from TileXR's Claude skills at source commit `1e2619e793b5894a1aec2d7d6897dbe5f7c501c0`. The operator-development and runtime-debugging workflows extend that baseline without importing cannBot automation. Claude-specific tool calls, fixed environment assumptions, destructive diagnostic commands, and the duplicate `commit-push-pr` skill are intentionally not shipped. Useful online workflows remain scripted: one dependency-free client searches and fetches Huawei's official documentation, and another obtains public GitCode PR diffs through bounded shallow fetches. See the [migration audit](docs/specs/2026-07-23-ascendc-development-migration.md), [expansion plan](docs/plans/2026-07-24-ascendc-development-expansion.md), and [third-party notices](THIRD_PARTY_NOTICES.md).

## Superpowers Neo

Superpowers Neo is a modular software-development workflow for coding agents. It keeps explicit design, plan execution, debugging, review, verification, and Git delivery practices while scaling ceremony to the ambiguity and risk of the task.

Neo has no global entry skill. Each skill is independently discoverable and loads only when its own trigger matches.

| Skill | Use when |
|---|---|
| `superpowers-neo-designing-complex-changes` | A change is complex, ambiguous, cross-component, or architecture-sensitive |
| `superpowers-neo-writing-plans` | Approved work needs a multi-step or subagent-ready implementation plan |
| `superpowers-neo-using-git-worktrees` | Workspace isolation may be needed for dirty or parallel work |
| `superpowers-neo-executing-plans` | An in-scope plan is ready for main-agent and scoped-subagent execution |
| `superpowers-neo-validation-strategy` | A change needs validation proportional to its risk |
| `superpowers-neo-systematic-debugging` | A bug or unexpected failure needs evidence-based diagnosis |
| `superpowers-neo-requesting-code-review` | A substantial or risky change benefits from independent review |
| `superpowers-neo-handling-code-review-feedback` | Review feedback needs technical evaluation |
| `superpowers-neo-verification-before-completion` | Work is about to be described as complete, fixed, or passing |
| `superpowers-neo-git-delivery` | Completed Git work needs scoped commit and delivery handling |

### What Changes from Superpowers

- No `using-superpowers` startup or umbrella skill.
- Complex-change design and persistent plans trigger only when complexity justifies them.
- Worktrees and subagents are selected by isolation and coordination value.
- Validation is risk-driven; test-first development is useful but not universal.
- Independent review is selected by risk rather than required after every task.
- Automatic delivery authorizes scoped task commits and normal pushes from established task-owned non-default branches. Manually invoking `superpowers-neo-git-delivery` additionally authorizes task-branch creation, normal push, and PR creation; merge, history rewrite, force push, hook bypass, and cleanup remain separately protected.
- Skill-authoring methodology is not part of the shipped series.

See the [Superpowers Neo design](docs/specs/2026-07-22-superpowers-neo-design.md) for its behavior contract and the [marketplace design](docs/specs/2026-07-23-codex-marketplace-design.md) for packaging and extension decisions.

## Validate

The repository validator uses Ruby standard libraries and needs no package installation:

```bash
ruby scripts/validate-skills.rb
ruby -c scripts/validate-skills.rb
bash -n scripts/install.sh
```

It checks the marketplace catalog, both plugin manifests and paths, all ten Superpowers Neo skill packages, all seven Ascend C Development skill packages, relative documentation links, nine Superpowers Neo scenarios, and two Ascend C Development scenarios.

Behavioral validation is a fresh-agent evaluation. Give a new agent only the relevant `SKILL.md` files and the request section from one file under `tests/<plugin-name>/scenarios/`, then compare the response with its expected behaviors and failure signals. Do not include the expected result in the agent prompt.

Before publishing a plugin change, also run the current validator supplied by Codex's installed `plugin-creator` skill against that plugin directory. This catches schema changes that may be newer than the repository validator.

## Manual Superpowers Neo Installation

Marketplace installation is preferred. A manual fallback remains available for environments that do not use Codex plugins.

Preview the installation:

```bash
scripts/install.sh --dry-run
```

Install to `${CODEX_HOME:-$HOME/.codex}/skills`:

```bash
scripts/install.sh
```

Use `--target PATH` to install elsewhere. The installer copies exactly the ten Neo skill directories from `plugins/superpowers-neo/skills/`, refuses to overwrite existing targets, and never disables or removes the original Superpowers plugin.

### Avoid Duplicate Installations

Manual copies under `${CODEX_HOME:-$HOME/.codex}/skills/superpowers-neo-*` can coexist with the marketplace plugin, but duplicate skill names make the active source ambiguous. After validating the marketplace plugin in a new Codex task, deliberately remove or archive the old manual copies. Marketplace installation does not modify them automatically.

The original `superpowers@openai-api-curated` plugin may also coexist with Neo during evaluation. Remove it only after Neo has been reviewed in real tasks and the user explicitly authorizes that cutover.

## Add a Plugin

Each independently versioned plugin lives under:

```text
plugins/<plugin-name>/
|-- .codex-plugin/plugin.json
`-- skills/
```

To add a plugin:

1. Use one normalized lower-case hyphenated name for its directory, manifest, and marketplace entry.
2. Give the plugin its own strict semantic version.
3. Put runtime skills under `plugins/<plugin-name>/skills/`.
4. Append its entry to `.agents/plugins/marketplace.json`; catalog order is user-visible.
5. Include `policy.installation`, `policy.authentication`, and `category`; omit product gating unless it is an explicit requirement.
6. Add plugin-specific tests under `tests/<plugin-name>/` and extend repository validation.
7. Document its selector as `<plugin-name>@lingqulab`.

Keep coherent skill series together, but publish unrelated skills as separate plugins instead of expanding one catch-all package.

## Attribution

Superpowers Neo is an independent adaptation inspired by [Superpowers](https://github.com/obra/superpowers) by Jesse Vincent. Superpowers is available under the MIT License. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the upstream notice. This project is not affiliated with or endorsed by the upstream project.

## License

This marketplace and Superpowers Neo are licensed under the [MIT License](LICENSE). The `ascendc-development` plugin is separately licensed under the [CANN Open Software License Agreement Version 2.0](plugins/ascendc-development/LICENSE); see [third-party notices](THIRD_PARTY_NOTICES.md).
