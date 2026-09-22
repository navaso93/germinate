# Configuration guide

This guide explains the JSON files in this folder. Keys are the names on the left of each colon. Files ending in `.example.json` are templates; editing them does not change a live run.

## How ayudas are selected

1. `sources.json` chooses the websites and how to collect their pages.
2. `rules.json` checks for funding words, relevant topics, and exclusion words.
3. `agent.json` controls optional AI review. The AI selection instructions are in `agent/prompt.md`, outside this folder.
4. Results are saved to `output/opportunities.csv`. Drive upload is optional.

The intended focus is non-repayable funding for sustainability, restoration, biodiversity, agriculture, and related community work. The current word rules are only a preliminary check.

## sources.json

Purpose: list the websites to check. Each object describes one source.

- `name`: the source name shown in the results.
- `collector_type`: how the website is read.
    - `html` follows links on ordinary pages.
    - `html_search` submits keyword searches through URLs.
    - `interactive_search` flags a site that still needs a dedicated collector; it does not search it yet.
- `start_urls`: starting pages for ordinary collection. For `html_search`, the requests use `search.url` instead.
- `max_depth`: how many link levels to follow. `1` reads pages linked directly from a starting page. `2` follows one more level. Default: `2`.
- `max_pages`: maximum pages visited per source, shared across all its searches and starting URLs. Search pages and failed fetches count too. Default: `30`.
- `notes`: information for people reading the file. It does not change collection or instruct the AI.
- `search`: settings for a source using `html_search`.
- `search.url`: the website's actual search address.
- `search.query_parameter`: the website's internal keyword field name. RED PAC uses `title`.
- `search.keywords`: phrases to search separately. Three phrases produce three search requests. Use `[]` for one request without a keyword filter.
- `search.parameters`: extra website filters applied to every search. Use the website's real field names and values. A list sends several values together; it does not create separate searches.
- `search.result_container_class`: optional HTML class identifying the results area. It helps exclude navigation links. A missing configured container produces an error.

Normally, the collector follows same-site links containing funding or topic words and no exclusion words. With a configured search results container, it follows same-site links in that container even if their titles are generic. It then applies the rules to the full page text. Starting/search pages are not themselves exported as opportunities.

Searches share a page budget, so an early search can use it up. Automatic pagination and JavaScript-only or POST search forms are not supported by the current generic collector.

## search-source.example.json

Purpose: template for adding one searchable website to `sources.json`.

- It uses the same source and `search` keys explained above.
- Copy the object into the list in `sources.json`, then replace the example values.
- `parameters.type: "grant"` is only an example filter. It is not a universal website setting.

## rules.json

Purpose: define the word-based checks used before AI review.

- `grant_terms`: words suggesting a grant or funding opportunity.
- `topic_terms`: words suggesting a relevant theme.
- `rejection_terms`: words that currently trigger automatic rejection.
- `minimum_score`: minimum score for a `candidate`. Funding and topic matches are also required. Current value: `3`.

Score = 2 × funding matches + topic matches − 4 × exclusion matches.

- `candidate`: funding and topic words matched, the score meets the threshold, and no exclusion word matched.
- `rejected`: at least one exclusion word matched, regardless of score.
- `review`: some words matched, but the candidate conditions were not met.
- No matches: the page is not included as a result.

Matching ignores letter case and looks for text fragments, not meaning. It checks the title, URL, and full extracted page text, which can include navigation. For example, `crédito presupuestario` and `Fondo Europeo Agrícola de Garantía` currently cause false rejections. These decisions do not confirm actual eligibility. Rejected rows remain in the CSV.

## agent.json

Purpose: control optional AI analysis of collected pages.

- `enabled`: `true` enables AI analysis. `false` leaves it off unless you run with `--agent`.
- `model`: the model identifier sent to the API.
- `minimum_confidence`: answers below this value become `review`. Current value: `0.8`.
- `max_pages_per_run`: maximum successfully analyzed pages per run. Current value: `25`. Failed attempts do not count, so this is not a strict request or cost limit.
- `max_page_characters`: maximum characters of page text sent for each analysis. Current value: `30000`.
- `max_output_tokens`: maximum output-token allowance per model request. Current value: `1600`.
- `timeout_seconds`: timeout used for each API request. Current value: `60` seconds.

Only rule-based `candidate` and `review` rows reach the AI. Rule-based rejections are skipped. AI results appear alongside the original rule results; they do not remove rows from the CSV.

