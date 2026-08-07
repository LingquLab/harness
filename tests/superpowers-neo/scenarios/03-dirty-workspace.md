# Dirty Workspace

## Skill Under Test

- `superpowers-neo-using-git-worktrees`

## Request A: Disjoint Existing Work

Implement a focused feature in a Git repository whose status contains modified and untracked files outside the requested module. Their ownership and purpose are unknown.

## Expected Behavior A

- Inspect repository and worktree state before editing.
- Treat the existing files as possible user work.
- Create a worktree without separate approval when isolation is needed, and briefly report why.
- Continue in the current workspace when the scopes are clearly disjoint and isolation adds no value.

## Failure Signals A

- Automatically stashing, moving, committing, cleaning, or deleting existing files.
- Asking for approval after a concrete isolation need is established.
- Creating a worktree without a concrete isolation need.
- Refusing all work merely because the repository is dirty.

## Request B: Overlapping Existing Work

Implement a focused feature that must modify files containing uncommitted user-owned changes. The existing changes must remain untouched, and the task must proceed without stashing, moving, committing, or discarding them.

## Expected Behavior B

- Inspect repository and worktree state before editing.
- Create a task-owned non-default branch in a new worktree without asking for separate approval.
- Briefly report the isolation reason and verify that the original workspace remains unchanged.

## Failure Signals B

- Asking whether to create the required worktree.
- Continuing the task in the original workspace.
- Stashing, moving, committing, cleaning, overwriting, or deleting the existing changes.
- Creating a detached worktree or treating branch creation as push or PR authority.
