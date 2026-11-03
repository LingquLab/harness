---
name: superpowers-neo-executing-plans
description: Use when an in-scope implementation plan is ready for execution, especially for multi-step work that may benefit from scoped delegation or coordinated parallelism
---

# Executing Plans

## Overview

Execute an approved plan continuously, using the main agent and only as much delegation as the work justifies. Treat the plan as an execution guide while preserving its approved scope, architecture, interfaces, and acceptance criteria.

## Load Authoritative Context

Read repository guidance, the approved spec when one exists, otherwise the settled request, and the assigned plan task from their authoritative paths. Give delegated agents those paths plus the goal, boundaries, dependencies, and acceptance criteria. Do not replace source documents with a copied conversation or bias an agent toward an expected conclusion.

## Choose an Execution Mode

| Work shape | Mode |
|---|---|
| Small, tightly coupled, or shared-file work | Main agent |
| Bounded workstream where specialization or context isolation helps | One subagent |
| Dependent tasks or tasks sharing files, state, artifacts, or ordering | Main agent or serial subagents |
| Read-only work or clearly disjoint write ownership | Parallel subagents |
| Parallel writes that require isolation | Separate worktrees |

For workspace isolation decisions, use `superpowers-neo-using-git-worktrees`. In a shared workspace, parallel writers need explicit, disjoint ownership and shared state must be serialized.

## Dispatch Boundaries

Each subagent receives:

- its goal, owned files, forbidden scope, dependencies, and acceptance criteria;
- authoritative repository-guidance and plan paths, plus the approved spec path when one exists or the settled request when it does not;
- required verification and the result protocol below.

Shared-workspace subagents may modify and verify but must not commit, push, or open a pull request; this is a coordination boundary, not an extra user-authorization prompt. An isolated-worktree subagent may create a scoped local integration commit by default after its assigned work is complete and verified. Subagents do not push or open pull requests. The main agent applies the delivery skill's default push rule only after reviewing and integrating the delegated result.

Do not hard-code model names. Subagents inherit the current model and reasoning settings unless the user or a supported environment policy explicitly directs otherwise.

## Execute Continuously

After any required design or spec approval, proceed through an in-scope plan without asking whether to continue after each task. The plan needs no separate approval when it stays within the approved spec or settled request. Give concise progress updates and integrate results as they arrive.

Implement only the requested capabilities. Do not add unrequested abstraction, locking, protection, or testing capabilities as hidden plan work. If an extra capability appears necessary, explain it and wait for explicit user approval; ordinary in-scope implementation choices remain autonomous.

Adjust file choices, ordering, and implementation details when the approved behavior and acceptance criteria stay intact. Pause only for a scope or architecture change, a false core assumption, an interface or acceptance-criteria change, major risk, irreversible action, unsafe workspace conflict, genuine ambiguity, or a blocker that cannot be resolved safely.

## Result Protocol

Every delegated result states:

- status: `complete`, `partial`, `needs clarification`, or `blocked`;
- modified files and artifacts;
- key decisions;
- verification commands and results;
- residual risks or unresolved work.

Review the evidence before integration. Do not blindly retry an unchanged prompt after failure; diagnose the gap, then add context, narrow the task, take over directly, or reassign it.
