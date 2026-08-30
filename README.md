# Germinate grant monitor

Germinate collects links from funding websites, applies inexpensive transparent rules, and can optionally ask an OpenAI model to verify and structure promising opportunities.

## How information moves

```text
config/sources.json → collectors → config/rules.json → optional OpenAI agent → output CSV
                                      ↓
                              only candidate/review pages
```

The **application/agent lives on the computer that runs this repository**. It is not hosted yet. The collectors communicate with funding sites over HTTPS. When enabled, `agent/client.py` communicates with OpenAI's Responses API over HTTPS. The final CSV remains local.

## Repository structure

- `germinate.py` — coordinates the complete workflow.
- `collectors/html.py` — downloads ordinary HTML, extracts links, and converts a page to text.
- `collectors/interactive.py` — explicit placeholder for dynamic sites requiring an API or browser automation.
- `config/sources.json` — sites, start URLs, and collector types.
- `config/rules.json` — visible first-pass grant, topic, and exclusion terms.
- `agent/client.py` — optional OpenAI Responses API connection.
- `agent/prompt.md` — Germinate's semantic selection policy.
- `agent/schema.json` — exact fields and allowed values the model must return.
- `config/agent.json` — model, confidence threshold, page/call limits, and timeouts.
- `evals/examples.jsonl` — human-labelled examples used to test future changes.
- `tests/` — automated code checks that do not call OpenAI.
- `output/` — generated CSV snapshots; CSV files are intentionally not committed.
- `.env.example` — safe template for local secrets. The real `.env` is ignored by Git.

## Run it

Offline demonstration, with no internet or API cost:

```powershell
.\run-demo.ps1
```

Live collection using deterministic rules only. It follows promising same-site links, reads their full page text, and stops at each source's `max_depth` and `max_pages` limits:

```powershell
.\run-live.ps1
```

Live collection plus agent analysis:

```powershell
Copy-Item .env.example .env
# Edit .env and replace the placeholder with your real key
.\run-live.ps1 -Agent
```

Test the agent with one small API call, without crawling live websites:

```powershell
Copy-Item .env.example .env
# Replace the placeholder in .env with your API key
.\test-agent.ps1
```

Create an API key in the [OpenAI API key dashboard](https://platform.openai.com/api-keys). Put only this in the uncommitted `.env`:

```dotenv
OPENAI_API_KEY=your_real_key
```

An API subscription is billed separately from a ChatGPT subscription. Never paste a key into source code or commit `.env`; use a secret manager when this is eventually hosted.

## What controls the results?

1. `sources.json` controls **where** Germinate searches.
2. Each collector controls **how** a source is read.
3. `rules.json` controls which links are followed and classifies their full page text.
4. `prompt.md` explains what Germinate considers an acceptable grant.
5. `schema.json` controls the exact structured output.
6. `agent.json` controls the model, confidence cutoff, maximum pages per run, text size, output size, and timeout.
7. `examples.jsonl` records expected decisions so tuning can be measured rather than guessed.

Low-confidence model answers are changed to `review`. The rule result remains in the CSV beside the agent result so decisions are auditable. Each run **replaces** its output file with a fresh snapshot; it does not append.

## How pages become CSV rows

For each ordinary HTML source, Germinate:

1. Opens every configured `start_url`. Start pages guide discovery but are not themselves written as opportunity rows.
2. Follows same-site links when the link title or URL contains a grant or topic term and no rejection term.
3. Repeats this up to the source's `max_depth` and `max_pages` limits. The current HTML sources use depth 2 and 30 pages.
4. Classifies each followed page using its link title, URL, and full visible page text.
5. Writes a row when at least one grant, topic, or rejection term is present.

There is currently **no minimum score for inclusion**. `minimum_score` only separates `candidate` from `review`:

```text
score = (2 × matched grant terms) + matched topic terms - (4 × rejection terms)
```

- `rejected`: at least one rejection term is present.
- `candidate`: grant and topic terms are present and the score is at least `minimum_score` (currently 3).
- `review`: some relevant terms are present, but the candidate conditions are not met.

After collection, exact source/URL duplicates are removed. Interactive sources produce a `needs_specialized_collector` row instead of pretending their initial HTML is sufficient.

Agent mode does not control whether a collected row is included. It analyzes only local `candidate` and `review` rows, up to `max_pages_per_run` (currently 25), and adds its assessment beside the local rule result. Agent-rejected rows therefore remain visible for auditing.

## Output

The original columns (`source`, `collector_type`, `title`, `url`, `decision`, `score`, matched terms, `checked_at`, and `note`) show the collector/rule result. Agent columns record whether AI was used, its decision and confidence, grant status, deadline, amount, currency, eligibility, topics, consortium requirement, and reason.

`test-agent.ps1` prints the complete raw structured agent response. The live CSV currently stores only the fields represented by the `Result` record, so raw fields such as `rolling_application`, `evidence`, and the agent-extracted title are not yet copied into the CSV.

## “Fine-tuning” the agent

For now, tune behavior in this order:

- Edit `rules.json` when pages are incorrectly included/excluded before AI.
- Edit `prompt.md` when the model misunderstands Germinate's policy.
- Edit `schema.json` when you need different output fields.
- Edit thresholds and limits in `agent.json`.
- Add real labelled cases to `evals/examples.jsonl`, then run comparisons after every change.

This is **prompt/configuration tuning**, not model fine-tuning. Actual fine-tuning changes model weights using a much larger reviewed dataset and should come later, only if evals show that prompting and structured outputs are insufficient.

## Is this RAG?

It is **RAG-like, but not classic RAG**. The model is grounded in text retrieved from live websites, so the broad idea is similar. Classic RAG normally stores documents in a searchable index (often embeddings/vector search), retrieves the most relevant chunks for a user's question, and gives those chunks to a model.

Germinate currently crawls known pages, uses rules to preselect links, and asks a model to classify/extract each page. There is no vector database, embedding search, or question-answering layer. It could become full RAG later by storing indexed opportunities and retrieving them in response to queries such as “show restoration grants open to Spanish nonprofits.”

## Costs and bottlenecks

- One candidate page normally means one API request, so cost and time scale with candidate count and page length.
- `max_pages_per_run` and `max_page_characters` cap that exposure.
- Dynamic sites need dedicated collectors; robots rules, rate limits, layout changes, PDFs, logins, and anti-bot systems can block collection.
- Model output can still be wrong, so evidence, confidence thresholds, evals, and human review remain necessary.
- Scheduling and hosting are separate future layers; this repository currently runs on demand.
