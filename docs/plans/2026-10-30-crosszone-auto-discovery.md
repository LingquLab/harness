# Crosszone automatic session discovery

Approved scope: the operator starts one default Bridge without a session; blue
sends OPEN in its current session, green binds and returns READY. One session at
a time, BUSY for competing sessions, CLOSE when idle. Existing explicit-session
commands remain available for independent multi-session workers. Preserve main's
concurrent task execution, durable receipts, recovery and reviewed egress.

Implementation contract:

1. Add separate strict blue connection envelopes (OPEN/CLOSE: protocol, type,
   event_id); keep legacy green OPEN unchanged. Replies READY/BUSY/CLOSED bind
   request_event_id and the receiving session, never disclose another session.
2. Add a discovery supervisor with durable per-session cursors, binding and
   reply outbox. Baseline existing history on first start; poll visible sessions
   every poll_seconds (default 5). SSE accelerates the bound session. Recover
   the binding and retry replies after restart without replaying work. Hold a
   discovery process lock and the existing session lock when bound.
3. CLI/launcher: no arguments selects discover; explicit open/run remain
   unchanged. Extend watchdog to default discovery. Release only after no queued,
   running, waiting, pending result or unresolved recovery remains.
4. Update skill, role/protocol references and English/Chinese operator docs;
   distinguish automatic blue OPEN from explicit green OPEN.
5. Verify discovery and bound dispatch with fake HAPI integration, stale-history
   exclusion, competing sessions, duplicates, restart, send failure, session locks,
   release and existing explicit launcher regressions. Run full plugin suite and
   repository crosszone contract checks. Independently review risky state paths.

Ownership: main agent owns runtime, launchers and discovery tests. A documentation
agent may own README*, skills/cross-zone-development/** and repository contract
tests only. No live HAPI messages or green operations are needed. Existing
worktrees remain untouched. This is a durable implementation/maintenance plan.

## Verification and review

- Runtime suite: 197 tests passed, including 22 automatic-discovery regressions.
- Repository crosszone contract: 8 tests passed. Skill validator, shell syntax
  checks and git diff whitespace checks passed.
- Independent review identified a TASK/CLOSE arrival race and reply starvation
  behind a failed session. CLOSE now catches up through its message position;
  reply queues drain independently per session. Both have regression coverage.
- Marketplace validation has an unchanged main-branch failure: marketplace.json
  advertises cross-zone 0.4.0 while its ZCode manifest is 0.5.2. Neither release
  metadata nor the validator was changed by this task.
- No live green Windows/HAPI deployment was used; tests exercise isolated HAPI
  fakes, real Bridge state/dispatch and existing HTTP/SSE transport regressions.
