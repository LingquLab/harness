# Code Simplification Before Review

## Skills Under Test

- `superpowers-neo-code-simplification`
- `superpowers-neo-requesting-code-review`
- `superpowers-neo-git-delivery`

## Request A: Simplify Before a Risk-Driven Review

A cross-module feature is implemented with passing focused tests and task-owned uncommitted changes. The diff contains unnecessary nesting and a one-use wrapper, while the workspace also contains unrelated user changes. The feature is ready for automatic Git delivery on an established task-owned non-default branch.

## Expected Behavior A

- Limit simplification to the task-owned diff and preserve the unrelated workspace changes.
- Simplify only clear behavior-preserving opportunities; preserve interfaces, error behavior, side effects, ordering, logging, and edge cases.
- Search repository references before deleting the wrapper or apparently unused code.
- Re-run checks invalidated by simplification.
- Review the final simplified diff and current evidence, using independent review because the change is cross-module.
- Evaluate review feedback before applying it, then refresh simplification and validation only for material follow-up code changes and perform a final main-agent diff review.
- Stage and commit only after the simplified final diff has current verification and review evidence.

## Failure Signals A

- Reviewing or committing the pre-simplification diff.
- Expanding cleanup beyond the task-owned change or modifying unrelated user work.
- Changing behavior, public interfaces, tests, or error handling merely to reduce code size.
- Deleting code without checking dynamic and repository consumers.
- Treating stale verification as evidence after simplification.
- Committing feedback-modified code without a final main-agent review of the resulting diff.
- Requiring repeated simplification or independent review when no code changed and risk does not justify it.

## Request B: Already-Clear Small Change

A narrow local fix is correct, readable, and covered by a focused test. No simplification opportunity would improve clarity without widening the diff.

## Expected Behavior B

- Treat a no-op simplification pass as valid and leave the code unchanged.
- Reuse current verification when the no-op invalidates nothing.
- Perform a main-agent review of the final diff without requiring an independent reviewer solely because delivery is automatic.

## Failure Signals B

- Manufacturing churn, abstraction, or line-count reduction to make the simplification pass visible.
- Re-running unaffected checks or requiring an independent reviewer by rote.
- Blocking delivery because simplification made no edit.

## Request C: README for Product Users

A plugin README opens with its upstream commit, migration history and internal
fallback order. The user asks for a useful introduction and installation guidance.
A required third-party license notice and operator setup instructions already exist.

## Expected Behavior C

- Apply the documentation pass even when the change contains no code.
- Explain capabilities, suitable tasks, setup and usage before implementation details.
- Describe each plugin by the problem it solves, keeping source-priority mechanics
  in usage guidance only when they affect user choices.
- Move provenance and maintenance detail to linked dedicated documents, preserving
  required license notices and instructions operators need.
- Keep translated guides consistent and verify links and examples.

## Failure Signals C

- Merely rephrasing commit hashes, adaptation history or fallback order as the introduction.
- Removing required attribution, dependencies or useful operational instructions.
- Inventing capabilities or rewriting unrelated documents.
