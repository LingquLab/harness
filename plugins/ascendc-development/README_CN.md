# Ascend C Development

[English](./README.md)

这是一个兼容 Codex 的插件，提供版本匹配的 Ascend C 算子实现、API 检索、代码审查、环境检查、NPU 状态、CANN 配置和运行时调试工作流。

## 使用方式

可以直接让智能体开发或迁移算子、核对 Ascend C API、审查 Host/Tiling/Kernel 代码、检查 Ascend 环境、查看 NPU 占用、安装或修复 CANN，或诊断运行时故障。八个聚焦的 skill 会根据请求独立触发。

## Skills

| Skill | 适用场景 |
|---|---|
| `ascendc-api-best-practices` | 核对 Ascend C API、对齐、缓冲区、精度与流水使用 |
| `ascendc-code-review` | 审查 Host、Tiling、Kernel、SIMT 与构建改动 |
| `ascendc-docs-search` | 检索版本匹配的本地及官方文档和示例 |
| `ascendc-env-check` | 检查 CANN 环境、工具和 NPU 可见性 |
| `ascendc-npu-status` | 查看指定设备的进程占用情况 |
| `ascendc-operator-development` | 开发或迁移完整算子并分层验证 |
| `ascendc-runtime-debug` | 诊断运行时、Tiling、设备异常、精度与性能问题 |
| `cann-env-setup` | 安装、配置或修复版本匹配的 CANN 环境 |

## 依赖与行为

- 网络：文档检索可能访问华为官方文档和公开 GitCode 内容；用户指定远程主机时，环境与 NPU 检查可能使用 SSH。
- 命令：根据任务调用本地构建、测试、CANN、NPU、Git、Python、Ruby、curl 或 SSH 命令。
- 文件：开发与环境配置工作流可能修改当前代码仓或用户明确选择的环境；代码审查、文档检索、状态和环境盘点默认只读。
- 服务：完整运行验证需要兼容的昇腾设备、驱动、固件、CANN 工具包和算子包。
- Hook 与 MCP：无。

本插件按随附的 [CANN Open Software License Agreement Version 2.0](LICENSE) 分发，来源署名见[第三方说明](../../THIRD_PARTY_NOTICES.md)。
