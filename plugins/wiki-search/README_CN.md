# WIKI 搜索

[English documentation](README.md)

按关键词、标题或正文查找华为 WIKI 文档。支持全平台、知识库、类目，以及某个文档及其子文档范围，返回相关文档链接和简短匹配摘要。

## 使用方式

使用 `codex plugin add wiki-search@lingqulab` 安装，然后要求搜索华为 WIKI，或调用 `$wiki-search`。限定知识库、类目或文档子树时，提供相应文档链接。提供本地 WIKI 资料库时会优先检索本地内容。

一般知识问题先使用 `aikg-search`；明确要求 WIKI 时直接使用本插件。参数与示例见[搜索指南](skills/wiki-search/SKILL.md)。

## 依赖与访问范围

在线搜索需要 `cross-zone-development@lingqulab`、已连接的绿区 Bridge，以及在绿区安装并认证的 `wiki-cli`（`wiki auth status` 返回 `✓ 已认证`）。智能体在绿区核对认证并运行 `wiki doc search`。本地资料库检索需要 `rg` 等文本搜索工具，无需 WIKI 认证。

在线查询通过 CLI 向华为 WIKI 发送关键词和参考 URL。本地查询在资料库所在区读取内容。受保护结果通过跨区审查后回传，原始响应和完整正文留在绿区。搜索不修改文档，凭据和缓存由 wiki-cli 管理。无 Hooks 或 MCP；跨区执行使用单独配置的 HAPI Bridge。

插件采用 MIT 许可证，CLI 和华为服务需另行提供。
