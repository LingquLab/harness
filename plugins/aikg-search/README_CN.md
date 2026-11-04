# AIKG 知识搜索

[English documentation](README.md)

从公开的 [AI Knowledge Graph](https://github.com/AmourSec/aikg) 查找知识解释和参考资料，覆盖 AI 基础、推理与训练系统、GPU/NPU 架构、Ascend/CANN、算子、编译器和性能分析。

## 使用方式

使用 `codex plugin add aikg-search@lingqulab` 安装，然后直接提问，例如“解释 KV Cache 的显存占用”，或调用 `$aikg-search`。回答基于相关文档证据，并附来源链接。也可以提供本地 AIKG checkout 进行离线检索。

一般知识查询优先检索 AIKG。需要补充证据时，可继续使用 `wiki-search@lingqulab`；在线 WIKI 检索还需要 `cross-zone-development@lingqulab` 和已配置的绿区环境。你可以明确限定查询来源。

## 依赖与访问范围

公开检索使用可用的网页读取工具，或通过 Git 和 `rg` 检索本地 Markdown。网络访问目标为 GitHub 或 GitHub Pages，不向其发送内部 WIKI 资料。已有 checkout 只读访问，可选浅克隆会写临时目录。不需要启动网站服务。无 Hooks 或 MCP。

插件采用 MIT 许可证。AIKG 文档采用 CC-BY-4.0，使用时应保留来源署名。详见[第三方说明](../../THIRD_PARTY_NOTICES.md)和[上游条款](https://github.com/AmourSec/aikg/blob/master/LICENSE)。
