# Cross Zone Development

[English](./README.md)

这个 Codex 与 ZCode 插件通过 HAPI 协调蓝区和绿区 AI。绿区 Windows Bridge
调用本地 Claude Code 兼容 CLI，只向蓝区返回经过审查的有界结果。传输不再使用
GitHub Issue，也不需要操作浏览器。

## 绿区主动开启协同

使用 v0.2.2 绿区运行时。将 [config.windows.json](config.windows.json) 复制为
`config.local.json`，配置 HAPI Hub、绿区仓库/权限别名，并填写：

```json
"session_url": "sessions/<蓝区会话 ID>"
```

`task_binding` 完全在绿区内部选择仓库和权限 profile，蓝区不提供也不需要知道这些
别名。`session_url` 只是会话引用，不是完整网址；不得包含主机名、凭据、查询参数或
fragment。HAPI key 保存在配置文件之外，通过指定环境变量或运行时隐藏输入提供。

在绿区 Windows 运行时目录执行：

```powershell
.\Start-Bridge.ps1 -Command open
```

Bridge 先检查本地 task binding、CLI 和目录；检查通过后才以 user 消息发送一次绿区
来源的 OPEN，然后绑定并监听该会话，等待
TASK/ANSWER/CANCEL。蓝区确认 OPEN 指向当前授权会话后，发送正式 TASK 开始协同；
若不接受，则仅用普通对话说明原因。蓝区不得注入、回显或返回 OPEN 协议消息。

蓝区完成并检查候选修改后，先提交并把任务分支推送到批准的 GitHub 仓库，再发送
TASK。绿区通过本地仓库绑定中的 `remote` 拉取 TASK 指定的完整 revision，在隔离、
干净的 checkout 中测试。HAPI 只传递协同消息和审查后的结果，不传代码；绿区不推送
诊断修改。

不需要绿区主动开启时，可以移除 `session_url`，继续使用运行时既有的 bind/run
流程。跨平台示例见 [config.example.json](config.example.json)。

## 协议边界

TASK/ANSWER/CANCEL 与 ACK/PROGRESS/QUESTION/RESULT/REJECTED 保持 v2 既有语义。
新 TASK 不携带仓库/profile 别名；v0.2.2 绿区运行时仅在本地授权范围内兼容旧版
带别名 TASK。
结果必须绑定准确的任务、iteration、target 和不可变 revision。RESULT 必须包含全部
requested checks；PASS 要求所有检查在干净且未修改的基线上通过。依赖或权限不足返回
BLOCKED；信息不足发送 QUESTION，最多 3 次。绿区完成出区审查后才能设置
`egress_reviewed=true`，不得返回源码、原始日志、凭据、内网地址、绝对路径、载荷或
包含源码的制品。

本插件为 LingquLab 原创内容，采用仓库中的 MIT 许可证。
