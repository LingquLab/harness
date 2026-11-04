# Third-Party Notices

Superpowers Neo adapts software-development workflow concepts and may include modified portions of documentation from the Superpowers project:

- Project: Superpowers
- Source: https://github.com/obra/superpowers
- Copyright: Copyright (c) 2025 Jesse Vincent
- License: MIT License

The upstream MIT notice follows.

```text
MIT License

Copyright (c) 2025 Jesse Vincent

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## caarlos0 Code Simplifier

The `superpowers-neo-code-simplification` skill primarily adapts the general workflow and guardrails from caarlos0's code-simplifier skill. It does not copy the upstream language-specific guides.

- Project: caarlos0/dotfiles
- Source: https://github.com/caarlos0/dotfiles/tree/b2c38ba14c4295476f4672bb097a405edd992642/skills/code-simplifier
- Source commit: `b2c38ba14c4295476f4672bb097a405edd992642`
- Copyright: Copyright (c) 2023-2025 Carlos Alexandro Becker
- License: MIT License

The upstream MIT notice follows.

```text
MIT License

Copyright (c) 2023-2025 Carlos Alexandro Becker

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## TileXR Ascend C Skills

The `ascendc-development` plugin adapts and modifies Ascend C and CANN skill documentation and diagnostic scripts from TileXR:

- Project: TileXR
- Source: https://github.com/LingquLab/TileXR/tree/1e2619e793b5894a1aec2d7d6897dbe5f7c501c0/.claude/skills
- Source commit: `1e2619e793b5894a1aec2d7d6897dbe5f7c501c0`
- Copyright: Copyright (c) 2026 Huawei Technologies Co., Ltd.
- License: CANN Open Software License Agreement Version 2.0
- Included license: `plugins/ascendc-development/LICENSE`
- Official license source used to recover the upstream repository's missing license file: https://gitee.com/ascend/shmem/blob/master/LICENSE

The CANN license applies to the `ascendc-development` plugin and its adapted contents. In particular, its grant is limited to developing software for use with Ascend processors. The repository's root MIT license does not replace that plugin-specific license.

The original five skills are adapted from TileXR's Claude skills at source commit `1e2619e793b5894a1aec2d7d6897dbe5f7c501c0`. The operator-development and runtime-debugging workflows extend that baseline without importing cannBot automation. Claude-specific tool calls, fixed environment assumptions, destructive diagnostic commands, and the duplicate `commit-push-pr` skill are intentionally not shipped. Useful online workflows remain scripted: one dependency-free client searches and fetches Huawei's official documentation, and another obtains public GitCode PR diffs through bounded shallow fetches. See the [migration audit](docs/specs/2026-07-23-ascendc-development-migration.md), [expansion plan](docs/plans/2026-07-24-ascendc-development-expansion.md), and [third-party notices](THIRD_PARTY_NOTICES.md).

## Archify

The `archify` plugin vendors the upstream Archify runtime release artifact:

- Project: Archify
- Source: https://github.com/tt-a1i/archify
- Source commit: `18911058008f17dc065af23a2cdc9bfeff6d3f7a`
- Version: `2.17.0-dev.1`
- Copyright: Copyright (c) 2026 tt-a1i (Archify); Copyright (c) 2025 Cocoon AI
- License: MIT
- Included notices: `plugins/archify/skills/archify/LICENSE` and `plugins/archify/skills/archify/THIRD_PARTY_NOTICES.md`

The included notices also record the separate terms and trademark guidance for
bundled brand marks and fonts. The repository's root MIT license does not
replace those terms.

## Avoid Overkill Engineering Concepts

Superpowers Neo independently restates selected software-design, debugging and testing principles informed by avoid-overkill. Its skill text, case files, writing guidance and plugin infrastructure are not vendored.

- Project: 6Kmfi6HP/avoid-overkill
- Source: https://github.com/6Kmfi6HP/avoid-overkill/tree/3e6c6da904f857c1eae83ee580131ca4cbd58df7/skills/avoid-overkill
- Source commit: `3e6c6da904f857c1eae83ee580131ca4cbd58df7`
- Copyright: Copyright (c) 2026 6Kmfi6HP
- License: MIT License; the MIT permission and warranty notice reproduced above also applies with this source's copyright notice.

## AI Knowledge Graph retrieval source

The aikg-search plugin links to [AmourSec/aikg](https://github.com/AmourSec/aikg); it does not vendor its documents, code or skills. Integration was reviewed against commit `f4a42b37e4b9c13e829d9ac9800a26684db7de2d`. Its documentation is CC-BY-4.0 and its code/configuration is MIT; see the [upstream license](https://github.com/AmourSec/aikg/blob/master/LICENSE). Retrieval uses current sources or identifies the local snapshot.
