---
name: superpowers-neo-using-git-worktrees
description: Use when a user requests isolation, parallel writes may conflict, the current Git workspace is unsafe, or staged, unstaged, or untracked files may belong to another task
---

# Using Git Worktrees

## Overview

Default to the current workspace. When isolation is needed, create a worktree without separate user approval and briefly report why.

## Evaluate the Workspace

1. Read repository guidance and any approved spec or plan requirements.
2. Inspect staged, unstaged, and untracked files with `git status --short --branch`, and inspect existing worktrees with `git worktree list`.
3. Determine whether those files overlap the planned work or may belong to another task.
4. If isolation is needed, create a worktree and preserve the existing workspace unchanged.

## Choose the Execution Shape

| Situation | Choice |
|---|---|
| Small, coupled, or shared-file work | Current workspace, main agent |
| Independent tasks that still share files or state | Current workspace, serialized work |
| Read-only tasks or writes with clearly disjoint ownership | Parallel agents may share the workspace |
| Conflicting parallel writes, unsafe workspace, or protected existing work | Separate worktree |

Same-workspace parallel writers must have explicit, disjoint file ownership. Serialize changes to shared files, generated artifacts, repository state, or ordered dependencies.

## Preserve Existing Work

Never automatically stash, move, clean, overwrite, or discard pre-existing or user-owned changes. Commit only the exact task-owned scope under the delivery default. Do not assume an untracked file is disposable or that a staged change belongs to the current task.

Creating a worktree does not by itself establish task ownership or authorize protected delivery actions. In a shared workspace, delegated agents may edit and verify but must not commit, push, or open a pull request. In an isolated worktree, a delegated agent may create a scoped local integration commit by default after its assigned work is complete and verified. Delegated agents do not push or open pull requests; after reviewing the result, the main agent may use the default push authority only when the branch is established, task-owned, and non-default.

After setup, verify the original workspace is unchanged and the selected workspace is on the intended branch and path.
