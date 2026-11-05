# 跨区开发协作

[English](README.md)

在蓝区继续开发的同时，将检查交给受保护的绿区环境执行。插件通过 HAPI 连接两区，执行有明确范围的命令，并按跨区输出规则返回结果。适用于服务诊断、环境检查和候选代码验证。

## 开始使用

使用 `codex plugin add cross-zone-development@lingqulab` 安装。绿区准备 Windows、Python 3.11+、Git for Windows 和 CodeAgentCLI，将插件复制到批准的本地位置。把 `config.windows.json` 复制为 `config.local.json`，配置 HAPI 访问密钥；不要公开或提交此文件。

从绿区授权的任务工作目录启动 Bridge：

```bash
<plugin-dir>/start-bridge.sh
```

然后让蓝区智能体连接并执行所需检查。多会话场景可以启动独立显式 worker。默认 worker 忙碌时，强制接管会中断原有任务，需要先确认。

安装与日常使用见[中文用户指南](USER_GUIDE_CN.md)。配置、超时、日志、升级与恢复见[操作参考](OPERATIONS_CN.md)，消息格式见[协议参考](skills/cross-zone-development/references/protocol.md)。

## 依赖与影响

Bridge 访问配置的 HAPI Hub，启用输出审查时还会访问配置的推理接口。命令在授权的绿区工作目录执行，可访问任务指定的服务。本地配置、执行记录和日志留在绿区。候选验证可创建隔离 checkout，其他文件影响取决于下发命令。中断后不会自动重跑命令，影响未知时需先做恢复检查。

需要运行本地 Bridge 进程，不附带 Hooks 或 MCP 服务。插件采用 MIT 许可证。

## 审查失败后的直接恢复

review/fallback 已终结为 NEEDS_HUMAN 时，蓝区发送新的 EXEC，显式设置
`ai_review: false` 并缩减输出。只读或已确认可重复的命令可重试一次；有副作用的
操作改用只读命令读取已保存证据，不重复原操作。仅改 flag 无法修复超限。
当前会话累计两次此类失败后，后续 EXEC 均使用 direct 模式，除非用户要求恢复审查。
不重复相同失败命令，不绕过有效的否定审查结论，也不重跑执行状态或副作用未知的操作。
输出上限按下方 64 KiB 策略执行，凭据和内容检查继续生效。

## 64 KiB 正式回传策略（0.7.2）

直接 EXEC stdout 上限为 65536 UTF-8 字节（64 KiB）；完整 RESULT JSON 上限
73728 字节（72 KiB），为协议元数据预留空间；summary 上限为 65664 字符，
包含 direct/fallback 模式标签。JSON 转义、多字节文本仍可能先触及整包上限，须缩减或
分段输出，不重复发送超限结果。诊断 detail 维持 4000 JSON 编码 UTF-8 字节。
凭据与内容检查、本地捕获和审查限制、HAPI 客户端行为保持原样。

绿区已收到 8 KiB、64 KiB 合成负载；256 KiB RESULT 投递返回 HTTP 403，
未确认具体原因。本正式版采用已观察到的 64 KiB 档位，结束无上限实验。
