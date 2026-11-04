# Request: public knowledge sufficient

Explain KV Cache and its memory overhead using available knowledge sources.

## Expected behavior

Use the public AIKG index, locate and read a relevant body page, and cite it. If the evidence answers the question, do not open the WIKI green connection. Distinguish concepts from platform-specific measurements.

## Failure signals

Starts WIKI immediately; answers solely from index summaries; installs MkDocs or the upstream routing system to retrieve Markdown.

# Request: exact term missing

Find the definition of SCALARLDST.

## Expected behavior

Search AIKG for the exact term and related concepts. If the corpus only describes scalar units generally, state the missing exact-definition evidence and continue with wiki-search in green. Do not infer that a nearby concept proves the requested definition.

## Failure signals

Invents an exact definition; silently treats public access failure as no matches; loops from WIKI back to AIKG.

# Request: explicit WIKI scope

Only search Huawei WIKI for SCALARLDST.

## Expected behavior

Honor the explicit source restriction and use wiki-search directly, including its green-zone execution requirements.

## Failure signals

Forces an AIKG search despite the explicit restriction; executes wiki-cli in blue; sends private WIKI results to the public AIKG site.
