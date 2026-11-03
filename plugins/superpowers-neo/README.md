# Superpowers Neo

[中文文档](./README_CN.md)

This ZCode and Codex plugin provides modular software-development workflows whose rigor scales with task complexity. Its skills cover design, planning, isolated worktrees, plan execution, validation, debugging, simplification, review, verification, and Git delivery.

## Use

Describe the development task normally. Each skill is independently discoverable and activates only when its focused workflow applies; there is no mandatory startup or umbrella skill.

## Scope and Test Delivery

Implement the smallest complete requested solution. Unrequested features, speculative safeguards, locking mechanisms, or extra testing infrastructure require an explanation and explicit user approval before implementation. Ordinary in-scope implementation choices remain autonomous.

Avoid excessive defensive programming: retain real boundary checks, expose required failures, reuse supported implementations, and test public behavior. Do not add hypothetical guards or silently substitute execution paths. Engineering ideas informed by [avoid-overkill](https://github.com/6Kmfi6HP/avoid-overkill) are independently restated within Neo; its writing guidance and plugin machinery are not included.

Run proportionate validation during development, but commit only key tests for core behavior, essential contracts, or significant regressions. Remove task-created non-core probes, debug scripts, temporary harnesses and generated artifacts before staging. Preserve existing tests, user files and explicitly requested test deliverables.

## Dependencies and effects

- Network: Git delivery may contact configured Git remotes and forge APIs when the user requests delivery.
- Commands: workflows may run repository build, test, formatting, Git, and forge CLI commands.
- Files: implementation workflows can edit the active repository. Worktree and Git delivery workflows can create task branches, commits, worktrees, pushes, and pull requests within the authorization described by the selected skill.
- Services: none required beyond the repository's own toolchain and configured Git hosting for delivery.
- Hooks and MCP: none.

This plugin is an independent adaptation inspired by Jesse Vincent's Superpowers and includes additional attributed material. See the repository `THIRD_PARTY_NOTICES.md`; the plugin is licensed under MIT.
