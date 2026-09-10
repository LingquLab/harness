# Archify

[English](./README.md)

这是一个兼容 ZCode 与 Codex 的插件，可将代码仓库或系统描述转换为经过验证、可交互的架构图、工作流图、时序图、数据流图和生命周期图。输出为包含内联 SVG 的独立 HTML，并支持静态图片和 WebM 导出。

## 使用方式

让智能体使用 Archify，并描述所需系统或图表即可。例如：`使用 Archify 绘制 Browser -> API -> Redis -> PostgreSQL。` 当图表必须反映真实代码时，该 skill 可以检查仓库证据。

## 依赖与行为

- 运行时：Node.js 18 或更高版本。
- 网络：随包提供的更新检查器可能读取 Archify 固定的稳定版更新清单；设置 `ARCHIFY_UPDATE_CHECK_DISABLED=1` 可禁用。图表生成本身在本地完成。
- 命令：调用 vendored Node.js 渲染、验证、预览与导出工具。
- 文件：写入用户请求的 JSON 规格以及生成的 HTML 或导出制品。预览模式会启动仅监听 loopback 的本地服务。
- Hook 与 MCP：无。

上游发布包与固定提交记录在 [VENDORED.md](./VENDORED.md)。Archify 采用 MIT 许可证；随包提供的品牌标志与字体仍遵循 [`skills/archify/THIRD_PARTY_NOTICES.md`](./skills/archify/THIRD_PARTY_NOTICES.md) 中记录的条款。
