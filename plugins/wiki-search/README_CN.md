# WIKI 搜索

[English documentation](./README.md)

使用 `wiki-cli` 搜索华为 WIKI。用户提供本地资料库时，先全文检索其中的 `_index.md`，没有相关结果再在线搜索。

使用 `codex plugin add wiki-search@lingqulab` 安装，然后要求搜索华为 WIKI，或调用 `$wiki-search`。范围、参数、示例和结果处理见 [skill 正文](skills/wiki-search/SKILL.md)。

依赖：安装 `cross-zone-development@lingqulab`，按其流程建立 HAPI 连接（OPEN/READY 或有效绿区 OPEN）。线上命令仅通过有界 EXEC 在绿区执行，TASK 需用户明确要求。在绿区单独安装 `wiki-cli`；线上搜索要求 `wiki auth status` 返回 `✓ 已认证`。插件不安装 CLI，也不代为认证。本地检索需要 `rg` 等文本搜索工具，无需网络或认证。

命令包括 `wiki auth status`、`wiki doc search`，必要时使用 `wiki doc search --help`。在线搜索通过 CLI 向华为 WIKI 发送关键词和参考 URL，需要能够访问该服务。本地检索在资料库所在区读取用户指定的资料库。受保护响应通过跨区 AI 审查后回传，原始搜索 JSON 和完整正文留在绿区。skill 不要求写入文档或创建本地文件；凭据和缓存行为由单独安装的 CLI 管理。不附带 Hooks、MCP 服务或后台服务；跨区执行使用单独配置的 HAPI Bridge。

本指导来自用户提供的 wiki-cli 搜索说明，包括本机 `wiki-doc.md` 的 search 参考。不附带 CLI 或华为服务。本插件按仓库的 MIT 许可证分发。
