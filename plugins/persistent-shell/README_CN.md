# Persistent Shell

[English](./README.md)

这是一个兼容 ZCode 与 Codex 的插件，用于在 Windows 上管理可复用、保留状态的 SSH shell 会话。PowerShell 与 Git Bash 启动器共享一个用户级本地守护进程，使多次命令可以复用同一个远端 shell channel。

## 使用方式

需要在 OpenSSH 别名或 `[user@]host` 上重复执行命令时，让智能体安装或使用 `pshell`。通过 `pshell start` 启动会话、`pshell exec` 执行命令、`pshell status` 查看状态，并用 `pshell stop` 关闭会话。

在 Windows 上运行 `skills/persistent-shell/scripts/install.ps1` 安装 skill 和启动器。安装器会选择一个能够导入 Paramiko 的可用 Python 3 解释器，不要求固定的 Python 小版本。

## 依赖与行为

- 网络：连接到用户明确选择的 SSH 目标。
- 命令：运行 Python、Paramiko、PowerShell 或 Git Bash 启动器，以及用户交给远端 shell 的命令。
- 文件：安装到用户的 Codex skills 目录，在指定的用户 bin 目录写入启动器，可能更新用户 PATH；守护进程状态保存在 `%LOCALAPPDATA%\pshell`，已接受的主机密钥记录到 `~/.ssh/known_hosts`。
- 服务：按需启动只监听 loopback 的用户级守护进程。支持密钥或 SSH agent 认证；交互式密码、文件传输、端口转发和代理跳转不在其范围内。
- Hook 与 MCP：无。

本插件采用 MIT 许可证。
