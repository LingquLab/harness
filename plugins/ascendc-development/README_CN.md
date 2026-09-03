# Ascend C Development

[English](./README.md)

这是一个兼容 ZCode 与 Codex 的插件，提供版本匹配的 Ascend C 算子实现、API 检索、代码审查、环境检查、NPU 状态、CANN 配置和运行时调试工作流。

## 使用方式

可以直接让智能体开发或迁移算子、核对 Ascend C API、审查 Host/Tiling/Kernel 代码、检查 Ascend 环境、查看 NPU 占用、安装或修复 CANN，或诊断运行时故障。八个聚焦的 skill 会根据请求独立触发。

## 依赖与行为

- 网络：文档检索可能访问华为官方文档和公开 GitCode 内容；用户指定远程主机时，环境与 NPU 检查可能使用 SSH。
- 命令：根据任务调用本地构建、测试、CANN、NPU、Git、Python、Ruby、curl 或 SSH 命令。
- 文件：开发与环境配置工作流可能修改当前代码仓或用户明确选择的环境；代码审查、文档检索、状态和环境盘点默认只读。
- 服务：完整运行验证需要兼容的昇腾设备、驱动、固件、CANN 工具包和算子包。
- Hook 与 MCP：无。

部分 skill 改编自 TileXR 材料，来源见仓库 `THIRD_PARTY_NOTICES.md`；本插件按随附的 CANN Open Software License Agreement Version 2.0 分发。
