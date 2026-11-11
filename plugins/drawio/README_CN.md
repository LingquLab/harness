# draw.io

[English](README.md)

将文字描述、Mermaid 或 draw.io XML 生成为可编辑的 `.drawio` 图表。
可选导出内嵌图表 XML 的 PNG、SVG、PDF，或生成浏览器编辑链接。

## 安装和使用

在 ZCode 中添加 `LingquLab/harness` 插件市场，安装 `drawio`。Codex 用户运行：

```bash
codex plugin marketplace add LingquLab/harness
codex plugin add drawio@lingqulab
```

开启新任务后，可以说：“用 drawio 把登录流程画成可编辑的 .drawio 文件”，
或“用 drawio 将这张架构图导出为 SVG”。需要交互式 HTML 图表时，明确选择 `archify`。

## 依赖与访问

- 直接编写 XML `.drawio` 文件无需安装 draw.io，也无需配置 MCP。
- Mermaid 转换、ELK 布局及 PNG/SVG/PDF 导出需要 draw.io Desktop 和其 CLI。
  Linux 无显示环境可能还需要 Xvfb。没有 Desktop 时，使用 XML `.drawio` 文件或浏览器链接。
- 内置形状搜索需要 Node.js 18+ 和网络；压缩浏览器链接也使用 Node.js。
  参考文档来自 GitHub，形状索引来自 jsDelivr，图标来自 `icons.diagrams.net`。
  图标搜索会向该服务发送形状查询词。浏览器链接包含图表内容并打开 `app.diagrams.net`。
- 技能会写入图表和临时源文件、运行 shell 命令，并可能打开 draw.io 或默认浏览器。
  导出流程在生成可编辑的导出文件后会删除中间 `.drawio` 源文件。
- 插件不配置 Hooks、MCP server、账号或凭据。

采用 [Apache-2.0 许可](LICENSE)。上游来源及市场适配见[来源记录](VENDORED.md)。
