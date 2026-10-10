# Cross Zone Development

[English](./README.md)

这个 Codex 与 ZCode 插件通过 HAPI 协调蓝区和绿区 AI。绿区 Windows Bridge
调用本地 Claude Code 兼容 CLI，只向蓝区返回经过审查的有界结果。传输不再使用
GitHub Issue，也不需要操作浏览器。

## 绿区主动开启协同

使用 v0.3 绿区运行时。将 [config.windows.json](config.windows.json) 复制为不受 Git
跟踪的 `config.local.json`，配置 HAPI Hub、access key 和绿区仓库/权限别名。

`task_binding` 完全在绿区内部选择仓库和权限 profile，蓝区不提供也不需要知道这些
别名。配置中不保存 session ID、session URL 或 state directory。`config.local.json`
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
TASK。绿区通过本地仓库绑定中的 `remote` 拉取 TASK 指定的完整 revision，在隔离、
干净的 checkout 中测试。HAPI 只传递协同消息和审查后的结果，不传代码；绿区不推送
诊断修改。

不需要绿区主动开启时，运行 `./start-bridge.sh run <session-id>`。每个会话自动使用
`.state/<session-id>/` 和独立日志，因此同一配置可服务多个并发会话。跨平台示例见
[config.example.json](config.example.json)。

## 协议边界

TASK/ANSWER/CANCEL 与 ACK/PROGRESS/QUESTION/RESULT/REJECTED 保持 v2 既有语义。
新 TASK 不携带仓库/profile 别名；v0.3 绿区运行时仅在本地授权范围内兼容旧版
带别名 TASK。
结果必须绑定准确的任务、iteration、target 和不可变 revision。RESULT 必须包含全部
requested checks；PASS 要求所有检查在干净且未修改的基线上通过。依赖或权限不足返回
BLOCKED；信息不足发送 QUESTION，最多 3 次。绿区完成出区审查后才能设置
`egress_reviewed=true`，不得返回源码、原始日志、凭据、内网地址、绝对路径、载荷或
包含源码的制品。

本插件为 LingquLab 原创内容，采用仓库中的 MIT 许可证。
