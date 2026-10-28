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
`access_key`。模板默认 `hub_url` 为 `https://su.kurox.cn/hapi/`，使用其他 Hub 时
在本地修改；Windows 模板默认以 `--effort low` 启动 CodeAgent。
从绿区授权作为任务 workspace 的目录启动：

```bash
<plugin-dir>/start-bridge.sh doctor <session-id>
<plugin-dir>/start-bridge.sh open <session-id>
```

需要 Bridge 退出后自动重新拉起时，在单独的 Git Bash 窗口运行：

```bash
<plugin-dir>/watch-bridge.sh <session-id> [config-file]
```

守护脚本每次退出后等待 3 秒，再执行 `start-bridge.sh open`；可用
`BRIDGE_RESTART_DELAY` 调整间隔，`Ctrl+C` 停止守护循环。先更新磁盘代码，
再结束 Bridge 进程，下一次启动即加载新版。实例锁继续生效；中断任务不会重跑。
后续 AI 先核查遗留进程和已完成操作，状态未知时只做只读检查，无需人工解锁。

0.5.1 使用 `CROSS_ZONE` 标记及 `cross-zone/v3` 协议，所有消息删除 `target`，
仅按当前 HAPI 会话绑定。OPEN 的 `version` 报告实际运行的 Bridge 版本。

