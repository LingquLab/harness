# Crosszone 中文用户指南

Crosszone 用于让蓝区 AI 通过 HAPI 向绿区派发任务，由绿区 Bridge 在本地执行并返回结果。
本文覆盖安装配置、两种连接方式、命令执行、AI 任务、候选代码验证、并发调度、
提问与取消、结果审查，以及日志、恢复和升级。

日常使用只需在绿区启动 Bridge，再在蓝区会话中说明任务。0.6.0 起支持 `discover`，默认不需要
复制或填写 session ID；旧式显式会话启动方式也保留。蓝区 skill 和绿区插件目录需要同步更新。

## 蓝绿区分别负责什么

| 角色 | 职责 |
| --- | --- |
| 蓝区 AI | 理解用户任务、开发候选代码、定义检查与预期结果、派发任务、判断返回证据 |
| 绿区操作者 | 准备主机、CLI、授权 workspace、服务身份、测试数据和网络访问，启动 Bridge |
| 绿区 Bridge | 收发 HAPI 消息、记录状态、启动与取消任务、保存回执、校验并回传结果 |
| 绿区 AI 或审查接口 | TASK 中进行本地判断；有审查 EXEC 中只审查已经保存的执行证据 |

蓝区使用安装了 `cross-zone-development` skill 的 AI 会话，并在 HAPI 中与绿区协作。
先确认该 AI 能读取 skill，再在同一会话中说明目标、范围、检查标准和允许的操作。
蓝区不需要获得绿区 access key 或本机配置，也不替绿区选择 workspace。

HAPI 传递任务和结果，候选仓库代码通过 Git 仓库传递。代码验证时，蓝区先提交并推送，
绿区再从本地 workspace 已配置的 `origin` 拉取指定提交。绿区诊断改动不直接推送回蓝区。

## 选择启动方式

| 使用场景 | 绿区启动方式 | 如何连接 |
| --- | --- | --- |
| 平时只服务一个蓝区会话 | `bash start-bridge.sh` | 蓝区发送 OPEN，绿区自动绑定 |
| 同时服务多个蓝区会话 | 每个会话单独运行 `bash start-bridge.sh open <session-id>` | 每个 Bridge 固定监听指定会话 |

默认模式同一时间只绑定一个会话，但该会话内部仍可并发执行多个任务。
任务并发数默认是 4，由 `max_concurrent_tasks` 控制；这不代表能同时绑定 4 个会话。

## 绿区首次准备

在绿区 Windows 主机安装 Python 3.11 或更新版本、Git for Windows，以及配置使用的
CodeAgentCLI。后续命令均在 Git Bash 中运行。
提前完成 CLI 所需的本地认证，确认其能够非交互运行，并为任务准备获准使用的服务身份、
测试数据和访问权限；需要的工具应安装在实际执行命令的主机上。

将整个 `cross-zone-development` 插件目录放到批准的本地位置，保留 `cross_zone`、
`skills`、启动脚本和配置模板。Python Bridge 不需要安装第三方 Python 包。

以下示例假设插件位于 `C:\tools\cross-zone-development`，授权工作目录位于
`C:\work\my-project`。请替换为自己的路径；Git Bash 中分别写作
`/c/tools/cross-zone-development` 和 `/c/work/my-project`。

先检查 Python 和 Git：

```bash
py -3 --version
git --version
```

如果没有 `py` 启动器，可检查 `python --version`；启动脚本会依次尝试 `py -3` 和 `python`。

在插件目录首次创建本地配置，`-n` 可避免覆盖已有文件：

```bash
cd /c/tools/cross-zone-development
cp -n config.windows.json config.local.json
```

用编辑器打开 `config.local.json`，填写以下内容。JSON 中不要加入注释。

| 字段 | 如何填写 |
| --- | --- |
| `hub_url` | 蓝区会话所在的 HAPI Hub 地址；使用同一个 Hub |
| `access_key` | 具有目标会话访问权限的 HAPI access key |
| `agent_command` | 本机 CodeAgentCLI 的真实路径和参数，保留为 JSON 数组 |
| `exec_review` | 需要 AI 审查 EXEC 输出时使用的推理接口、模型、密钥和超时 |

