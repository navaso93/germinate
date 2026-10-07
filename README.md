# Germinate grant monitor

Collect funding opportunities, assess them with an OpenAI model, and export the agreed Spanish columns. Runs execute locally and on demand.

## Start here

- [Search guide](config/SOURCE_SEARCH_GUIDE.md): how each of the four searchable websites works, filters and limitations.
- [Configuration guide](config/README.md): JSON keys and output column definitions.

There are currently two active collection workflows. They have different search logic; neither is obsolete.

| What to run | Command | Active settings |
| --- | --- | --- |
| Rural Toolkit, Cascade and IPYME, with model assessment | `python run_sources.py` | `config/site-searches.json` |
| One of those sources | `python run_sources.py --source ipyme` | Same file |
| Those sources without model assessment | `python run_sources.py --collect-only` | Same file |
| Original HTML workflow, including RED PAC | `python germinate.py --agent` | `config/sources.json` |
| Original workflow without the model | `python germinate.py` | Same file |
| Offline demonstration | `python germinate.py --demo` | `demo/sample_source.html` |

The original runner reads all entries in sources.json; it is not a RED PAC-only command. Its old entries for the three new adapters do not invoke their specialized collectors: use run_sources.py for those sites.

## Setup

Install Python 3.10 or newer and run these commands from the repository folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
# Only if .env does not already exist:
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in the local `.env` for model runs. Keep `.env` and credentials out of Git. The offline demonstration and collection-only runs do not need an API key. The single requirements file includes PDF extraction and Google integration dependencies.

To check the API connection with one small paid model request:

```powershell
python -m agent.smoke_test
```

The previous run-demo.ps1, run-live.ps1 and test-agent.ps1 launchers have been removed. Use the direct Python commands above. Python must be installed or otherwise available on PATH; the removed launchers' Codex-specific runtime fallback is no longer used.

## Where to change behavior

| File | Purpose |
| --- | --- |
| `config/sources.json` | Original HTML sources and RED PAC search parameters |
| `config/site-searches.json` | Specialized searches and date policy for the three newer adapters |
| `config/website-filters.json` | Website field labels and code meanings; not active selections |
| `config/rules.json` | Preliminary keyword scoring |
| `agent/prompt.md` and `agent/schema.json` | Model policy and structured facts |
| `config/agent.json` | Model and assessment settings |
| `config/output-columns.json` | Column names, order and field mappings |
| `collectors/` | HTML parsing, search URLs and specialized collection logic |
| `run_sources.py` / `germinate.py` | Collection, assessment and export orchestration |
| `output_columns.py` | Presentation values and audit export |
| `tests/` | Offline regression tests |
| `evals/examples.jsonl` | Small labelled examples for future model comparisons; not an automated evaluation runner |

The original runner sends only keyword `candidate`/`review` rows to the model, with a default limit of 25 successful assessments across the run. Its export keeps rejected rows. The specialized runner assesses every retained candidate and exports model accept/review rows that pass its date policy. Do not assume the original runner's model cap or the newer runner's date rules apply to both. See the search guide for source-specific details.

## Output and Google Sheets

Both workflows use the 18 columns in `config/output-columns.json`. Unknown facts and manual columns remain blank. `Max Budget (€)` is the supported maximum award per applicant/project in EUR. `Estatus` is `En curso` only when opening is confirmed; otherwise `Pendiente`. That label does not imply a closed call will reopen.

- Original runner: `output/opportunities.csv` plus `opportunities.audit.csv`. `--output PATH` changes the destination; `--columns-config PATH` changes the layout.
- Specialized runner: dated/config-specific folders under `output/multi-source/`, containing `append.csv`, raw assessments and coverage/error reports. Successful model responses are cached so retries can resume without repeating them.
- Local exports replace their own snapshots. They do not carry forward manual edits to previous CSV files.
- Appending to an existing Google Sheet currently uses the connected Google Drive plugin. Neither runner automatically edits a Sheet tab. Preserve existing rows and check duplicate URLs before appending.

Keep output folders when audit history or cached responses are needed. They are generated artifacts, not source code.

## Import website URLs from a Google Sheet

Create the ignored `config/sheets.json` with the input spreadsheet URL/ID, tab and URL column:

```json
{
  "spreadsheet": "YOUR_SPREADSHEET_URL_OR_ID",
  "tab": "Buscadores de financiaciones",
  "column": "A",
  "start_row": 3,
  "access": "public"
}
```

```powershell
python sync_sources.py          # preview
python sync_sources.py --apply  # merge into sources.json
```

Public import reads the XLSX export, including hyperlinks behind labels. Private import uses `access: "private"` and Google Application Default Credentials, for example a service account selected by `GOOGLE_APPLICATION_CREDENTIALS`. Enable the Sheets API and share the input spreadsheet with that account as Viewer. Store credentials outside Git. The importer preserves existing source settings; it does not remove old sources or configure new search adapters automatically. It never edits the input Sheet.

## Optional CSV upload to a Drive folder

This is separate from editing a Google Sheets tab. It creates a new dated CSV in a configured folder.

1. Copy `config/drive.example.json` to the ignored `config/drive.json` and set the folder URL/ID.
2. Enable the Drive API in a Google Cloud project. Create a Desktop OAuth client, configure its consent screen/test users as needed, and save the client file as `secrets/drive-client.json`.
3. Run `python drive_upload.py --authorize` and sign in with an account that can add files to that folder. This requests the full Drive scope and stores the token locally.
4. Set `enabled: true` for automatic original-runner uploads, or use an explicit command:

```powershell
python germinate.py --agent --drive
python drive_upload.py --file output/opportunities.csv
```

Without Drive configuration, results stay local. Normal demos do not upload. Upload failures preserve the CSV and return exit code 2; check the destination before retrying after a network interruption. Plugin sign-in does not configure this separate local OAuth integration.

## Development

```powershell
python -m unittest discover -s tests
```

Tests are offline and do not call the model. Use the [search guide](config/SOURCE_SEARCH_GUIDE.md) for reproducible dates, cache controls and source coverage reports. No scheduler, hosting service or model fine-tuning is configured.

Remaining work from the earlier planning notes:

- Fabio: tune source filters and model policy against reviewed grant examples, including keyword false rejections.
- Fabio: improve targeted URLs and coverage of dynamic portals and pagination.
- Marc: measure actual API usage/cost and agree the run budget, frequency, timezone and host before scheduling.
- Bring RED PAC into a shared run interface while preserving its own filters; implement its rolling-date policy in the normal workflow.
- Automate duplicate-aware appends to the chosen output Sheet if recurring delivery is required.
