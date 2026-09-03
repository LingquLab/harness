# Superpowers Neo

[English](./README.md)

这是一个兼容 ZCode 与 Codex 的模块化软件开发工作流插件，会根据任务复杂度调整严谨程度。所含 skill 覆盖设计、计划、隔离 worktree、计划执行、验证、调试、简化、审查、完成确认和 Git 交付。

## 使用方式

正常描述开发任务即可。每个 skill 都可独立发现，只在对应工作流适用时触发；插件没有强制启动或总入口 skill。

## 依赖与行为

- 网络：用户要求交付时，Git 工作流可能访问已配置的远端仓库和代码托管 API。
- 命令：工作流可能执行仓库构建、测试、格式化、Git 和代码托管 CLI 命令。
- 文件：实现工作流可能修改当前代码仓；worktree 与 Git 交付工作流可在对应 skill 的授权范围内创建任务分支、提交、worktree、推送和 Pull Request。
- 服务：除仓库自身工具链及交付所需的 Git 托管服务外，无额外服务依赖。
- Hook 与 MCP：无。

本插件是受 Jesse Vincent 的 Superpowers 启发的独立改编，并包含其他已注明来源的材料。详情见仓库 `THIRD_PARTY_NOTICES.md`；插件采用 MIT 许可证。