## sheets.json

Purpose: choose the Google Sheet containing website URLs to import into `sources.json`. This is an input, not the destination for results.

- `spreadsheet`: Google Sheet URL or spreadsheet ID.
- `tab`: exact worksheet name to read.
- `column`: column letter containing URLs or linked names, such as `A`.
- `start_row`: first row to read. `3` skips two heading rows.
- `access`: `public` reads without signing in. `private` uses configured Google credentials with read-only access.

Run `python sync_sources.py` to preview new sources. Add `--apply` to save them. The import preserves existing settings and does not remove old URLs. Cells without URLs are reported and skipped. The Google Sheet is never edited.

## drive.example.json and drive.json

Purpose: configure where result CSV files are uploaded. Copy `drive.example.json` to `drive.json` to activate the configuration; the example alone is not used.

- `enabled`: `true` uploads after live runs. `false` uploads only when explicitly requested with `--drive`.
- `folder`: destination Google Drive folder URL or ID.
- `client_secrets_file`: path to the Google OAuth client file used when connecting your account.
- `token_file`: path where the saved Google authorization is stored.

Relative credential paths start at the project root. Complete `python drive_upload.py --authorize` before uploading. Each upload creates a dated CSV and keeps the local copy. Ordinary demo runs do not upload. Without `drive.json`, results stay local.

## Publication-date window: proposed, not active

- `publication_filter`: proposed source setting for filtering by publication date. The current program does not read this key.
- `publication_filter.last_days`: proposed rolling window, such as `90` for publications dated on or after today minus 90 days.

The RED PAC 90-day count was a separate diagnostic, not an implemented live-run filter. Publication date is different from application deadline. Recent entries may already be closed or may be amendments to older calls.


## website-filters.json

Purpose: keep filter definitions for multiple websites in one file. The future UI can use these definitions to display each website's fields and options. Active selections still belong in `sources.json`; changing this reference alone does not change searches.

- `websites`: list of website definitions. Add one object for each supported website.
- `source_name`: exact matching `name` in `sources.json`, such as `RED PAC`.
- `url`: the website's search address, for reference.
- `filters`: the website's fields, keyed by their internal parameter names.

Each website has its own filter names and value codes. For example, a code meaning Cataluña on RED PAC may mean something different elsewhere. Copy the website structure when adding another site, but verify its actual fields and values.

### RED PAC example

The first website entry is RED PAC. Edit its entry in `sources.json` to change these selections:

- `field_territorial_scope_target_id`: Ámbito territorial. `"All"` leaves territory unrestricted. `"11"` selects national-level calls, not every region. `"21"` selects Cataluña. All available codes are in the reference file.
- `field_call_year_value`: Año convocatoria. Use a year such as `"2026"`, or `""` for no year restriction. This is not publication date or a rolling window.
- `field_ifgc_value`: Mecanismos de apoyo. `"0"` selects Ayudas / Intervenciones / Subvenciones. `"1"` selects Instrumentos Financieros de Gestión Centralizada. `"All"` selects either.
- `title`: Buscar un término. Set `query_parameter` to `"title"` and edit `keywords`. Each phrase is a separate search. `[]` leaves the keyword field empty.

Current defaults: any territory, any year, aid mechanism `"0"`, and the existing three keywords. All filters apply together in each request. Dropdown selections do not replace our later classification rules.

Example: Cataluña, call year 2026, grants, without keyword filtering:

```json
"search": {
  "url": "https://redpac.es/buscador-ayudas",
  "query_parameter": "title",
  "keywords": [],
  "parameters": {
    "field_territorial_scope_target_id": "21",
    "field_call_year_value": "2026",
    "field_ifgc_value": "0"
  },
  "result_container_class": "view-id-ayudas"
}
```

Each field inside a website's `filters` uses these metadata keys:

- `label`: field name displayed on the website and usable in our future UI.
- `type`: suggested UI input: `select`, `text`, or `list`.
- `config_key`: where the selected value belongs in the source configuration.
- `options`: available dropdown codes and their readable labels.
- `empty_value`: value to use when no filter is wanted.
- `example`: an example input, not an active setting.
- `query_parameter`: website field receiving each keyword.

Codes were checked against https://redpac.es/buscador-ayudas on 20 September 2026. RED PAC dropdown codes are stored as strings. A future UI can match `source_name`, read that website's `filters`, and save its selected values into the matching entry in `sources.json`. No UI or automatic code validation is implemented yet.
