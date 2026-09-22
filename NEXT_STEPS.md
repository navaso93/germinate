# Germinate next steps 08/09/2026

- [FABIO] **Adjust filters** — Tune `config/rules.json` using real examples of useful grants and unwanted results. Define eligibility, geography, funding type, topics, and deadline requirements. Review whether rejection terms appearing anywhere on a page should reject an otherwise relevant grant.
- [FABIO] **Adjust the prompt** — Update `agent/prompt.md` to reflect the agreed criteria, distinguish open calls from general funding information, and preserve `review` for missing evidence. Add representative cases to `evals/examples.jsonl` to check the changes.
- [MARC] **Define costs and recurrence of runs** — Measure pages analyzed and actual API token usage in a representative run, then estimate per-run and monthly costs using verified model pricing. Agree a budget, frequency, timezone, and execution host before enabling a schedule. Current limits are 25 agent-analyzed pages per run, 30,000 characters per page, and 1,600 output tokens per request; these are limits, not a cost estimate.
- [FABIO] **Adapt URLs to better target websites and content** — Verify source-specific call and funding pages and prefer these over broad homepages. Review crawl depth and page limits, handle relevant start pages as opportunities where appropriate, and implement dedicated collectors for interactive sources.
- [FABIO] **Increase search and counting effectiveness** - Apply other scoring criteria e.g. when word "deadline" is detected, automatically send page to agent. Fabio to discuss wiht team.

Suggested implementation order: target URLs → filters → prompt → representative run and cost measurement → Drive delivery → recurring runs.

Decisions still needed: exact selection criteria, destination Drive folder, snapshot versus replacement behavior, run frequency, monthly budget, and execution host.

# Call 15/09/2026

## Distinguish "searchable" web URLs
Fabio to indicate which URLS include search options, which might make collecting of information harder.
Need to be able to instruct collector how to search for financing options in such websites.
Tell agent, in each URL, what words to look for.
Important to distinguish sites that allow for "free searchbar" VS "pre-defined search" e.g. checkboxes of different areas.
Affected URLs by this are marked with (Marc).
Ideally, algorithm can separate pages with and without search option.

## Land the file directly in Google Drive
Add delivery of the generated CSV to a chosen Drive folder. Decide whether each run creates a dated snapshot or updates one stable file; configure authentication and report upload failures clearly.

## PREVIOUS CHECKS
- [FABIO] **Adapt URLs to better target websites and content** — DONE
- [FABIO] **Adjust filters** - Pending search sites URL tasks above
- [FABIO] **Adjust the prompt** — Pending search sites URL tasks above
- [FABIO] **Increase search and counting effectiveness** - Not needed if criteria for agent search is correct.
