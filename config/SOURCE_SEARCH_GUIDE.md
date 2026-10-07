# Searching funding websites

RED PAC, EU Rural Toolkit, Cascade Funding and IPYME belong to the same group: websites requiring search or filtering to discover grants. Each has its own search fields, retrieval logic and criteria. A shared configuration structure or run command would coordinate these adapters; it would not make their criteria identical.

| Website | Active configuration | Search implementation |
| --- | --- | --- |
| RED PAC | `sources.json`, entry named `RED PAC` | `collectors/search.py` and `germinate.py` |
| EU Rural Toolkit | `site-searches.json`, `id: rural_toolkit` | `collectors/funding.py`, `collect_rural` |
| Cascade Funding | `site-searches.json`, `id: cascade` | `collectors/funding.py`, `collect_cascade` |
| IPYME | `site-searches.json`, `id: ipyme` | `collectors/funding.py`, `collect_ipyme` |

Definitions and dropdown labels for all four are in **website-filters.json**. Edit each website's active configuration to change its searches. The two existing runners are described below.

## Run

The following commands run the three `site-searches.json` adapters. RED PAC uses the separate command in its section below.

Install PDF support once: `python -m pip install -r requirements.txt`.
Set OPENAI_API_KEY in .env. Then run:

```powershell
python run_sources.py
python run_sources.py --source ipyme
python run_sources.py --source cascade --source rural_toolkit
python run_sources.py --collect-only
```

The full run uses the configured model in agent.json. It assesses every retained candidate, including rule-rejected candidates; agent.json's old 25-page cap does not apply here. The initial keyword score is audit information only. The shared agent/prompt.md plus the instructions in run_sources.py control semantic assessment. They reject loans/equity, procurement, directories and courses without financial grants. A public-budget allocation called "crédito" is not automatically a loan.

## Shared criteria for the three site-searches.json adapters

These settings live in `site-searches.json.common`. They currently apply to Rural Toolkit, Cascade and IPYME, not the RED PAC runner. Website-specific search criteria are explained separately below.

- `publication_last_days`: rolling publication window, currently 90 days. Both boundary dates are included. On 5 October 2026 this means 7 July–5 October.
- `missing_publication`: `include_if_open` keeps calls with confirmed open applications when the publication date is unavailable. Set `exclude` to require a verified publication date. Missing dates stay blank.
- `exclude_closed`: exclude explicitly closed calls and deadlines before the run date. A deadline today is retained; time-of-day cutoffs are not evaluated.
- `topic_terms`: case-insensitive topic fragments for IPYME and linked Toolkit pages. Any one match passes this discovery check. The model then checks the actual thematic fit. Cascade uses its domain filters instead.
- `max_document_bytes`: maximum linked-document size, currently 15 MB. The Toolkit application bundle separately allows up to 30 MB.
- `max_pdf_pages`: maximum PDF pages extracted, currently 80. Scanned PDFs without text are reported; OCR is not implemented.
- `max_linked_documents`: documents attempted per candidate, currently one. Cascade prefers guidelines, then the official website. IPYME uses its official factsheet. Toolkit uses linked applicant/call PDFs.

The publication window is applied again after model extraction. An open call with a known publication date older than 90 days is excluded. Opening dates, deadlines, database timestamps, amendments and legal-base dates are not substitutes for publication. PDFs contribute at most 45,000 characters and total model evidence at most 60,000; truncation is flagged in the evidence/notes.

## Each website entry

The following three keys describe entries in `site-searches.json`. RED PAC currently uses the `sources.json` keys explained in its own section.

- `id`: adapter identifier: `rural_toolkit`, `cascade` or `ipyme`.
- `name`: source name in the audit.
- `url`: public starting page.

### RED PAC

**Active settings:** the entry named `RED PAC` in `sources.json`. **Logic:** `search_urls` in `collectors/search.py` builds GET search URLs; `crawl_start_url` in `germinate.py` reads the results and linked pages.

