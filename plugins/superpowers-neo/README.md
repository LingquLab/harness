# Superpowers Neo

[中文文档](./README_CN.md)

This Codex plugin provides modular software-development workflows whose rigor scales with task complexity. Its skills cover design, planning, isolated worktrees, plan execution, validation, debugging, simplification, review, verification, and Git delivery.

## Use

Describe the development task normally. Each skill is independently discoverable and activates only when its focused workflow applies; there is no mandatory startup or umbrella skill.

## Scope and Test Delivery

Implement the smallest complete requested solution. Unrequested features, speculative safeguards, locking mechanisms, or extra testing infrastructure require an explanation and explicit user approval before implementation. Ordinary in-scope implementation choices remain autonomous.

Avoid excessive defensive programming: retain real boundary checks, expose required failures, reuse supported implementations, and test public behavior. Do not add hypothetical guards or silently substitute execution paths.

Run proportionate validation during development, but commit only key tests for core behavior, essential contracts, or significant regressions. Remove task-created non-core probes, debug scripts, temporary harnesses and generated artifacts before staging. Preserve existing tests, user files and explicitly requested test deliverables.

## Skills

| Skill | Use when |
|---|---|
| `superpowers-neo-designing-complex-changes` | A change is complex, ambiguous, cross-component, or architecture-sensitive |
| `superpowers-neo-writing-plans` | Approved work needs a multi-step or subagent-ready implementation plan |
| `superpowers-neo-using-git-worktrees` | Workspace isolation may be needed for dirty or parallel work |
| `superpowers-neo-executing-plans` | An in-scope plan is ready for main-agent and scoped-subagent execution |
| `superpowers-neo-validation-strategy` | A change needs validation proportional to its risk |
| `superpowers-neo-systematic-debugging` | A bug or unexpected failure needs evidence-based diagnosis |
| `superpowers-neo-code-simplification` | Simplifying code and user-facing documentation before final review or delivery |
| `superpowers-neo-requesting-code-review` | A substantial or risky change benefits from independent review |
| `superpowers-neo-handling-code-review-feedback` | Review feedback needs technical evaluation |
| `superpowers-neo-verification-before-completion` | Work is about to be described as complete, fixed, or passing |
| `superpowers-neo-git-delivery` | Completed Git work needs scoped commit and delivery handling |

## User documentation

README and product guides explain capabilities, suitable tasks, setup and usage. Source history and internal implementation details belong in linked maintainer or attribution documents. In Chinese documentation and code comments, keep technical terms such as `token` and `opaque handle` in English. Explain behavior with concrete actions checked against the code, avoiding literal translations and vague verbs.

## Dependencies and effects

- Network: Git delivery may contact configured Git remotes and forge APIs when the user requests delivery.
- Commands: workflows may run repository build, test, formatting, Git, and forge CLI commands.
- Files: implementation workflows can edit the active repository. Worktree and Git delivery workflows can create task branches, commits, worktrees, pushes, and pull requests within the authorization described by the selected skill.
- Services: none required beyond the repository's own toolchain and configured Git hosting for delivery.
- Hooks and MCP: none.

Licensed under MIT. See [third-party notices](../../THIRD_PARTY_NOTICES.md) for attribution.
