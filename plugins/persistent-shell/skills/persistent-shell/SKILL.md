---
name: persistent-shell
description: Manage reusable SSH shell sessions from Windows with the user-level pshell command. Use when repeated remote commands need to preserve shell state or avoid SSH session startup latency; do not use for interactive full-screen programs, file transfer, or port forwarding.
---

# Persistent SSH Shell

Use `pshell` to keep one shell channel open per SSH target across separate local commands. It reads OpenSSH aliases and keys from `~/.ssh/config` and does not require PuTTY or WSL.

The installed PowerShell and Git Bash launchers use the same local daemon. A session started in either shell is immediately available from the other.

## Workflow

1. Run `pshell start <target>` before latency-sensitive work. Targets may be an OpenSSH alias or `[user@]host`; this resolves connection options once for that session.
2. Run commands with `pshell exec <target> -- <command>`. Quote shell operators so the remote shell, rather than PowerShell, interprets them.
3. Use `pshell shell <target>` for a local read-eval loop backed by the same remote shell.
4. Inspect connections with `pshell list` or `pshell status <target>` and close them with `pshell stop <target>` or `pshell stop --all`.

Preserve state deliberately: `cd`, `export`, environment activation, functions, and shell variables affect later commands in the same session. A reconnect creates a new shell and reports `shell state was reset`; never imply that prior state survived.

## Trust And Limits

- Use trust on first use for new hosts: accept the first host key and persist it in `~/.ssh/known_hosts`. Reject a changed key unless the user separately verifies and removes or replaces the retained entry.
- Authentication is non-interactive: use configured keys or an SSH agent. Do not place passwords in commands, state files, or skill resources.
- Treat command timeouts as destructive to that shell channel. The daemon closes it because output boundaries can no longer be trusted.
- The persistent non-interactive channel combines stdout and stderr. Use ordinary SSH when exact stream separation matters.
- Use ordinary interactive `ssh` for `vim`, `top`, `less`, password prompts, interactive `sudo`, or other terminal applications. Use `scp`, `sftp`, or purpose-built tools for file transfer.
- One command runs at a time per target. Different targets may run concurrently.

Run `pshell doctor` when setup or daemon startup fails. For protocol, state, and failure details, read [references/design.md](references/design.md).

Place client options before the target because everything after the target may be remote command text. For example: `pshell exec --timeout 10 server -- "sleep 2; hostname"`.

## Installation

When installing this packaged skill on Windows, run `scripts/install.ps1` from the extracted `persistent-shell` directory. It copies the skill into the user's Codex skills directory, creates PowerShell and Git Bash launchers, and adds the user bin directory to PATH. It selects an available Python 3 interpreter with Paramiko instead of requiring a particular Python minor version.
