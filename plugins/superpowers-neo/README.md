# Superpowers Neo

[中文文档](./README_CN.md)

This ZCode and Codex plugin provides modular software-development workflows whose rigor scales with task complexity. Its skills cover design, planning, isolated worktrees, plan execution, validation, debugging, simplification, review, verification, and Git delivery.

## Use

Describe the development task normally. Each skill is independently discoverable and activates only when its focused workflow applies; there is no mandatory startup or umbrella skill.

## Dependencies and effects

- Network: Git delivery may contact configured Git remotes and forge APIs when the user requests delivery.
- Commands: workflows may run repository build, test, formatting, Git, and forge CLI commands.
- Files: implementation workflows can edit the active repository. Worktree and Git delivery workflows can create task branches, commits, worktrees, pushes, and pull requests within the authorization described by the selected skill.
- Services: none required beyond the repository's own toolchain and configured Git hosting for delivery.
- Hooks and MCP: none.

This plugin is an independent adaptation inspired by Jesse Vincent's Superpowers and includes additional attributed material. See the repository `THIRD_PARTY_NOTICES.md`; the plugin is licensed under MIT.