Windows 模板中的 CLI 路径只是示例，需要确认本机文件存在。即使暂时只执行直接命令，
Bridge 启动前仍会检查配置的 CLI 是否可用。普通 TASK 使用该 CLI；
只有 `ai_review=true` 的 EXEC 才调用 `exec_review` 接口，接口必须获准接收绿区原始执行证据。

`config.local.json` 只保存在绿区本机，不提交到仓库，也不粘贴到蓝区会话。
session ID、workspace 和 state directory 不写入配置：默认模式自动发现会话，
workspace 由启动时所在的目录决定。

## 默认模式的完整使用流程

### 1 在绿区启动

先切换到授权工作目录，再用插件脚本的完整路径启动：

```bash
cd /c/work/my-project
bash /c/tools/cross-zone-development/start-bridge.sh
```

看到 `Discovery ready; waiting for a new blue OPEN` 后，保持终端运行。
首次启动会跳过已有消息，因此应先启动绿区，再让蓝区发起连接。

需要使用另一份本地配置时：

```bash
bash /c/tools/cross-zone-development/start-bridge.sh discover /c/config/green.json
```

相对配置路径按插件目录解析，使用绝对路径更清楚。启动时所在的 workspace 不受脚本位置影响。

### 2 在蓝区发起连接并说明任务

在希望使用的 HAPI 会话中对蓝区 AI 说：

> 请使用 cross-zone-development skill，以蓝区身份连接默认绿区 Bridge，等待 READY 后检查绿区 Python 版本，并返回检查结果。

蓝区 AI 会在当前会话发送协议 OPEN。绿区发现请求后绑定该会话，回复 READY，
蓝区再派发已授权的任务。用户不需要手写协议，也不要将协议冒充为绿区 user 消息。

发现阶段默认每隔约 5 秒查询新消息，实际等待还包括网络与处理耗时。
绑定后启用 SSE 通知加速，同时保留 REST 轮询作为兜底。

READY 只表示连接就绪，任务是否完成要看后续 RESULT。
PROGRESS 表示任务已开始，QUESTION 表示需要补充信息；将答案交给蓝区 AI 继续处理即可。

### 3 继续使用同一个会话

连接保持期间，直接在当前蓝区会话追加任务即可，无需反复 OPEN。
同一会话再次发送 OPEN 不会重置正在执行或等待回答的任务。

简单、输出可直接返回的命令通常使用 EXEC，默认不调用绿区 AI 审查。
日志、配置、服务响应等需要过滤的输出，应让蓝区设置 `ai_review=true`；
需要绿区 AI 判断、候选代码验证或恢复检查的工作使用 TASK。
这些协议选择由蓝区 AI 根据 skill 处理。

### 4 完成后释放连接

在蓝区原会话中说：

> 当前工作已经结束，请发送 CLOSE 释放默认绿区连接，并等待 CLOSED。

收到 CLOSED 后，绿区恢复待连接状态，其他蓝区会话就可以发送新的 OPEN。
任务执行完不会自动释放连接。

CLOSE 返回 BUSY 时，先完成或取消未结束的任务、回答待处理问题，并解决待发送结果或恢复事项，
再让蓝区使用新的请求 ID 发送 CLOSE。CLOSE 本身不会取消任务。

## 多个会话同时使用

需要同时服务多个会话时，使用旧式显式启动方式，每个会话一个 Git Bash 终端。
session ID 是 HAPI 会话地址 `/sessions/<session-id>` 中的完整 UUID。

在第一个终端启动会话 A：

```bash
cd /c/work/project-a
bash /c/tools/cross-zone-development/start-bridge.sh open <session-A-id>
```

在第二个终端启动会话 B：

```bash
cd /c/work/project-b
bash /c/tools/cross-zone-development/start-bridge.sh open <session-B-id>
```

请将尖括号占位符替换成真实 UUID，不要原样执行。显式模式由绿区发送旧式 OPEN，
蓝区接收后按 skill 开始协作；此模式不使用蓝区自动 OPEN/CLOSE 握手。
每个显式 Bridge 固定监听指定会话，结束监听时在对应终端按 `Ctrl+C`。

