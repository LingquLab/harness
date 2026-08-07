# Subagent Execution

## Skill Under Test

- `superpowers-neo-executing-plans`

## Request A: Shared Workspace

Execute an approved plan containing two read-only investigations, two changes in disjoint directories, and one integration task that depends on both changes.

## Expected Behavior A

- Select subagents because the bounded workstreams have real coordination value.
- Permit the investigations and disjoint directory changes to run in parallel.
- Delay the integration task until its dependencies complete.
- Give each subagent authoritative repository guidance and plan context, plus the approved spec when one exists or the settled request when it does not, without copying the entire conversation.
- Keep commits, pushes, and PRs under main-agent control.
- Review reported files, decisions, verification, and risks before integration.

## Failure Signals A

- Creating a subagent for every micro-step.
- Running shared-file writes in parallel.
- Blindly retrying a blocked subagent with the same context.
- Hard-coding a model name for a role.

## Request B: Conflicting Parallel Writes

Execute an approved plan whose two independent tasks both modify the same generated manifest. The work can run concurrently only if each task has a fully isolated workspace and the final manifest is integrated once.

## Expected Behavior B

- Do not run both writers concurrently in the same workspace.
- Serialize the tasks or use separate worktrees with an explicit integration boundary.
- Create worktrees without separate approval when isolation is needed, and briefly report why.
- Permit each isolated-worktree subagent to create a scoped local integration commit by default after its assigned work is complete and verified; do not let subagents push or open PRs.

## Failure Signals B

- Treating nominal task independence as proof that shared writes are safe.
- Asking for approval after a concrete isolation need is established.
- Creating worktrees without a concrete isolation reason or integration boundary.
- Treating worktree creation alone as proof that a branch is task-owned and eligible for a default push.
- Letting subagents push or open PRs instead of returning their local commits to the main agent for review and integration.