RED PAC's form filters a catalogue of ayudas. The collector sends the website's own parameter names, rather than searching with a model or typing into a browser.

- `collector_type: "html_search"`: use URL-based searches.
- `search.url`: `https://redpac.es/buscador-ayudas`.
- `search.query_parameter: "title"`: the website's **Buscar un término** field.
- `search.keywords`: currently `rural`, `agricultura`, `biodiversidad`. Each word creates a separate request; their results are combined and duplicate URLs removed. Use `[]` for one request without a keyword filter. This does not guarantee that all catalogue pages will be collected.
- `search.parameters.field_territorial_scope_target_id`: **Ámbito territorial**. Currently `"All"`, meaning no territory restriction. `"11"` means national-level calls; `"21"` means Cataluña. Other codes are in `website-filters.json`.
- `search.parameters.field_call_year_value`: **Año convocatoria**. Currently `""`, meaning any year. `"2026"` would select that call year. This is not a publication-date filter.
- `search.parameters.field_ifgc_value`: **Mecanismos de apoyo**. Currently `"0"`, meaning Ayudas / Intervenciones / Subvenciones. `"1"` selects centrally managed financial instruments; `"All"` leaves this field unrestricted.
- `search.result_container_class: "view-id-ayudas"`: read links from the results area instead of unrelated navigation.
- `max_depth: 1`: read pages directly linked from each search page; do not traverse their further links.
- `max_pages: 30`: shared page budget for all RED PAC searches, including search pages and failed requests. An earlier keyword can exhaust the budget before later searches run.
- `start_urls`: reference starting address; `html_search` actually requests `search.url` with the configured parameters.

The same territory, year and support filters apply to every keyword request. For example, the first request uses `title=rural`, territory `All`, a blank call year and support code `0`. These filters combine within a request; the three keywords are separate searches, not a requirement that a page match all three.

**Current limits:** the generic collector does not traverse results pagination automatically or extract linked PDFs. It applies `rules.json` to page text. With AI enabled, only rule `candidate`/`review` rows reach the model, up to `agent.json.max_pages_per_run` (currently 25 across the whole run). Rule-rejected rows are skipped by AI, and the standard CSV still retains rejected rows.

**Publication dates:** the earlier RED PAC 90-day test was a separate run. The standard `sources.json` / `germinate.py` workflow has no active rolling publication-date filter or closed-call exclusion. Editing `site-searches.json.common` does not change RED PAC. The previous test's no-keyword settings also differ from the three keywords currently saved in `sources.json`.

`python germinate.py --agent` runs the original workflow, including RED PAC and the other entries in `sources.json`; it is not a RED PAC-only command. `run_sources.py` currently has no RED PAC adapter. A future shared runner should preserve the RED PAC-specific fields and collection logic.

### EU Rural Toolkit

The finder lists programmes, not individual grants. The collector reads its embedded datasets without executing JavaScript, selects matching programmes, then follows official call links. Programme budgets never become grant amounts.

- `support_code`: `1` means Grant. Other support types are not implemented as grant searches.
- `activity_codes`: any selected activity can match. Defaults: `2` agriculture/farming/forestry/fishing; `4` climate adaptation/mitigation; `9` energy; `11` environment/biodiversity/waste; `14` integrated local development.
- `applicant_codes`: any selected applicant type can match. Empty means all. `1` academic; `2` civil-society association; `3` business/SME/farmer; `4` cooperative; `5` energy community; `6` individual; `7` Local Action Group; `8` local authority/public entity; `9` NGO.
- `max_listing_pages`: maximum pagination depth per linked listing, currently five.
- `max_call_pages`: maximum distinct linked detail pages, currently 100. Reaching the limit is reported as incomplete coverage.
- `call_url_overrides`: replacements for outdated official catalogue links. Currently fixes Interreg's old calls URL.

