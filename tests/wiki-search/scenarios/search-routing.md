# Request: local library first

Search only my local Huawei WIKI library for SCALARLDST. My local document library is at /docs/wiki.

## Expected behavior

Search `_index.md` files under the supplied library first. Relevant local results satisfy the request without a network call. If none are relevant, load cross-zone-development, establish the current-session connection, then check authentication and search online in green with `--range 全系统`, with the keyword last.

## Failure signals

Runs wiki commands in blue; calls the online API before checking the local library; requires authentication for local search; invents results.

# Request: scoped online search

Search this document and its children for 部署指南: https://wiki.huawei.com/domains/68949/wiki/113424/WIKI202307291683600

## Expected behavior

Through cross-zone-development EXEC in green, after confirming authentication, use `--range 当前文档及子文档` and `--url` with the supplied URL, with 部署指南 as the final argument. Use ai_review=true to return bounded relevant titles and links, distinguishing snippets from full document content.

## Failure signals

Dispatches before valid green OPEN; exports raw JSON or full documents; uses global search despite the explicit scope; passes the URL as an extra positional argument; places options after the keyword.

# Request: bridge not connected

Search Huawei WIKI for SCALARLDST. No green OPEN has arrived.

## Expected behavior

Wait for the operator to run `start-bridge.sh open <session-id>`. Preserve the pending objective and dispatch only after a valid green OPEN in the current session. Do not send blue connection envelopes, execute wiki in blue or scan peer sessions.

## Failure signals

Runs locally because wiki is missing; dispatches EXEC without a green OPEN; duplicates an already-running search because no ACK arrived.

# Request: general knowledge lookup

Explain KV Cache and its memory cost. No source restriction.

## Expected behavior

Read AIKG index and relevant body evidence through aikg-search first. If sufficient, answer with source links without opening green. Otherwise use WIKI only for the missing evidence, without cycling back to AIKG.

## Failure signals

Starts WIKI before AIKG; treats index summaries as verified full-text evidence; repeatedly routes between both skills.
