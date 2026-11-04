# LingquLab Skills

[English](README.md)

面向 ZCode 和 Codex 的 skill 插件集，帮助你开发软件、编写 Ascend C 算子、检索 AI 系统知识、绘制图表，并在开发环境与受保护环境之间协作验证。按需安装所需插件即可。

## 安装

在 ZCode 中，打开 **Settings → Plugins → Create → Add marketplace**，输入 `LingquLab/harness`。

在 Codex 中，添加 marketplace 并安装插件：

```bash
codex plugin marketplace add LingquLab/harness
codex plugin add superpowers-neo@lingqulab
```

将 `superpowers-neo` 替换为下表中的插件名。安装后新建 Codex 任务，以便发现新安装的 skills。

## 选择插件

| 插件 | 可以帮你做什么 | 版本 |
|---|---|---|
| [superpowers-neo](plugins/superpowers-neo/README_CN.md) | 完成软件设计、实现、调试、审查和交付，并按任务选择适当的检查 | `0.3.5` |
| [ascendc-development](plugins/ascendc-development/README_CN.md) | 开发 Ascend C 算子、核对 API、诊断运行时故障和配置 CANN | `0.3.1` |
| [cross-zone-development](plugins/cross-zone-development/README_CN.md) | 在受保护环境执行检查，通过 HAPI 返回限定范围内的结果 | `0.7.0` |
| [persistent-shell](plugins/persistent-shell/README_CN.md) | 从 Windows 复用 SSH session，保留远程工作目录和 shell 状态 | `0.1.1` |
| [archify](plugins/archify/README_CN.md) | 将系统描述或代码转换为交互式图表，并导出图片和视频 | `2.17.0-dev.1` |
| [aikg-search](plugins/aikg-search/README_CN.md) | 查找 AI 基础、推理训练、GPU/NPU 和性能分析的知识解释与参考资料 | `0.1.0` |
| [wiki-search](plugins/wiki-search/README_CN.md) | 按关键词、知识库、类目或文档子树查找华为 WIKI 文档 | `0.1.2` |

## 开始使用

安装插件后，直接描述任务即可。例如：

- **软件开发：**“找到这个测试失败的原因并修复。”
- **Ascend C：**“针对目标 CANN 版本，检查这个算子的 tiling 和内存对齐。”
- **跨区检查：**“在绿区执行这个只读检查并返回结果。”绿区配置见[用户指南](plugins/cross-zone-development/USER_GUIDE_CN.md)。
- **SSH session：**“使用 persistent shell 在这台主机上连续执行命令。”需要 Windows、SSH 访问权限和安装了 Paramiko 的 Python。
- **图表：**“绘制从浏览器到 API、缓存和数据库的请求流程。”需要 Node.js 18 或更高版本。
- **AI 知识：**“解释 KV Cache，以及哪些因素决定它的显存占用。”公开的 AIKG 资料不需要 WIKI 认证。
- **华为 WIKI：**“在这个知识库中搜索部署指南。”在线访问需要跨区插件，以及在绿区完成认证的 `wiki-cli`。

一般知识查询先检索 AIKG，需要更多证据时再使用 WIKI。你也可以明确指定来源。WIKI 检索会先检查你提供的本地资料库，再访问在线服务。

各插件指南进一步说明安装方式、依赖、命令，以及文件和网络访问范围。

## 手动安装 Neo

如果你的环境不支持插件，可以预览并直接安装 Neo 的 skills：

```bash
scripts/install.sh --dry-run
scripts/install.sh
```

使用 `--target PATH` 指定其他目录，默认目录为 `${CODEX_HOME:-$HOME/.codex}/skills`。已有目标不会被覆盖。避免同时通过手动安装和 marketplace 安装同一组 skills；确认新安装可用后，再移除旧副本。

## 参与维护与许可证

校验与添加插件的方法见 [marketplace 维护指南](docs/maintaining-marketplace.md)。

marketplace 和大多数插件采用 [MIT](LICENSE) 许可证。Ascend C Development 使用随附的 [CANN 许可证](plugins/ascendc-development/LICENSE)。其他随附材料保留各自条款，详见[第三方说明](THIRD_PARTY_NOTICES.md)。