新增 `EXEC`：蓝区提供命令参数数组，或 Bash/PowerShell/Python 脚本，Bridge
在 session 目录原样执行，默认再由绿区 AI 仅过滤已保存的输出并回传。退出码、超时和
取消状态由 Bridge 保留，AI 不能把执行失败变成 PASS；原始日志只留绿区，中断不重跑。
字段与示例见[协议](skills/cross-zone-development/references/protocol.md#direct-commands-and-scripts-exec)。

恢复已有监听且不需要再次发送 OPEN 时可用 `run`。首次 `run` 会绑定当前消息游标并
跳过历史 TASK，因此应在蓝区下发任务前启动。启动脚本写入
`<plugin-dir>/.cac/bridge-<command>-<session-id>.log`；其中可以显示有长度限制的 Agent 流式输出，
但该内容只保留在绿区。状态和任务专属 detached checkout 位于配置文件目录下的
`.state/<session-id>/`。

## 绿区主动开启协同

使用插件内置的 v0.5 绿区运行时及不受 Git 跟踪的 `config.local.json`。

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
TASK/EXEC/ANSWER/CANCEL。收到有效 OPEN 即按蓝区处理，无需确认角色。
蓝区确认 OPEN 指向当前授权会话后，按全新连接处理：若上下文已有明确授权、
尚未完成且下一步已就绪的绿区工作，就直接下发，不要求用户重复指令；否则回复就绪并等待。
OPEN 本身不增加任务授权，不重放已完成或仍在运行的动作；先前执行效果不明时，仍须
先核查状态。Bridge 不自动恢复本地旧队列。用户请求执行工作时默认使用
EXEC；需要绿区判断、指定 revision 的验证或必要恢复时才使用 TASK。
历史记录和恢复保护仍然保留；`ai_review` 默认 false，可能返回受限信息时由蓝区显式设置 true。
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

TASK/EXEC/ANSWER/CANCEL 与 ACK/PROGRESS/QUESTION/RESULT/REJECTED 使用 v3 会话绑定语义。
ACK/PROGRESS 仅保留类型、任务 ID 和轮次；即时启动时合并为 PROGRESS。
消息在协议标记后使用缩进 JSON 代码块，兼容旧版单行 JSON 和完整通知。
TASK 不携带仓库/profile 别名。
结果必须绑定准确的任务、iteration 和当前 HAPI 会话；TASK 提供 revision 时还必须绑定该
不可变 revision。RESULT 必须包含全部 requested checks；代码验证的 PASS 还要求所有
检查在干净且未修改的基线上通过。依赖或权限不足返回
BLOCKED；Agent 故障会附带脱敏、限长的诊断详情。信息不足发送 QUESTION，最多 3 次。绿区完成出区审查后才能设置
`egress_reviewed=true`，不得返回凭据、个人或客户数据、请求/响应正文、大批量日志、
完整源文件、diff、patch，以及达到 10 行的代码或伪代码片段。允许返回相关的
Markdown 围栏、URL、内网地址、绝对路径、完整堆栈，以及少于 10 行的代码或可重建
实现的伪代码。整个结构化结果最多 4096 字节，`summary` 最多 3000 个字符。

本插件为 LingquLab 原创内容，采用仓库中的 MIT 许可证。

### 通过推理接口审查 EXEC

`ai_review=true` 使用一次 OpenAI 兼容 Chat Completions 请求，不再启动 CodeAgent，
模型也没有工具调用能力。在已忽略的 `config.local.json` 中填写：

```json
"exec_review": {
  "base_url": "http://techdev.hicomputing.huawei.com:18000/v1",
  "model": "Qwen3.8",
  "api_key": "REPLACE_WITH_REVIEW_API_KEY",
  "timeout_seconds": 300
}
```

审查默认超时为 300 秒，同时受总任务剩余时间限制。已有本地配置显式填写 60 秒时，
仍使用该值；请将 `exec_review.timeout_seconds` 改为 300，或删除该字段使用新默认值，
然后重启 Bridge。带审查 EXEC 的总任务时限需覆盖命令时限和配置的审查预算。

真实密钥只在本地替换占位符，不提交到仓库；已有本地配置需要补充该节。
`base_url` 是 API 前缀，Bridge 在后面追加 `/chat/completions`。指定的内部 HTTP
接口已获操作者授权，需部署在授权网络内。接口会收到任务目标、检查项、执行事实和
已保存的 receipt/stdout/stderr 内容，而非仅收到脱敏后的摘要；只能配置获准处理
这些绿区证据的推理服务。

Bridge 一次读取证据，三份文件合计最多 64 KiB，必须为 UTF-8；超限或无法解码时扣留，
不会截断后继续判断通过。模型返回的 JSON 继续执行原有结果、凭据和出区大小校验。
模型不能执行命令、读取其他文件或改变执行事实。验证后的内部结果保存为
`runs/<task-id>/<iteration>/execution/review.json`。程序日志只显示审查任务标识、
开始/完成及耗时，不打印提示词或接口响应。

只请求一次，不跟随重定向、不重试、不回退到 CLI、不重跑命令。接口失败或结果无效/
不安全时返回 NEEDS_HUMAN，原始输出不出区；超时和取消保留相应终态。已发出的请求
可能在服务端继续完成，但取消或到期后的响应不会保存或导出。等待时间同时受本地配置
及任务剩余期限约束。普通 TASK 继续使用 `agent_command`；默认 `ai_review=false`
的 EXEC 不调用审查接口。

### 简单 EXEC 结果跳过 AI

EXEC 的 `ai_review` 默认 `false`，省略时由 Bridge 直接返回结果，不启动绿区 AI。
可能返回受限信息或需要过滤时，由蓝区显式设置 `true`。所有检查必须在命令中用断言完成，退出码为零才表示通过。输出须为
不超过 2000 字节的 UTF-8 stdout，stderr 必须为空；异常输出不截断外发。
凭据检测、结果大小限制、执行回执和恢复规则仍生效。不确定输出内容或涉及日志时
显式启用 AI 审查。完整契约见协议中的 Optional AI review。

### 中文输出编码

Bridge 屏幕日志及 Python 子进程流统一使用 UTF-8，覆盖 Windows Git Bash 和
tee 重定向场景。更新后需要重启 Bridge，使新进程继承编码设置。该设置不会自动
转换所有原生命令的输出；使用其他编码的命令仍须显式输出 UTF-8。已损坏的旧日志
不会自动恢复。

交互式终端中，Bridge 程序日志的时间和级别显示为青色，Agent 正文为绿色，工具
调用及结果为灰色，Agent stderr 为黄色；多行输出延续所属类别的颜色。日志文件与
重定向输出仍为纯文本。任务结果 PASS 使用加粗绿色，FAIL 使用加粗红色。
设置 `NO_COLOR=1` 可关闭颜色。

### 消息历史重置

HAPI 消息历史代次或游标失效时，Bridge 自动绑定到当前消息末尾并继续监听，
不再要求更换状态目录或直接退出。支持停止 Bridge、删除本地 state 后重新 open。
重新绑定保留当前已有的任务、执行回执、去重记录、恢复状态和待发结果，不取消
正在执行的任务，也不重放历史指令。重置窗口内尚未接收的指令可能被跳过，程序会
明确提示蓝区重发尚未确认接收的指令；重发应保留原 task_id 和 iteration。
不要在 Bridge 运行中删除 state；删除 state 会丢失本地执行历史，不能据此确认
先前远端操作是否完成。

### v3 升级

两侧需同步升级到 0.5.1；旧标记和 v2 协议不再接收。旧配置的路由身份仅用于
验证原数据库归属，不作为新协议字段。已有完成记录、回执和去重记录保留，待发
通知保持 event_id 并转换成 v3。旧的未启动排队指令标记 BLOCKED，不会自动执行；旧执行中
或等待继续的任务（包括回答后重新排队的续跑任务）标记 NEEDS_HUMAN 并要求恢复检查。不能验证归属的旧状态原样
保留并拒绝加载，不通过删除历史来绕过恢复。详见协议 Upgrading from v2。

open 会从当前消息末尾开始新的交互；蓝区可直接下发已授权且就绪的待办工作，
Bridge 不自动续跑已有排队任务。需要保留并继续
原有监听及队列时使用 run。已完成记录、回执和恢复保护不因 open 被清除。
