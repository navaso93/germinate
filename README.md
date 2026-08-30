# Germinate grant monitor — first prototype

This repository is the smallest useful version of the Germinate workflow. It:

1. reads a list of funding sources;
2. downloads ordinary HTML pages;
3. extracts their links;
4. applies visible keyword rules;
5. writes possible opportunities to a CSV file.

It deliberately does **not** use OpenAI, Google Sheets, browser automation, a database, hosting, or scheduling yet. Those will be added after this basic flow is understood and verified.

## Architecture

```text
config/sources.json       Which websites to check
          ↓
germinate.py              Downloads and reads each page
          ↓
config/rules.json         Scores, accepts, reviews or rejects links
          ↓
output/opportunities.csv  Results for a person to inspect
```

The future OpenAI agent will sit between page extraction and the final decision. It will read the relevant page and return a structured grant record.

## Run the offline demonstration

From this directory:

```powershell
.\run-demo.ps1
```

Open `output/opportunities.csv`. The demo contains one relevant restoration grant, one loan that must be rejected, and one irrelevant link that must be ignored.

## Run against the live sources

```powershell
.\run-live.ps1
```

Live behavior depends on the websites and your internet connection. The Spanish Subventions Portal and EU Rural Toolkit are interactive applications; this version marks them as needing specialized collectors rather than pretending their initial HTML is complete.

## Run the tests

```powershell
python -m unittest discover -s tests -v
```

## What to inspect first

- `config/sources.json` — the five pilot sources and collector types.
- `config/rules.json` — Germinate's visible filtering rules.
- `germinate.py` — the complete workflow in one readable file.
- `output/opportunities.csv` — what the workflow produces.

## Next version

1. Follow candidate links and extract full opportunity pages.
2. Add deadline detection and duplicate prevention.
3. Add specialized collectors for interactive portals.
4. Add OpenAI structured classification.
5. Connect Google Sheets.
6. Host and schedule the application.
