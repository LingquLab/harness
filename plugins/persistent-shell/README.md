# Persistent Shell

[中文文档](./README_CN.md)

This ZCode and Codex plugin manages reusable, stateful SSH shell sessions from Windows. PowerShell and Git Bash launchers share a user-level local daemon, so repeated commands can reuse one remote shell channel.

## Use

Ask the agent to install or use `pshell` for repeated commands on an OpenSSH alias or `[user@]host`. Start a session with `pshell start`, execute commands with `pshell exec`, inspect it with `pshell status`, and close it with `pshell stop`.

Run `skills/persistent-shell/scripts/install.ps1` on Windows to install the skill and launchers. The installer selects an available Python 3 interpreter that can import Paramiko; it does not require a fixed Python minor version.

## Dependencies and effects

- Network: opens SSH connections to targets explicitly selected by the user.
- Commands: runs Python, Paramiko, PowerShell or Git Bash launchers, and commands supplied for the remote shell.
- Files: installs under the user's Codex skills directory, writes launchers to the selected user bin directory, may update the user PATH, stores daemon state under `%LOCALAPPDATA%\pshell`, and records accepted host keys in `~/.ssh/known_hosts`.
- Services: starts a user-level loopback daemon on demand. It supports key or SSH-agent authentication; interactive password entry, file transfer, port forwarding, and proxy jumps are outside its scope.
- Hooks and MCP: none.

This plugin is licensed under MIT.
