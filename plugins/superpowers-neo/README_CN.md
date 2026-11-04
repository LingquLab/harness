# Superpowers Neo

[English](./README.md)

这是一个兼容 ZCode 与 Codex 的模块化软件开发工作流插件，会根据任务复杂度调整严谨程度。所含 skill 覆盖设计、计划、隔离 worktree、计划执行、验证、调试、简化、审查、完成确认和 Git 交付。

## 使用方式

正常描述开发任务即可。每个 skill 都可独立发现，只在对应工作流适用时触发；插件没有强制启动或总入口 skill。

## 范围与测试交付

禁止过度设计，只实现完整满足用户需求的最小方案。未经要求的功能、假设风险下的保护机制、文件锁或额外测试框架，必须先说明必要性和代价，等待用户明确确认后再开发。需求范围内的常规实现选择不需要重复确认。

禁止过度防御编程：保留真实边界校验，让必要失败明确暴露，优先复用已有实现，并测试用户依赖的行为；不为假设状态层层加防御，也不静默切换执行路径。

开发中按风险做必要验证；上库只保留验证核心行为、关键契约或重大具体回归的测试。提交前删除本次创建的非核心测试代码、一次性探针、调试脚本、临时框架及生成物。保留原有测试、用户文件，以及用户明确要求交付的测试代码或框架。

## Skills

| Skill | 适用场景 |
|---|---|
| `superpowers-neo-designing-complex-changes` | 设计复杂、跨模块或有关键歧义的变更 |
| `superpowers-neo-writing-plans` | 为多步骤工作制定可执行计划 |
| `superpowers-neo-using-git-worktrees` | 按需隔离工作区，保护现有改动 |
| `superpowers-neo-executing-plans` | 执行计划并协调相互依赖的步骤 |
| `superpowers-neo-validation-strategy` | 按风险选择必要的验证方式 |
| `superpowers-neo-systematic-debugging` | 用可复现证据定位故障原因 |
| `superpowers-neo-code-simplification` | 简化代码并检查面向用户的文档 |
| `superpowers-neo-requesting-code-review` | 为重要改动安排适当的独立审查 |
| `superpowers-neo-handling-code-review-feedback` | 核实并处理审查意见 |
| `superpowers-neo-verification-before-completion` | 确认完成结论有当前验证证据 |
| `superpowers-neo-git-delivery` | 按授权完成提交、推送与 PR 交付 |

## 用户文档

README 和产品指南介绍能力、适用任务、安装及使用方式。来源历史和内部实现细节放在链接可达的维护或署名文档中。文档和代码注释中的技术术语优先保留英文，例如 `token`、`opaque handle`；中文应解释实际行为，避免逐词翻译和“协调资源”等含糊表达。动作、所有权和清理顺序必须与代码一致。

## 依赖与行为

- 网络：用户要求交付时，Git 工作流可能访问已配置的远端仓库和代码托管 API。
- 命令：工作流可能执行仓库构建、测试、格式化、Git 和代码托管 CLI 命令。
- 文件：实现工作流可能修改当前代码仓；worktree 与 Git 交付工作流可在对应 skill 的授权范围内创建任务分支、提交、worktree、推送和 Pull Request。
- 服务：除仓库自身工具链及交付所需的 Git 托管服务外，无额外服务依赖。
- Hook 与 MCP：无。

本插件采用 MIT 许可证，来源署名见[第三方说明](../../THIRD_PARTY_NOTICES.md)。
