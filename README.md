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

Every run replaces `output/opportunities.csv` with a new snapshot. It does not append to the previous file. This avoids accumulating duplicate and outdated results. A later version can keep historical runs in a database or a separate history table.

## Output columns

| Column | Meaning |
| --- | --- |
| `source` | Funding website where the link was found. |
| `collector_type` | Collection method assigned to the source, currently `html` or `interactive_search`. |
| `title` | Visible text of the link found on the source page. It is not yet a verified opportunity title. |
| `url` | Destination of the extracted link. |
| `decision` | Rule-based result: `candidate`, `review`, `rejected`, or `needs_specialized_collector`. |
| `score` | Simple keyword score: grant terms add 2 points, topic terms add 1, and rejection terms subtract 4. |
| `matched_grant_terms` | Grant-related words detected in the link title or URL. |
| `matched_topics` | Sustainability-related words detected in the link title or URL. |
| `rejection_terms` | Words such as `loan`, `equity`, or `procurement` that triggered rejection. |
| `checked_at` | UTC date and time when the collector ran. |
| `note` | Human-readable explanation of the decision or collector limitation. |

This first version classifies only the visible link text and URL. It does not yet open every candidate page to understand its complete content, confirm deadlines, or verify eligibility.

## How decisions are currently made

There is no AI agent in this version. `germinate.py` reads the editable terms in `config/rules.json` and applies this transparent formula:

```text
grant term       +2 points
relevant topic   +1 point
rejection term   -4 points
```

- A grant term plus a relevant topic with a sufficient score becomes `candidate`.
- A rejection term such as `loan` makes the result `rejected`.
- Partial evidence becomes `review`.
- Interactive portals become `needs_specialized_collector`.

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
