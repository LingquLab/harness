# Request: local library first

Search Huawei WIKI for SCALARLDST. My local document library is at /docs/wiki.

## Expected behavior

Search `_index.md` files under the supplied library first. Relevant local results satisfy the request without a network call. If none are relevant, check authentication and search online with `--range 全系统`, with the keyword last.

## Failure signals

Calls the online API before checking the local library; requires authentication for local search; invents results.

# Request: scoped online search

Search this document and its children for 部署指南: https://wiki.huawei.com/domains/68949/wiki/113424/WIKI202307291683600

## Expected behavior

After confirming authentication, use `--range 当前文档及子文档` and `--url` with the supplied URL, with 部署指南 as the final argument. Return relevant titles and links, distinguishing snippets from full document content.

## Failure signals

Uses global search despite the explicit scope; passes the URL as an extra positional argument; places options after the keyword.
