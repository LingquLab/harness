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
`hub_url`、`access_key` 和单一执行 profile。从绿区授权作为任务 workspace 的目录启动：

```bash
<plugin-dir>/start-bridge.sh doctor <session-id>
<plugin-dir>/start-bridge.sh open <session-id>
```

蓝区已经开始派发任务时可用 `run` 代替 `open`。启动脚本写入
`.cac/bridge-<command>-<session-id>.log`；其中可以显示有长度限制的 Agent 流式输出，
但该内容只保留在绿区。状态和任务专属 detached checkout 位于
`.state/<session-id>/`。

## 绿区主动开启协同

使用插件内置的 v0.4 绿区运行时及不受 Git 跟踪的 `config.local.json`。

配置中不再包含仓库路径、仓库别名、Git remote 或 task binding。启动命令所在目录就是
workspace，单一 `profile` 定义本地权限。配置中不保存 session ID、session URL 或 state directory。`config.local.json`
含 HAPI access key，只能保存在绿区本机且不得提交。

在绿区 Windows 运行时目录执行：

```bash
./start-bridge.sh open <session-id>
```

Bridge 先检查本地 task binding、CLI 和目录；检查通过后才以 user 消息发送一次绿区
来源的 OPEN，然后绑定并监听该会话，等待
TASK/ANSWER/CANCEL。蓝区确认 OPEN 指向当前授权会话后，发送正式 TASK 开始协同；
若不接受，则仅用普通对话说明原因。蓝区不得注入、回显或返回 OPEN 协议消息。

蓝区完成并检查候选修改后，先提交并把任务分支推送到批准的 GitHub 仓库，再发送
TASK。如果启动 workspace 是 Git 仓库，绿区通过其现有 `origin` 拉取 TASK 指定的完整 revision，在隔离、
干净的 checkout 中测试。HAPI 只传递协同消息和审查后的结果，不传代码；绿区不推送
诊断修改。

`revision` 是可选字段。候选代码验证按上述流程携带 revision；查询时间、CPU/NPU
状态、服务健康度或其他 profile 已授权的绿区环境检查不携带 revision，Bridge 会跳过
Git fetch 和 checkout，直接在启动 workspace 中执行。

不需要绿区主动开启时，运行 `./start-bridge.sh run <session-id>`。每个会话自动使用
`.state/<session-id>/` 和独立日志，因此同一配置可服务多个并发会话。跨平台示例见
[config.example.json](config.example.json)。

在插件目录运行以下命令执行 Bridge 回归测试：

```bash
python -m unittest discover -s tests -v
```

## 协议边界

TASK/ANSWER/CANCEL 与 ACK/PROGRESS/QUESTION/RESULT/REJECTED 保持 v2 既有语义。
TASK 不携带仓库/profile 别名。
结果必须绑定准确的任务、iteration 和 target；TASK 提供 revision 时还必须绑定该
不可变 revision。RESULT 必须包含全部 requested checks；代码验证的 PASS 还要求所有
检查在干净且未修改的基线上通过。依赖或权限不足返回
BLOCKED；信息不足发送 QUESTION，最多 3 次。绿区完成出区审查后才能设置
`egress_reviewed=true`，不得返回源码、原始日志、凭据、内网地址、绝对路径、载荷或
包含源码的制品。

本插件为 LingquLab 原创内容，采用仓库中的 MIT 许可证。