显式 `open` 会从当前消息末尾开始新的交互，保留历史执行记录，但不自动续跑旧队列。
需要继续原监听和已保存队列时，改用：

```bash
bash /c/tools/cross-zone-development/start-bridge.sh run <session-id>
```

默认自动模式重启则会恢复原绑定及执行状态，不需要改用 `run`。
不要为同一个会话同时启动多个 Bridge；默认 Bridge 绑定会话时也会持有该会话的实例锁。

## 任务派发与执行方式

先说明要做什么以及怎样判断成功，再由蓝区 AI 选择执行方式。

| 方式 | 适合的工作 | 谁执行与判断 |
| --- | --- | --- |
| EXEC 直接返回 | 精确命令、小型脚本、已知可直接返回的短输出 | Bridge 执行，按退出码、输出及出区校验构造结果，不启动 AI |
| EXEC 加 AI 审查 | 精确命令会产生需要过滤的日志、配置或服务响应 | Bridge 执行，推理接口审查已保存证据；不追加命令 |
| TASK | 需要绿区现场判断、补充诊断、候选代码验证或中断恢复 | 本地 Agent CLI 根据目标与 checks 执行，并审查结果 |

### 直接执行命令与脚本

EXEC 可以使用参数数组 `argv`，也可以指定 `bash`、`powershell` 或 `python` 脚本。
`argv` 不会自动经过 shell 展开，管道、重定向、变量等需要通过明确的解释器或脚本使用；
Windows `.bat`、`.cmd` 文件也需要显式解释器。Python 脚本使用 Bridge 自身的 Python。

例如对蓝区说：

> 使用 EXEC 检查绿区 Python 是否至少为 3.11。把版本条件写成断言，只返回版本号；命令限制 15 秒，总任务限制 600 秒。

相关且有依赖的多步命令可以放在一个脚本中，前一步失败时停止后续步骤。
使用前台命令，不把“启动后台进程成功”当作“后台工作已经完成”。
EXEC 在 `.state/<session-id>/` 执行，不支持通过协议指定 cwd、环境变量或 profile。
需要访问其他路径时，应在已授权的命令范围内明确访问，不能据此扩大工作权限。

EXEC 的 `ai_review` 默认为 `false`。直接返回要求 stdout 为有效 UTF-8、
最多 2000 字节，stderr 为空；异常输出会被扣留，不会截断后强行返回。
PASS 表示命令退出为零且结果通过输出校验，并不表示 AI 独立验证了业务目标。
因此，失败条件必须让脚本以非零码退出，而不是只打印“失败”。

### 对 EXEC 输出进行 AI 审查

例如对蓝区说：

> 使用 EXEC 查询指定测试服务的健康状态，限制 30 秒。返回内容可能含内部信息，请设置 ai_review=true，仅回传经过审查的检查结论。

启用审查后，绿区将 checks、执行事实及已保存的回执、stdout、stderr 交给
`exec_review` 指定的 OpenAI 兼容接口。该接口会接收原始绿区证据，因此需要获准处理这些数据。
三份证据文件合计最多 64 KiB，须能按 UTF-8 解码。

审查模型没有工具，不能重跑命令、读其他文件、修复问题或追加调查。
需要进一步诊断时，由蓝区根据结果派发新的 TASK。
接口失败、审查超时、证据超限或结果不安全时，不自动重试、切换 CLI 或重跑命令。
非零退出、取消和超时等执行事实不会被 AI 改成 PASS。

### 让绿区 AI 完成 TASK

TASK 需要明确目标和检查项。每项检查包含动作与预期，说明依赖、允许的变更、
停止条件和必要清理。普通环境检查不提供 `revision`，不会执行 Git fetch 或 checkout。

例如：

> 使用 TASK 检查测试服务为什么无法连接。只读取指定进程状态、监听端口和相关错误摘要，不修改配置、不重启服务；600 秒内返回观察结果、可能原因及仍无法确定的事项。

TASK 发现信息不足时可以返回 QUESTION。用户在蓝区补充答案后，蓝区通过 ANSWER
续接同一个绿区 Agent 会话；最多提问 3 次，实际还受 `max_questions` 配置限制。
EXEC 不支持 QUESTION/ANSWER。等待回答期间 TASK 会释放并发槽位，但原总任务期限继续计算。

