---
name: superpowers-neo-powershell-remote-execution
description: Use when PowerShell drives a Linux host over SSH, especially when the remote work needs shell control flow, pipelines, quoting, variable expansion, multiple commands, or transferred scripts.
---

# PowerShell Remote Linux Execution

Keep non-trivial remote shell logic out of inline SSH commands. PowerShell, SSH, and the remote shell each add a parsing boundary; nested command text is difficult to inspect and easy to alter unintentionally.

## Execute Remote Work

1. Put loops, conditionals, pipelines, heredocs, command substitutions, or multi-command logic in a task-scoped `.sh` file.
2. Give the script a narrow interface. Pass changing values as fixed positional arguments rather than interpolating them into its source or constructing remote command strings.
3. Transfer the script through an existing Mutagen session when one already covers the relevant paths. Otherwise use another method only after verifying the destination host, path, and transferred content.
4. Invoke SSH with only the fixed script path and its positional arguments. Quote arguments at the PowerShell boundary and let the script validate their count and meaning.
5. Capture the transfer result, remote exit status, and bounded output. Remove the remote task file only when cleanup is authorized and its exact path is known.

An inline SSH command is acceptable for a simple, fixed invocation such as `uname -a` or calling the transferred script. Do not compress non-trivial logic into one line to avoid creating a script.

## Safety

- Do not assume a Mutagen session exists, points at the intended host, or has synchronized the current file; inspect its endpoints and state first.
- Do not pass secrets in command-line arguments when they can be read from a protected remote file or standard input.
- Do not transfer or invoke a script until its task scope, target path, and effects are understood.
