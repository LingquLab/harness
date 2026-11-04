# AIKG 知识搜索

[English documentation](README.md)

未限定来源的知识查询优先检索公开的 [AI Knowledge Graph](https://github.com/AmourSec/aikg)，再使用华为 WIKI。读取 `llms.txt` 定位相关 Markdown 正文并引用来源；证据不足或不可访问时回退 `wiki-search`。用户明确指定的来源优先。

使用 `codex plugin add aikg-search@lingqulab` 安装，调用 `$aikg-search` 或直接提出 AI 基础设施问题。见 [skill 正文](skills/aikg-search/SKILL.md)。可选回退插件为 `wiki-search@lingqulab` 和 `cross-zone-development@lingqulab`，WIKI 命令仅在绿区执行。

依赖和影响：使用可用的网页读取工具，或 Git 与 `rg` 检索本地 Markdown。已有 checkout 可离线只读检索；可选浅克隆仅写临时目录。不需要也不附带 MkDocs 服务、上游自动路由器、Python 包、Hooks 或 MCP 服务。公开检索访问 GitHub 或 GitHub Pages，不向其发送内部 WIKI 资料。绿区回退使用单独配置的 HAPI Bridge 和已认证的 wiki-cli。

本插件以 MIT 许可发布，仅包含 harness 编写的检索指导，不内置上游正文或代码。上游文档为 CC-BY-4.0，代码与配置为 MIT，使用其内容时保留来源署名。集成时核对的上游提交为 `f4a42b37e4b9c13e829d9ac9800a26684db7de2d`；实际检索使用当前来源或注明本地快照。见 [上游许可](https://github.com/AmourSec/aikg/blob/master/LICENSE)。