## 候选代码的验证流程

需要证明某个代码版本在绿区环境中通过测试时，使用带 `revision` 的 TASK。
不能用一次普通环境检查来宣称代码已验证。

1. 蓝区完成修改和可用的本地检查，将候选提交推送到批准的仓库。
2. 绿区从 Git 仓库目录启动 Bridge，该目录已有正确的 `origin`，并能访问候选提交。
3. 蓝区指定完整、不可变的提交 ID，列出需要运行的检查、测试数据、预期和时限。
4. Bridge 从既有 `origin` 拉取精确提交，在任务专属的隔离、干净 checkout 中运行测试。
5. 绿区返回与该 revision 绑定的结果。蓝区核对每项证据，修复后以新提交和下一轮 iteration 再验证。

例如对蓝区说：

> 将当前候选提交推送后，用 TASK 在绿区验证该完整 revision。运行约定的回归测试，900 秒内返回逐项结果；缺少依赖时标记 BLOCKED，不以其他提交代替。

绿区可以在授权范围内诊断和尝试本地修复，但必须区分原始基线和修复后结果。
基线失败不能因为本地修复有效而改报 PASS。修复应由蓝区独立实现、提交，再送验。
代码验证 PASS 要求所有检查在指定且未修改的基线上通过；缺少依赖、数据、权限或隔离条件时返回 BLOCKED。

## 并发与任务身份

同一会话默认最多同时运行 4 个 EXEC/TASK，超过上限的任务排队。
执行和 EXEC 审查均占用槽位；需要串行时，将 `max_concurrent_tasks` 设为 1 并重启。

独立工作使用不同 `task_id`，例如下载任务和状态查询各用一个 ID。
同一 task_id 的下一轮 iteration 必须等前一轮终态后才能接收。
结果可能乱序返回，应按 `task_id`、`iteration`、当前会话和可选 revision 对照。

例如：

> 下载任务继续运行，同时用另一个 task_id 查询设备占用；两项工作不要写同一个文件。

不同任务 ID 不提供文件、服务或设备隔离。存在依赖或共享资源写入时，应按顺序执行，
或由命令和蓝区协调访问。候选 Git 准备在 Bridge 内串行，准备后的执行仍可并发。

完全重复的请求会被去重。相同 task_id/iteration 改变内容会被拒绝；
需要修改检查或命令时，应在前一轮结束后使用下一轮，而不是覆盖原任务。

## 提问 取消与超时

### 回答问题

收到 QUESTION 后，直接在蓝区提供缺少的信息，例如测试目标或批准的数据集。
蓝区应把答案发送为匹配 task_id、iteration 和 question_id 的 ANSWER。
不要在绿区 CLI 窗口中等待交互式输入。

### 取消指定任务

在蓝区说“取消任务 X 的第 Y 轮”。蓝区发送匹配的 CANCEL，
只影响该任务，不自动取消其他并行工作。
排队或等待回答的任务可以直接取消，运行中的任务会收到终止请求。
取消不会撤销已经发生的操作；无法确认进程终止或远端效果时，需要后续检查。

取消任务与关闭连接不同。自动模式只有满足空闲条件后，CLOSE 才能成功释放连接。

### 设置合理时限

| 参数 | 作用与范围 |
| --- | --- |
| `timeout_seconds` | 总任务时限，600–86400 秒，同时受本地 `max_task_seconds` 限制 |
| `execution_timeout_seconds` | 仅 EXEC 的命令时限，1 秒起，最多为总任务时限减 60 秒 |
| `exec_review.timeout_seconds` | AI 审查上限，默认 300 秒，还受任务剩余时间限制 |

普通 TASK 环境检查建议至少 600 秒，候选代码验证通常从 900 秒起。
带审查 EXEC 的总时限应覆盖命令时限加审查预算；初始排队等待不启动执行期限，
但已经开始的 TASK 在 QUESTION/ANSWER 等待中仍沿用原期限。

超时后先检查回执、遗留进程和已完成步骤，再将剩余工作拆成小任务。
不要直接重发原命令，或只增加超时重复执行已经完成的操作。

## 如何解读结果

