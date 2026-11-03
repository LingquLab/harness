---
name: superpowers-neo-designing-complex-changes
description: Use when a requested change is complex, has key ambiguity, spans components, has cross-component effects, or requires an architectural decision.
---

# Designing Complex Changes

## Purpose

Turn an underspecified or structurally significant change into an approved design without blocking ordinary edits. Keep the process proportional to the decisions at stake.

## Confirm the Trigger

Use this workflow only when at least one trigger in the description applies. Do not use it for a clear small edit, a straightforward fix, or a configuration change whose scope and approach are already understood; inspect the repository and implement those directly.

The user may explicitly waive this design workflow. Record the waiver and proceed within the stated scope. Do not infer a waiver from urgency or brevity.

## Prohibit Overengineering

Implement the smallest complete solution to the user's requested behavior. Do not add unrequested capabilities, frameworks, generalization, or protective infrastructure for hypothetical needs. Calling an addition a best practice, safety measure, or internal detail does not bring it into scope.

If an extra capability seems necessary, explain the concrete need, smallest proposed addition, and cost, then wait for explicit user approval before implementing it. This applies even to a small addition. Routine implementation choices needed to deliver the requested behavior do not require separate approval.

For example, a requested test runner does not authorize file locking or file-protection infrastructure merely to prevent hypothetical test edits. Reuse existing test facilities and simple fixtures instead of inventing extra mechanisms.

## Inspect Without Changing the Project

Before proposing a design:

1. Read repository guidance and the relevant code, tests, documentation, and existing conventions.
2. Run read-only inspection or diagnostics needed to replace assumptions with facts.
3. Identify the decisions that materially affect scope, architecture, interfaces, behavior, risk, or acceptance criteria.

Do not modify project files until the user approves the concise design or explicitly waives this gate.

## Clarify Material Decisions

Ask only questions whose answers can change the design. Ask dependent questions sequentially; group independent questions when that is clearer and faster. State reasonable assumptions for immaterial unknowns instead of prolonging discovery.

Compare multiple approaches only when genuine trade-offs exist. Explain the meaningful differences and recommend one. When one approach is clearly appropriate, present that recommendation and its reasons without manufacturing alternatives.

## Propose and Approve the Design

Tailor the design to the task, covering only the useful parts of:

- Goal, scope, and non-goals.
- Affected components and their responsibilities.
- Interfaces, data flow, state changes, and compatibility boundaries.
- Failure handling, migration concerns, and verification strategy.
- Key risks, assumptions, and unresolved decisions.

Present the design concisely and wait for user approval before implementation. If feedback changes a material decision, revise the design and request approval again.

## Persist Complex Designs

After the concise design is approved, write a persistent spec when it materially improves understanding of architecture, module relationships, interfaces, or long-term decisions. Use an existing repository documentation convention only when it is Neo-compatible and is not tied to the original Superpowers product name. If the only convention is under `docs/superpowers/`, or no convention exists, use:

`docs/specs/YYYY-MM-DD-<topic>-design.md`

Obtain user approval of the written complex-task spec before implementation. Do not make a spec-only commit; include the spec in the later implementation commit. An explicit user waiver may skip the design or spec gate the user names.

When approved execution is multi-step, high-risk, cross-module, multi-session, or intended for handoff, use `superpowers-neo-writing-plans`.
