---
name: superpowers-neo-writing-plans
description: Use when execution is multi-step, high-risk, cross-module, likely to span sessions, or intended for handoff to another agent.
---

# Superpowers Neo Writing Plans

## Purpose

Create a standalone execution contract usable without the original conversation. Preserve approved decisions while leaving implementation choices open where the repository should decide them.

## Confirm the Trigger and Inputs

Do not create a persistent plan for a clear small edit. Inspect and implement that work directly with proportionate verification.

For work that meets the trigger:

1. Read repository guidance, any approved spec, and the relevant source and test structure.
2. Treat the approved spec or settled user request as the scope boundary.
3. Resolve material design ambiguity before planning. Use `superpowers-neo-designing-complex-changes` when its complexity, ambiguity, cross-component, or architecture triggers apply.

## Write a Sufficient Plan

Include:

- Goal, scope, and explicit non-goals.
- Relevant components, files or modules, and authoritative repository references.
- Ordered implementation work and dependencies between tasks.
- Key risks, constraints, assumptions, and compatibility boundaries.
- Verification strategy with checks justified by risk.
- Independently assignable tasks where work can be separated safely.

Point to repository-relative sources instead of duplicating unrelated material. Do not require code blocks, line-by-line edits, unnecessary implementation detail, or per-task commits.

## Make Each Task Subagent-Ready

For every independently assignable task, state:

1. **Objective and role:** the outcome and its place in the overall design.
2. **Background and prerequisites:** required decisions, dependencies, and repository context.
3. **Modification scope:** owned files or modules and coordination boundaries.
4. **Constraints and non-goals:** behavior and areas to preserve or avoid.
5. **Acceptance and verification:** observable criteria and runnable commands.
6. **Artifacts and interfaces:** outputs and downstream contracts.

Order dependencies explicitly. Label work independent only when its contract is sufficient without hidden conversational context.

## Preserve Approval Boundaries

An implementation plan within an approved spec needs no separate user approval. Request approval before execution when it expands scope, changes architecture, interfaces, or acceptance criteria, or introduces major risk. Apply the same boundary to a settled request when no spec exists.

If feedback or discovery crosses a boundary, update the plan and request approval again. Ordinary detail within the approved boundary does not reopen approval.

A generated plan does not expand Git delivery authority. Automatic delivery authorizes a scoped commit by default and a normal push from an established, task-owned non-default branch; branch choice on the default branch and pull-request creation still require user direction. Explicitly invoking `superpowers-neo-git-delivery` is a separate bundled authorization for task-branch creation, commit, normal push, and PR creation. Merge, history rewrite, hook bypass, and cleanup always retain their own explicit authorization boundaries. Treat adding any protected action as a material approval decision, not ordinary plan detail.

## Store and Retire the Plan

Classify the plan before writing it:

### Durable Plan

Use a durable plan for cross-session, long-term handoff, or maintenance value. Follow a Neo-compatible repository convention not tied to the original Superpowers product name. If only `docs/superpowers/` exists, or no compatible convention exists, use:

`docs/plans/YYYY-MM-DD-<topic>.md`

Retain and commit it with the implementation, not in a mandatory plan-only commit.

### Temporary Plan

Use `docs/plans/YYYY-MM-DD-<topic>.md` for a working plan with no long-term value. Keep it uncommitted and unstaged. Delete it only after implementation is complete and the implementation commit succeeds. Include this cleanup in the handoff so broad staging does not capture it.

After the plan is ready, use `superpowers-neo-executing-plans` when structured execution or handoff is needed.