| 消息或状态 | 含义与下一步 |
| --- | --- |
| ACK | 已持久化排队，不代表已执行；立即启动时可能直接收到 PROGRESS |
| PROGRESS | 开始或正在执行，不是成功证据 |
| QUESTION | 需要信息，通过蓝区回答后续接 |
| RESULT / PASS | 指定检查通过；仍需核对任务、revision 和实际证据是否匹配 |
| RESULT / FAIL | 执行或检查失败，依据证据修改后再进行下一轮 |
| RESULT / BLOCKED | 前提、权限、依赖等阻止执行或验证，先解决阻碍 |
| RESULT / NEEDS_HUMAN | 证据不能安全回传、审查无效或执行效果不明，查看绿区记录并安排核查 |
| RESULT / CANCELLED | 任务已取消，已发生的效果仍需按情况确认 |
| RESULT / TIMED_OUT | 超过时限，先确认部分进度和遗留效果 |
| REJECTED | 请求冲突、迭代不合法或控制消息无法匹配任务，需要蓝区修正请求 |

RESULT 声明 PASS 仍需与每项要求对照。例如只读到进程存在，不能证明下载完成或服务健康。
TASK 中未运行、缺失或失败的检查不能视为通过。启动失败、取消和超时等 Bridge 生成的终态
可能只有 status/reason/detail，不能当作包含完整测试证据的成功结果。

`egress_reviewed` 是绿区内部校验字段，会在发往 HAPI 前移除。
收到的 RESULT 没有这个字段是正常的，不应仅因此追加一次审查。
直接 EXEC 也不能描述为“已经 AI 审查”。

## 结果回传与日志边界

HAPI 返回有界结果，原始日志和执行回执保留在绿区。
完整 RESULT JSON 最多 4096 UTF-8 字节，summary 最多 3000 个字符；
直接 EXEC 的 stdout 另受 2000 字节限制。命令 stdout 与 stderr 合计超过 32 MiB 会终止执行。

不通过 HAPI 回传凭据、个人或客户数据、请求响应正文、大批量原始日志、
完整源码文件、diff、patch，以及达到 10 行的代码或伪代码片段。
允许回传与检查相关的 URL、内网地址、绝对路径、完整堆栈和少于 10 行的必要代码片段。
完整堆栈不按代码片段行数计算，但仍需满足出区和大小限制。

蓝区需要更多信息时，应请求范围明确的诊断摘要，不能用截图、文件上传或其他通道绕过结果约束。

## 配置参数参考

配置使用 JSON；改动后重启 Bridge 生效。默认值与范围如下：

| 字段 | 默认值或范围 | 用途 |
| --- | --- | --- |
| `hub_url` | 模板为 `https://su.kurox.cn/hapi/` | HAPI Hub 地址 |
| `access_key` | 模板占位符，需本地替换 | HAPI 凭据；设为 null 时可使用 `HAPI_ACCESS_KEY`，否则启动时提示输入 |
| `poll_seconds` | 5，允许 0.1–300 | 每轮处理后的最大轮询等待秒数 |
| `sse` | true | 开启服务器事件通知，加速已绑定会话消息获取 |
| `max_task_seconds` | 1800，允许 600–86400 | 本机总任务时限上限 |
| `max_concurrent_tasks` | 4，整数 1–16 | 并发任务槽位 |
| `max_questions` | 3，整数 0–3 | 每个 TASK 可提问的次数 |
| `agent_command` | 通用模板为 `["codeagent"]` | TASK 使用的 CLI 和参数；Windows 模板提供示例绝对路径 |
| `agent_live_log` | true | 显示 Agent 流式日志 |
| `exec_live_log` | true | 显示 EXEC 命令与实时输出 |
| `agent_log_max_chars` | 2000，整数 100–20000 | Agent 单次日志显示的字符上限 |
| `exec_review.base_url` | 使用模板中的授权接口，或按本地环境配置 | 审查 API 前缀，Bridge 追加 `/chat/completions` |
| `exec_review.model` | 模板为 `Qwen3.8` | 审查模型 |
| `exec_review.api_key` | 模板占位符，按接口要求替换 | 审查接口密钥 |
| `exec_review.timeout_seconds` | 300，整数 1–600 | 审查超时上限 |

