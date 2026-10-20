# Cross Zone Development

[English](./README.md)

这个 Codex 与 ZCode 插件通过 HAPI 协调蓝区和绿区 AI。绿区 Windows Bridge
调用本地 Claude Code 兼容 CLI，只向蓝区返回经过审查的有界结果。传输不再使用
GitHub Issue，也不需要操作浏览器。

## 绿区运行时安装

插件已经包含 Python Bridge [`cross_zone`](cross_zone)、Git Bash 启动脚本
[`start-bridge.sh`](start-bridge.sh)、配置模板和离线运行时测试。绿区 Windows 主机需安装
Python 3.11+、Git for Windows 和 CodeAgentCLI，然后把整个插件目录复制到批准的本地
位置；Bridge 不依赖第三方 Python 包。

把 [config.windows.json](config.windows.json) 复制为已忽略的 `config.local.json`，填写
`hub_url` 和 `access_key`。从绿区授权作为任务 workspace 的目录启动：

```bash
<plugin-dir>/start-bridge.sh doctor <session-id>
<plugin-dir>/start-bridge.sh open <session-id>
```

恢复已有监听且不需要再次发送 OPEN 时可用 `run`。首次 `run` 会绑定当前消息游标并
跳过历史 TASK，因此应在蓝区下发任务前启动。启动脚本写入
`<plugin-dir>/.cac/bridge-<command>-<session-id>.log`；其中可以显示有长度限制的 Agent 流式输出，
但该内容只保留在绿区。状态和任务专属 detached checkout 位于配置文件目录下的
`.state/<session-id>/`。

## 绿区主动开启协同

使用插件内置的 v0.4 绿区运行时及不受 Git 跟踪的 `config.local.json`。

配置中不再包含仓库路径、仓库别名、Git remote 或 task binding。启动命令所在目录就是
workspace。配置中也不包含 profile、allowed tools 或自定义出区正则，不保存 session ID、session URL 或 state directory。`config.local.json`
含 HAPI access key，只能保存在绿区本机且不得提交。
旧配置中已经删除的字段会被直接忽略，不能覆盖命令行 session、启动 workspace 或本地
workspace。

在绿区授权的任务 workspace 中执行：

```bash
<plugin-dir>/start-bridge.sh open <session-id>
```

Bridge 先检查启动 workspace、CLI 和状态目录；检查通过后先绑定消息游标，再以 user
消息发送一次绿区来源的 OPEN，并监听该会话，等待
TASK/ANSWER/CANCEL。收到有效 OPEN 即按蓝区处理，无需确认角色。
蓝区确认 OPEN 指向当前授权会话后，发送正式 TASK 开始协同；
若不接受，则仅用普通对话说明原因。蓝区不得注入、回显或返回 OPEN 协议消息。

蓝区完成并检查候选修改后，先提交并把任务分支推送到批准的 GitHub 仓库，再发送
TASK。如果启动 workspace 是 Git 仓库，绿区通过其现有 `origin` 拉取 TASK 指定的完整 revision，在隔离、
干净的 checkout 中测试。HAPI 只传递协同消息和审查后的结果，包括允许的短诊断代码片段；绿区不推送
诊断修改。

`revision` 是可选字段。候选代码验证按上述流程携带 revision；查询时间、CPU/NPU
状态、服务健康度或其他绿区环境检查不携带 revision，Bridge 会跳过
Git fetch 和 checkout，直接在 `.state/<session-id>` 中执行。

不需要绿区主动开启时，运行 `./start-bridge.sh run <session-id>`。每个会话自动使用
`.state/<session-id>/` 和独立日志，因此同一配置可服务多个并发会话。跨平台示例见
[config.example.json](config.example.json)。

在插件目录运行以下命令执行 Bridge 回归测试：

```bash
python -m unittest discover -s tests -v
```

Agent 故障会返回明确且安全的原因：`agent_executable_not_found` 表示
`agent_command[0]` 不存在或不在 PATH；`agent_executable_not_runnable` 表示文件不能
执行；`agent_exit_nonzero` 表示 CLI 非零退出；`agent_output_protocol_error` 表示 CLI
没有返回要求的 stream-json 结构化结果。绿区本地 Bridge 日志会记录异常类型、有长度
限制的详情、退出码和对应修复建议。

TASK 超时不得低于 600 秒。普通代码验证建议使用 900 秒；即使是较小的环境检查也应
使用 600 秒，因为绿区 CLI 初始化和执行可能超过 5 分钟。

## 协议边界

TASK/ANSWER/CANCEL 与 ACK/PROGRESS/QUESTION/RESULT/REJECTED 保持 v2 既有语义。
ACK/PROGRESS 仅保留类型、任务 ID 和轮次；即时启动时合并为 PROGRESS，兼容旧格式。
TASK 不携带仓库/profile 别名。
结果必须绑定准确的任务、iteration 和 target；TASK 提供 revision 时还必须绑定该
不可变 revision。RESULT 必须包含全部 requested checks；代码验证的 PASS 还要求所有
检查在干净且未修改的基线上通过。依赖或权限不足返回
BLOCKED；信息不足发送 QUESTION，最多 3 次。绿区完成出区审查后才能设置
`egress_reviewed=true`，不得返回凭据、个人或客户数据、请求/响应正文、大批量日志、
完整源文件、diff、patch，以及达到 10 行的代码或伪代码片段。允许返回相关的
Markdown 围栏、URL、内网地址、绝对路径、完整堆栈，以及少于 10 行的代码或可重建
实现的伪代码。整个结构化结果最多 4096 字节，`summary` 最多 3000 个字符。

本插件为 LingquLab 原创内容，采用仓库中的 MIT 许可证。
