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
The Chinese guide also replaces `token` with an unnatural literal translation.

## Expected Behavior C

- Apply the documentation pass even when the change contains no code.
- Explain capabilities, suitable tasks, setup and usage before implementation details.
- Describe each plugin by the problem it solves, keeping source-priority mechanics
  in usage guidance only when they affect user choices.
- Move provenance and maintenance detail to linked dedicated documents, preserving
  required license notices and instructions operators need.
- Keep translated guides consistent and verify links and examples.
- Preserve original English technical terms such as `token`; explain their meaning
  in Chinese when useful instead of forcing unnatural translations.

## Failure Signals C

- Merely rephrasing commit hashes, adaptation history or fallback order as the introduction.
- Removing required attribution, dependencies or useful operational instructions.
- Inventing capabilities or rewriting unrelated documents.
- Replacing `token` with a forced Chinese equivalent or using inconsistent terminology.

## Request D: Clear Chinese Code Comments

A bilingual Host API comment translates `opaque handle` as “不透明句柄” and
says destruction “coordinates internal resource cleanup”. The user asks for
clearer comments without changing behavior.

## Expected Behavior D

- Read the relevant implementation before describing destruction or ownership.
- Keep `opaque handle` in English and explain what callers can access.
- Replace vague coordination language with the actual calls, waits or releases
  supported by the code, without inventing ordering or synchronization guarantees.
- Keep both language versions accurate without requiring literal translation.

## Failure Signals D

- Merely replacing one awkward Chinese term with another literal translation.
- Claiming an unobserved wait, cleanup order or successful release guarantee.
- Changing runtime behavior to match a rewritten comment.
