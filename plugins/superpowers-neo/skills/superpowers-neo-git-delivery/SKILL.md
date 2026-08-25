---
name: superpowers-neo-git-delivery
description: Use after completing feature or bug-fix work in a Git repository; for explicit or general Git delivery requests; or when manually invoked to authorize current-task branch selection, a scoped commit when needed, normal push, and pull request creation
---

# Git Delivery

## Authority

Enter automatically after completed feature or bug-fix work in a Git repository and on delivery requests. Clarify requests whose intended actions are unclear. Respect any opt-out or narrower instruction; for non-Git work, provide only a result summary.

- **Automatic entry:** Commit task-owned uncommitted changes after checks. Push only an established, task-owned non-default branch. Outside automatic worktree isolation, do not infer branch-choice or PR authority.
- **Named request:** Perform exactly the requested Git actions without redundant confirmation. A first normal push includes setting upstream. Infer no unnamed action.
- **Manual invocation:** `$superpowers-neo-git-delivery` or an equivalent explicit attachment authorizes selecting or creating and switching to a task branch, a scoped commit when needed, normal push, and PR creation. A quoted name, discussion, or automatic trigger is not manual invocation.

Automatic entry and the manual bundle do not authorize merge, history rewrite, force push, hook bypass, cleanup, discarding changes, or bypassing repository protections. Apply the separate boundaries below even when a protected action is named.

## Deliver

1. Read repository guidance and inspect the branches, history, tracking, status, diffs, untracked files, generated artifacts, sensitive content, and intended PR target.
2. Choose a branch and scope that contain only the current task. Under automatic entry, ask before creating or switching branches or committing on the default branch, except that worktree isolation may create its task-owned non-default branch without another prompt. Under a named request, change branches only when requested. Under manual invocation, choose or create a suitable task branch without another prompt, following repository conventions or otherwise using `codex/<topic>`. Preserve unrelated changes and history; stop and ask when safe isolation is unclear. If nothing remains to deliver, report that instead of creating empty Git artifacts.
3. When a commit is authorized and task-owned code changes exist, ensure `superpowers-neo-code-simplification` has run on the deliverable diff; run it when the final diff has not had a simplification pass. Accept only behavior-preserving improvements within scope; a no-op is valid when the code is already clear.
4. Verify the actual content that will be delivered and re-establish checks invalidated by simplification. Fix task-caused failures only when a commit is authorized; otherwise preserve the workspace. Report unavailable checks, unrelated failures, and residual risk, and stop when they block safe delivery.
5. Review the final diff. Always perform a main-agent diff review; use `superpowers-neo-requesting-code-review` when risk justifies independent review. Evaluate findings with `superpowers-neo-handling-code-review-feedback`. If accepted feedback materially changes code, simplify those paths, refresh invalidated verification, and perform a final main-agent diff review. Repeat independent review only when the resulting risk or repository policy justifies it.
6. When a commit is authorized and task-owned changes exist, stage exact paths, inspect the cached diff, and commit using repository style. Otherwise leave the index unchanged and create no empty commit. Never bypass hooks by default. Delete only the implementation's temporary plan after a successful commit.
7. Push only the selected branch under the applicable authority, setting upstream on first push. Before a PR, identify the intended remote target and reuse only a matching existing PR without implicitly retargeting another. Base readiness on the content actually published for that PR, follow the template, and report verification gaps and risks. Create a ready PR only when complete and verified; otherwise stop or use a clearly qualified draft.

## Protected Actions

- **Merge:** Require an explicit merge request, then check CI, review status, branch currency, and repository policy.
- **History rewrite:** Require the specific operation and affected commits after explaining collaboration impact.
- **Force push:** Require separate risk confirmation for `--force-with-lease`; never use bare `--force` or bypass protections.
- **Hook bypass:** Require separate authorization after explaining the cause, validation gap, and risk. Never bypass a task-caused failure.
- **Cleanup:** Require an explicit target. Confirm integration, a clean worktree, and that the target is not the current working directory. Never discard changes implicitly.

Never fabricate results or treat a failed remote action as permission for a riskier workaround.