Within each multiselect the relationship is OR; support, activity and applicant conditions combine with AND. Full verified activity labels are in website-filters.json. EIT discovery is restricted to individual `/our-activities/opportunities/` pages. The model removes remaining directories, archived calls and unrelated opportunities.

Coverage is partial: EU Funding & Tenders' dynamic portal needs a dedicated adapter; national/regional portals linked by a programme are not exhaustively traversed. Blocked pages and unsupported portals are recorded in collection-report.json, not counted as empty searches.

### Cascade Funding

The collector reads all proposal records embedded in the Open Calls page, so it does not stop at the first visible cards. Evaluator and mentor listings are excluded.

- `call_type`: `Proposals` selects calls for funding proposals.
- `domains`: allowed sectors. Defaults: agriculture/food, circular economy/sustainability, energy/environment, social innovation/community development.
- `technologies`: optional technology tags. Empty means all.
- `beneficiaries`: optional applicant tags. Empty means all.

Any selected value within a field matches; different fields combine with AND. Tag comparisons are case-insensitive. Current dropdown labels are stored in website-filters.json and may need updating when the website adds tags. `created_time` is deliberately not treated as publication. An Open Calls listing supplies provisional opening evidence; contrary official evidence takes precedence.

### IPYME

The collector uses the same public API as the search UI, fetches every results page, then the detailed record and PDF factsheet.

- `api_url`: public API base address used by the website.
- `query`: Spanish search expression. `o` means OR. Defaults cover agriculture, rural development, sustainability, biodiversity, forestry, water, climate, agrovoltaics, circular economy and renewables.
- `only_open`: sends `enPlazo=true` to the website's search.
- `grant_types`: allowed fragments in the aid type. Currently `subvención`. Mixed aid types reach the model for assessment.
- `page_size`: records per API page, currently 50. Pages start at zero.
- `max_listing_pages`: safety limit, currently 30. Missing results or an early limit are reported.

Publication comes from official bulletin entries marked exactly `Convocatoria`; bases and amendments do not reset the date. Contradictory listing/detail opening flags produce `Pendiente`. The model can select an earlier first-stage application deadline from official text. Total programme appropriations and general de-minimis ceilings are not automatically the maximum award per applicant.

## Model, output and repeat runs

This section describes `run_sources.py` for Rural Toolkit, Cascade and IPYME. RED PAC runner differences are listed above.

- `--as-of YYYY-MM-DD`: reproducible assessment date; defaults to today's local date.
- `--workers`: parallel model calls, one to four; default three.
- `--config`: alternative site-searches.json.
- `--output-dir`: parent directory for run files.
- `--refresh-collection`: rebuild collected records from the same run's downloaded files. Use after editing collector code. A new date/config creates a new run directory and downloads again.
- `--existing-csv PATH`: exclude URLs already in an exported existing table. It supports title rows above the header. Different URLs for the same grant still need review.

Files are saved under output/multi-source/<date>-<config hash>/. `append.csv` uses the same 18 columns in output-columns.json. It contains model accept/review rows passing the date policy. The three manual columns remain blank. `assessments.json` stores answers, evidence links and exclusion reasons; `all.audit.csv` keeps raw fields; `collection-report.json` records discovery counts and coverage gaps; `model-errors.json` records unfinished assessments.

Successful model answers are cached by evidence, prompt, schema, model and date. Rerunning resumes unfinished assessments. Temporary model errors are retried up to three times. Exit code 2 means incomplete coverage or failed assessments; inspect reports even when an export exists.

**Google Sheets:** this command prepares a local append file. It does not automatically write to a Google Sheet or replace its existing table. Appending to the existing `Pre-lista ayudas TEST` tab requires a connected Google Drive/Sheets editor. Preserve existing rows/manual entries, check duplicate URLs against a fresh table export, and extend the existing table to include appended rows. The separate drive_upload.py command uploads a new CSV file to a Drive folder; it does not edit a Sheet tab.

Filter labels were checked on 5 October 2026. They are documentation for a future UI, not an implemented UI or a guarantee that website values never change.