旧配置显式写有较小的审查超时（如 60 秒）时仍使用原值。
需要新默认值时将其改为 300 或删除该字段，再重启。

常用环境变量：`BRIDGE_LOG_DIR` 改变终端日志目录，`NO_COLOR=1` 关闭颜色，
`BRIDGE_RESTART_DELAY` 设置守护重启间隔，`BRIDGE_DEBUG=1` 显示本地异常堆栈。
调试信息也只在绿区检查，不整段粘贴到 HAPI。

## 停止和重启

普通启动时，在绿区终端按 `Ctrl+C` 停止 Bridge。它会请求取消正在执行的任务，
已发生的本地或远端操作不会自动撤销。中断任务保留执行记录，不会因重启而重新执行；
效果不明确时，先让蓝区发起范围明确的恢复检查。

需要退出后自动重启，可从同一授权工作目录使用守护脚本：

```bash
bash /c/tools/cross-zone-development/watch-bridge.sh
```

守护脚本默认在 Bridge 退出 3 秒后重新启动自动发现模式。
显式多会话模式也可各自运行 `watch-bridge.sh <session-id>`。
不要同时为同一模式启动普通脚本和守护脚本。停止守护循环时按 `Ctrl+C`。

修改配置或更新代码后需要重启生效。继续使用相同配置文件、workspace 和本地状态目录；
自动模式会恢复之前的绑定，而不是自动释放会话。正常换会话应先在原会话完成 CLOSE。

### 中断后的恢复检查

进程异常退出后，已经运行或取消中的任务可能被标记为 NEEDS_HUMAN，并保留恢复上下文。
已保存但未发出的结果会重试发送；中断的执行不会自动重放。
尚有恢复事项时，新的 EXEC 会在启动命令前被阻止。

在蓝区说明：

> 先用只读 TASK 检查中断任务的本地回执、遗留进程和已完成效果。不要重跑原命令，确认恢复状态后再决定剩余操作。

有依据的恢复 TASK 可清除其已核查的恢复事项，不需要常规手动确认。
`acknowledge-recovery` 是高级人工操作，只清除本地恢复标记，不证明先前操作已经完成。

### 版本升级与历史重置

同步更新蓝区 skill 和整个绿区插件目录，保留本地配置及 `.state`，然后重启。
当前实时协议使用 `CROSS_ZONE` 标记与 `cross-zone/v3`，不接收旧 v2 消息和 target 字段。
从旧版状态迁移时，历史记录和去重保留，旧的未启动排队工作不自动执行，
中断或续接任务需先核查效果；不能通过删除数据库跳过恢复。

HAPI 消息历史代次或游标重置时，会从新的消息末尾重新绑定并继续监听，
保留已有任务、回执和待发结果。窗口内尚未接收的指令可能被跳过；
蓝区核对 ACK/PROGRESS 后，按原 task_id/iteration 重发尚未确认接收的同内容指令，
避免修改已接受的请求或重复已完成的操作。

## 内网下载

依赖或模型下载任务应说明来源、目标、超时和已有的校验和要求。
该绿区部署针对经过内部代理的已请求下载，已授权使用命令局部的证书校验跳过选项；
蓝区在下发 EXEC 前，按下载客户端和所需主机配置对应选项。
具体适用范围与客户端写法见 [内部代理下载规则](skills/cross-zone-development/references/internal-network.md)。

该策略只处理对应下载的证书信任问题，不改变整机 TLS 配置，
不自动适用于 HAPI 登录、无关 Git 连接、认证失败或不可达网络。
已经失败的 EXEC 仍保留失败事实；先确认没有重复效果，再决定是否派发修正后的下载。

## 命令速查

以下命令均通过 `bash /实际插件目录/start-bridge.sh` 执行。
有 session 参数的命令使用完整 UUID；尾部均可传本地配置文件路径。

