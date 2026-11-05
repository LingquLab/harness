# LingquLab Skills

[中文文档](README_CN.md)

Skills for ZCode and Codex that help you develop software, build Ascend C operators, research AI systems, create diagrams, and validate work across development and protected environments. Install only the plugins you need.

## Install

In ZCode, open **Settings → Plugins → Create → Add marketplace** and enter `LingquLab/harness`.

In Codex, add the marketplace and install a plugin:

```bash
codex plugin marketplace add LingquLab/harness
codex plugin add superpowers-neo@lingqulab
```

Replace `superpowers-neo` with a plugin name below. Start a new Codex task after installation to discover its skills.

## Choose a Plugin

| Plugin | What it helps you do | Version |
|---|---|---|
| [superpowers-neo](plugins/superpowers-neo/README.md) | Design, implement, debug, review and deliver software changes with checks suited to the task | `0.3.5` |
| [ascendc-development](plugins/ascendc-development/README.md) | Develop Ascend C operators, check APIs, diagnose runtime failures and configure CANN | `0.3.1` |
| [cross-zone-development](plugins/cross-zone-development/README.md) | Run protected-environment checks and receive bounded results through HAPI | `0.7.2` |
| [persistent-shell](plugins/persistent-shell/README.md) | Reuse SSH sessions from Windows while keeping the remote directory and shell state | `0.1.1` |
| [archify](plugins/archify/README.md) | Turn system descriptions or code into interactive diagrams with image and video export | `2.17.0-dev.1` |
| [aikg-search](plugins/aikg-search/README.md) | Find explanations and references for AI fundamentals, inference, training, GPU/NPU and performance analysis | `0.1.0` |
| [wiki-search](plugins/wiki-search/README.md) | Find Huawei WIKI documents by keyword, knowledge base, category or document subtree | `0.1.2` |

## Get Started

After installing a plugin, describe the task in your own words. For example:

- **Software development:** “Find the cause of this test failure and fix it.”
- **Ascend C:** “Review this operator's tiling and memory alignment for the target CANN version.”
- **Cross-zone checks:** “Run this read-only check in green and report the result.” Green setup is covered in the [user guide](plugins/cross-zone-development/USER_GUIDE_CN.md).
- **SSH sessions:** “Use a persistent shell for repeated commands on this host.” Requires Windows, SSH access and Python with Paramiko.
- **Diagrams:** “Draw the request flow from browser to API, cache and database.” Requires Node.js 18 or newer.
- **AI knowledge:** “Explain KV Cache and what determines its memory use.” Public AIKG sources need no WIKI authentication.
- **Huawei WIKI:** “Search this knowledge base for deployment instructions.” Online access requires the cross-zone plugin and authenticated `wiki-cli` in green.

General knowledge searches consult AIKG first and use WIKI when more evidence is needed. You can explicitly choose a source. For WIKI searches, a supplied local document library is checked before online access.

Plugin guides describe installation, dependencies, commands and file or network access in more detail.

## Manual Neo Installation

If your environment does not support plugins, preview and install Neo's skills directly:

```bash
scripts/install.sh --dry-run
scripts/install.sh
```

Use `--target PATH` to select another directory. The default is `${CODEX_HOME:-$HOME/.codex}/skills`. Existing targets are never overwritten. Avoid installing the same skills both manually and through the marketplace; remove older copies only after verifying the new installation.

## Contributing and Licenses

See [marketplace maintenance](docs/maintaining-marketplace.md) for validation and adding plugins.

The marketplace and most plugins use [MIT](LICENSE). Ascend C Development uses its bundled [CANN license](plugins/ascendc-development/LICENSE). Other bundled materials retain their own terms; see [third-party notices](THIRD_PARTY_NOTICES.md).
