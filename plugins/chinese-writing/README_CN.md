# 中文技术表述

[English](README.md)

撰写或检查中文技术文档、代码注释、PR 说明和回复。根据实际实现写清具体动作，保留 `communicator`、`opaque handle` 等英文术语和标识符。

## 使用方式

运行 `codex plugin add chinese-writing@lingqulab` 安装插件。新建 Codex 任务后，可以直接请它检查中文草稿，也可以显式调用 `$chinese-writing`。

[Skill 说明](skills/chinese-writing/SKILL.md)提供扫描 UTF-8 文件和标准输入的命令。脚本用 Python 3 读取本地[词汇黑名单](skills/chinese-writing/references/blacklist.json)，打印每处命中的位置和改写提示。扫描无需联网，也不会修改草稿。插件无 Hook 或 MCP。

采用 [MIT 许可证](../../LICENSE)。