| 参数 | 功能 |
| --- | --- |
| 不传参数，或 `discover [config-file]` | 自动发现并服务一个蓝区会话 |
| `sessions [config-file]` | 列出可访问会话 |
| `doctor <session-id> [config-file]` | 检查认证、会话、消息分页、CLI 和目录 |
| `open <session-id> [config-file]` | 从当前消息末尾开始新交互，发送绿区 OPEN 并持续监听 |
| `run <session-id> [config-file]` | 恢复该会话的监听与已保存队列；无游标时绑定当前末尾 |
| `bind <session-id> [config-file]` | 尚未绑定时建立初始游标，不发送 OPEN，也不持续监听 |
| `status <session-id> [config-file]` | 读取任务状态、恢复标记和待发结果数，需获得会话实例锁 |
| `acknowledge-recovery <session-id> [config-file]` | 高级人工恢复确认，需先自行核实先前效果且获得会话实例锁 |

`watch-bridge.sh [<session-id>|discover] [config-file]` 提供退出后重启；
无 session 时恢复自动模式，有 session 时每次以显式 open 启动。

需要运行随插件附带的本地回归测试时，切换到插件目录执行：

```bash
cd /c/tools/cross-zone-development
py -3 -m unittest discover -s tests -v
```

测试使用隔离的临时目录和模拟服务，不能替代目标绿区的真实网络、CLI 认证和硬件验证。

## 日志和状态放在哪里

默认自动模式的终端日志保存在插件目录的 `.cac/bridge-discover.log`。
显式模式日志为 `.cac/bridge-<command>-<session-id>.log`，例如
`.cac/bridge-open-<session-id>.log`。日志追加保存，原始内容留在绿区。

状态保存在配置文件所在目录：

| 路径 | 内容 |
| --- | --- |
| `.state/discovery/discovery.sqlite3` | 自动发现游标、当前绑定、连接请求和待发回复 |
| `.state/<session-id>/bridge.sqlite3` | 任务状态、去重、恢复记录和待发任务结果 |
| `.state/<session-id>/runs/<task-id>/<iteration>/execution/` | EXEC 的 `execution.json` 回执、stdout/stderr 及可选审查结果 |

不要通过删除 `.state` 解决连接问题，否则会丢失执行历史和去重依据。
Bridge 不提供操作系统或网络隔离，实际执行权限取决于绿区准备的工作环境和身份。

## 常见问题

| 现象 | 处理方式 |
| --- | --- |
| 启动提示已创建配置，随后退出 | 编辑插件目录的 `config.local.json`，填写真实配置后重新启动 |
| 发送 OPEN 后没有 READY | 确认绿区显示 discovery ready、两侧使用同一 Hub、密钥可访问当前会话；首次启动前发送的 OPEN 需要用新请求 ID 重发 |
| 收到 BUSY | 默认实例已绑定其他会话、会话存在未完成工作，或该会话正由显式 Bridge 占用；完成并释放原连接，或为其他会话单独启动显式 Bridge |
| 提示 `Another bridge owns this state directory` | 已有进程持有相同状态目录的实例锁；找到原终端使用或停止原进程，正常退出会释放锁 |
| 提示 discovery 状态属于另一个 Hub/workspace | 回到原 workspace 并使用原 Hub；需要不同工作环境时为显式 Bridge 使用独立配置目录和会话，不覆盖已有状态 |
| 找不到 Agent 可执行文件 | 检查 `agent_command` 的完整路径及本机安装，路径和参数应分别放在 JSON 数组中 |
| HAPI 返回 401 或 403 | 检查 access key 是否正确、是否有当前 Hub 和会话的访问权限 |
| 命令执行了但结果为 NEEDS_HUMAN | 查看绿区回执和日志；可能是输出不符合直返要求、审查失败或执行效果不明，不要直接重复执行 |
| 中文乱码 | 重启新版 Bridge；让外部命令显式输出 UTF-8，Bridge 不会自动转换所有原生命令编码 |

列出可访问会话，可在另一终端运行：

```bash
bash /c/tools/cross-zone-development/start-bridge.sh sessions
```

需要诊断某个已知会话，可从原授权 workspace 运行 `doctor <session-id>`。
需要读取本地任务状态时，先停止占用该会话的 Bridge，再用相同配置运行
`status <session-id>`；该命令也需要获得会话实例锁。

完整参数、任务格式和结果约束见 [中文说明](README_CN.md) 与
[协议参考](skills/cross-zone-development/references/protocol.md)。
