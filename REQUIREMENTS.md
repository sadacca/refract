# Refract — Cognitive Bias Analysis & Reframing Tool
## Product Requirements Document

---

## Foundational Framing

**Cognitive bias is a normal feature of human cognition, not a character flaw or editorial sin.**

Every human mind uses heuristics and shortcuts — this is how we function. Cognitive biases are not errors made by bad actors; they are natural patterns that emerge from how brains process information under uncertainty. When they appear in written text, they reflect the author's human cognition, their editor's, their source's, and their reader's. They are pervasive and expected.

**What Refract is doing — and what it is not:**

| What it IS | What it is NOT |
|---|---|
| Descriptive analysis of cognitive patterns in text | A rating system for news quality |
| A tool for understanding *how* a piece is framed | A tool for labeling outlets as biased or unbiased |
| Grounded in cognitive psychology literature | Grounded in political or ideological frameworks |
| Interested in *all* biases present, as a complete picture | Interested in finding the "worst" or "most" biased sources |
| A foundation for reframing — presenting the same facts differently | A fact-checker or misinformation detector |

**Practical implications for how the tool works:**

- **An article with many bias instances is normal, not alarming.** A well-written, thoroughly reported 2,000-word article will likely contain multiple instances of availability heuristic, framing effects, narrative structure, and anchoring. That's expected — it's how human writing works. The tool should present this as a complete cognitive map of the article, not a score to be minimized.
- **Every bias instance is worth capturing.** The goal is a full inventory: every excerpt that exhibits a bias pattern, labeled with the bias type, the location in the text, and enough context to support reframing. Nothing is too minor to flag.
- **Reframing is exploratory, not corrective.** The reframed version of an article is not the "right" version — it is a different possible framing that reduces identified cognitive patterns. Both versions are valid; the comparison is the value.
- **The tool is not a judge of sources.** Patterns found across 100 articles from one outlet are descriptive data about that outlet's editorial tendencies, not a verdict. The same analysis applied to any outlet, including wire services, academic papers, or this tool's own output, would find cognitive patterns.

---

## Overview

**Refract** is a Streamlit web application that identifies, evaluates, and reframes cognitive biases in written text — starting with news articles and expanding to broader media and GenAI output. The tool is grounded in cognitive psychology (not equity/DEI framing) and is designed to build a standardized framework for bias evaluation and automated reframing.

---

## Goals

1. Establish a canonical, indexed taxonomy of cognitive biases drawn from cognitive psychology literature.
2. Produce a complete inventory of all bias instances in evaluated text — every occurrence, with location and context.
3. Reframe evaluated text to present the same information with reduced cognitive distortion, as one possible alternative framing.
4. (Later) Scale evaluation to article sets, entire news sites, and GenAI outputs.

---

## MVP — Phase 1

### Feature 1: Cognitive Bias Index

**Purpose:** Provide a browsable, searchable reference of cognitive bias categories and examples — the foundation for all downstream evaluation. The index is not merely a glossary; it is the ground-truth reference used by the LLM evaluation pipeline. Its richness directly determines the quality of detection and reframing.

#### 1a. Index Construction Process

The index must be built deliberately, not scraped wholesale. Construction process:

1. **Seed from canonical sources** — start with the Wikipedia Cognitive Bias Codex (~180 biases) and Buster Benson's categorization, then cross-reference against primary literature (Kahneman & Tversky, Cialdini, Ariely, Gilovich, etc.)
2. **Filter for textual detectability** — retain only biases that can manifest detectably in written text; exclude purely perceptual or memory-retrieval biases with no written signal
3. **Enrich each entry from the literature** — pull identification criteria, canonical examples, and reframing strategies from source papers and textbooks, not from secondary summaries
4. **Add journalism-specific examples** — for each bias, include at least one real or constructed example as it would appear in a news article, op-ed, or headline
5. **Peer-review the entry** — each entry should cite at least one primary source; entries without a citable source are marked "provisional"
6. **Version and publish** — the taxonomy is stored as versioned JSON; changes are tracked in git with a changelog

#### 1b. Per-Entry Data Schema

Each bias entry in `taxonomy.json` must include all of the following fields:

| Field | Description |
|---|---|
| `id` | Unique slug (e.g., `confirmation-bias`) |
| `name` | Common name |
| `aliases` | Other names for the same bias |
| `category` | Top-level grouping (see categories below) |
| `subcategory` | More specific grouping within category |
| `definition` | Plain-language definition (2–4 sentences) |
| `mechanism` | Cognitive mechanism: what mental shortcut or error produces this bias |
| `literature_description` | How the bias is described in the primary cog psych literature; include key researcher names and study context |
| `identification_criteria` | Explicit, testable criteria for identifying this bias in written text — written as rules an evaluator (human or LLM) can apply |
| `linguistic_signals` | Specific language patterns, word choices, or structural features that are diagnostic of this bias in writing (e.g., passive voice obscuring agency, absence of counterargument, emotionally loaded adjectives) |
| `canonical_example` | A brief neutral example of the bias in general prose, drawn from or consistent with the literature |
| `reframing_strategy` | How to rewrite or restructure text exhibiting this bias to reduce it; what information needs to be added, removed, or restructured |
| `reframing_example` | A journalism example rewritten using the `reframing_strategy` |
| `common_confusions` | Other biases this one is frequently mistaken for, and how to distinguish them |
| `severity_signal` | Typical severity when present in journalism: high / medium / low, with rationale |
| `sources` | List of primary citations (author, year, title, DOI or URL if available) |
| `status` | `canonical` (cited primary source) or `provisional` (needs source) |
| `reference_examples` | Precomputed, human-verified example set used as few-shot anchors in evaluation prompts (see below) |

**`reference_examples` sub-schema:**

| Sub-field | Description |
|---|---|
| `positive[]` | 3 short journalism excerpts that clearly exhibit this bias, each via a different linguistic mechanism, spanning different topic domains. Human-verified. |
| `near_miss[]` | 2 excerpts that look like the bias but are not instances of it. Each includes `why_not` — a one-sentence explanation of the distinction. Human-verified. |
| `contrast` | 1 example illustrating the most commonly confused bias (`common_confusions`), with a `distinction` field explaining the boundary. |

These are the anchors injected into Pass 2 identification prompts. Detection compares article text against this fixed reference set — the model does not generate its own representation of the bias at inference time. When reference examples change, `framework_version` increments.

#### 1c. Bias Category Taxonomy

Top-level categories to organize the index (based on Benson/codex structure, adapted for written-text detectability):

- **Attribution & Causation** — errors in assigning cause, credit, or blame (fundamental attribution error, actor-observer bias, just-world hypothesis)
- **Framing & Anchoring** — how presentation order and reference points distort interpretation (framing effect, anchoring, contrast effect)
- **Availability & Salience** — overweighting information that is vivid, recent, or easily recalled (availability heuristic, the spotlight effect, availability cascade)
- **Confirmation & Belief Perseverance** — seeking and favoring information that confirms existing beliefs (confirmation bias, myside bias, backfire effect)
- **In-Group & Social** — favoritism toward perceived in-group and distortion of out-group (in-group bias, out-group homogeneity, moral licensing)
- **Narrative & Pattern** — imposing story structure, causality, or pattern where none is established (narrative fallacy, clustering illusion, Texas sharpshooter fallacy)
- **Authority & Social Proof** — deferring to authority, consensus, or popularity as a substitute for evidence (appeal to authority, bandwagon effect, expert halo)
- **Affect & Emotional Reasoning** — letting emotional tone stand in for evidentiary argument (affect heuristic, emotional contagion in text, fear/outrage framing)
- **Omission & Selective Emphasis** — bias through what is left out, minimized, or buried (omission bias, selective emphasis, euphemistic labeling)
- **Temporal & Recency** — over- or under-weighting information based on timing (recency bias, present bias, end-of-history illusion)
- **GenAI-Specific** *(Phase 2)* — sycophancy, training data recency bias, overconfidence, persona injection

#### 1d. Precompute Phase

Before evaluation can run on any article, a separate precompute phase must populate `reference_examples` for every bias in the taxonomy. This runs once per taxonomy entry and re-runs whenever the entry's definition, criteria, or examples are updated.

**Why precompute:** The evaluation pipeline injects reference examples as few-shot anchors. If an entry has no verified examples, Pass 2 falls back to criteria-only detection (the weaker, probabilistic approach). Entries without `reference_examples` are flagged as `examples_status: "pending"` in the taxonomy and tracked on the Framework Dashboard.

**Precompute pipeline** (runs via `scripts/precompute_examples.py`):
1. For each entry with `examples_status: "pending"`, call the LLM with a generation prompt requesting 3 positive, 2 near-miss, and 1 contrast example
2. Write candidate examples to `data/pending_examples/{bias_id}.json`
3. Human reviews each via a simple UI in the Framework Dashboard (accept / reject with reason)
4. Accepted examples are written back to `taxonomy.json`; `examples_status` set to `"verified"`
5. Commit updated taxonomy and increment `framework_version`

**Priority order for human review:** Biases with high literature prominence and high Wikipedia prominence first (per the three-dimension scoring in 1a). These will appear most frequently in evaluated articles and benefit most from strong anchors.

#### 1e. Index as Evaluation Substrate

The index is the direct input to the LLM evaluation pipeline:
- Pass 2 identification prompts inject `identification_criteria`, `linguistic_signals`, and `reference_examples` (positive, near-miss, contrast) as fixed anchors — the model compares article text against these, not against a probabilistic in-context representation
- Recall probes inject bias names and positive example summaries to check for category-level misses
- The reframing prompt uses `reframing_strategy` and `reframing_example` as few-shot examples
- When a new bias is added with verified examples, the evaluation pipeline automatically gains full coverage — no prompt engineering required

**UI:**
- Sidebar nav or tabbed layout
- Card or table view with expandable detail panels
- Filter by category, subcategory, severity, or status (canonical / provisional)
- Each card shows: name, category, definition, linguistic signals, journalism example, and reframing example
- Full detail panel shows all fields including literature description, sources, and common confusions

---

### Feature 2: Single Article Bias Evaluation

**Purpose:** Accept a single news article (URL or pasted text) and return a structured bias analysis.

**Requirements:**
- Input modes:
  - Paste raw article text
  - Enter a URL (fetch and parse article body, strip boilerplate/ads)
- Analysis pipeline:
  - Extract article text
  - Send to LLM (Claude via Anthropic API) with structured prompt referencing the bias taxonomy
  - Return structured output: list of detected biases, each with:
    - Bias name and category
    - Quoted excerpt(s) from the article that exhibit the bias
    - Explanation of how the excerpt exhibits the bias
    - Confidence score (high / medium / low)
    - Severity rating for this instance
- Aggregate summary:
  - Overall bias score / profile for the article
  - Dominant bias categories present
  - Bias balance: is the article predominantly one type of distortion?
- Results displayed in a readable, structured UI (not raw JSON)
- Option to export results as JSON or PDF

**Constraints:**
- Article length limit (configurable, default 10,000 words)
- Graceful handling of paywalled or inaccessible URLs
- API key managed via environment variable, not hardcoded

---

### Feature 3: Article Reframing

**Purpose:** Generate a rewritten version of the article with identified biases removed or neutralized, while preserving factual content.

**Requirements:**
- Builds on Feature 2 output (requires bias evaluation to have run first)
- Reframing modes (user selects):
  - **Neutralize:** Rewrite to minimize identified biases; preserve all facts, restructure framing
  - **Steelman:** Rewrite to present the strongest version of each competing perspective mentioned
  - **Annotated:** Keep original text, insert inline annotations explaining each bias instance
- Reframing pipeline:
  - Pass original text + bias evaluation results to LLM with reframing prompt
  - LLM returns reframed text
- Display original and reframed text side by side (diff-style optional)
- Highlight which biases were addressed in the reframe
- Export reframed article as plain text or markdown

**Constraints:**
- Reframe should not introduce new factual claims
- System prompt explicitly instructs model to flag if reframing would require information not present in the source

---

## Secondary Build-Out — Phase 2

### Feature 4: Multi-Article Event Analysis

**Purpose:** Evaluate a current news event across multiple articles from different outlets.

**Requirements:**
- User inputs a topic or search query
- System fetches N articles (via news API or manual URL list)
- Runs Feature 2 evaluation on each article
- Aggregates results:
  - Bias profile per outlet
  - Cross-outlet comparison: which biases appear most, which outlets share patterns
  - Timeline view if article dates vary
- Identify consensus framing vs. outlier framings

---

### Feature 5: Website / Publication Bias Inventory

**Purpose:** Evaluate a news source or website at scale to inventory its characteristic bias patterns.

**Requirements:**
- User inputs a domain or publication name
- System fetches a sample of recent articles (configurable sample size)
- Runs batch evaluation
- Returns a bias signature for the publication:
  - Frequency distribution of bias types
  - Most common bias categories
  - Severity distribution
  - Example articles for each dominant bias type
- Results exportable as a report

---

### Feature 6: GenAI Output Evaluation

**Purpose:** Apply the same bias evaluation framework to LLM-generated text.

**Requirements:**
- Input modes:
  - Paste GenAI output directly
  - Enter a prompt; system generates a response from a configurable model and evaluates it
- Evaluation identical to Feature 2
- Additional GenAI-specific bias categories:
  - Sycophancy / agreement bias
  - Training data recency bias
  - Overconfidence / epistemic hedging failure
  - Persona/framing injection from system prompt
- Comparative mode: run same prompt against multiple models, compare bias profiles

---

## Phase 3 — Gap Audit & Model Comparison

### 3a. High-Level Gap Audit

Before full Phase 3 build-out, run a structured audit of what the MVP pipeline is missing. This is a one-time review using the accumulated `data/processed/` dataset from the POC run.

**Audit questions:**

| Gap area | Audit method |
|---|---|
| **Taxonomy coverage** | Are there bias patterns appearing in articles that don't map to any taxonomy entry? Sample 20 articles manually and look for patterns the pipeline didn't detect. |
| **Category boundary errors** | Which biases are most often misassigned to the wrong category? Check `category_accuracy` in eval log. |
| **Reference example quality** | For each bias with high FP or FN rate in the hand-eval log, review whether the reference examples are the problem — too narrow (missing real instances) or too broad (matching non-instances). |
| **Recall probe effectiveness** | How often do recall probes surface true positives that Pass 2 missed? If rarely, probes are working. If frequently, Pass 1 category triage is too aggressive in excluding categories. |
| **Reframe quality** | Read 10 reframed articles. Do they read as more neutral? Are any facts changed or dropped? |
| **Pipeline failures** | What percentage of article fetches fail (paywall, timeout, encoding issues)? What percentage of LLM calls fail or return malformed JSON? |

Audit findings feed directly into taxonomy updates, reference example revisions, and prompt changes before Phase 3 model comparison runs.

### 3b. Model Comparison

**Purpose:** Once the POC is working and produces a baseline dataset, compare models on their ability to detect cognitive bias to understand which is most accurate, where models diverge, and whether cost justifies quality differences.

**Requirements:**
- Run the same set of evaluated articles (from `data/processed/`) through multiple models using the same framework version and prompts
- Models to compare: Gemini 2.0 Flash (POC baseline), Claude Sonnet, Groq/Llama 3.1 70B, and at least one additional (Gemini 1.5 Pro or Claude Haiku for cost comparison)
- For each article, record per-model: bias instances detected, confidence scores, recall probe results, and judge verdicts
- Aggregate comparison metrics:
  - Agreement rate between models on the same article (which biases all models agree on vs. model-specific detections)
  - Precision/recall per model against the hand-eval test set
  - False negative rate per model (via recall probes)
  - Cost per article per model
- Display a model comparison page in the UI showing the above metrics
- Use this to make an evidence-based decision on the default model for Phase 2 features

**What makes this tractable:** Because every article is persisted with its `framework_version` and `model` field, re-running existing articles through a different model is a batch job against `data/processed/index.json`, not a fresh data collection effort. The dataset built during POC is the test bed for this comparison. Gap audit findings (3a) are resolved before model comparison runs — otherwise you're comparing models against a flawed reference framework.

---

## Technical Architecture

### Reference Architecture

The balt311-service-equity app (`github.com/sadacca/balt311-service-equity`) is the architectural reference for Refract. Key patterns to carry forward:

**App structure:**
- Single `app/app.py` entrypoint; UI components imported from `app/components/`
- Tabbed or page-based navigation (balt311 uses two tabs; Refract uses Streamlit multipage)
- `@st.cache_data` on all data loading functions — critical for LLM call results which are expensive to recompute
- Session state for cross-page coordination (active article, evaluation results, selected framework version)
- Graceful degradation: check data/result availability before rendering, display instructional message if missing

**Pipeline separation:**
- balt311 separates ingest (API fetch) from processing (clean + aggregate) into distinct stages with intermediate artifact storage
- Refract follows the same pattern: article fetch → evaluation → results stored as JSON artifacts; evaluation does not re-run on page refresh
- A headless `scripts/` equivalent (`refract/scripts/batch_eval.py`) for running the 100-article pipeline outside the Streamlit UI

**Data fetching patterns:**
- Exponential backoff retry (up to 4 attempts, 2^n second waits) on all external API calls — carry this directly into the Guardian API and Anthropic API clients
- ThreadPoolExecutor with conservative worker count (4) for parallel fetches — applicable to batch article fetching in Phase 2
- Page size negotiation before bulk fetch — relevant for Guardian API pagination

**Secrets:**
- `st.secrets` with graceful fallback — `ANTHROPIC_API_KEY`, `GUARDIAN_API_KEY` stored as Streamlit Cloud secrets; local dev uses `.env` + `python-dotenv`

**Deployment:**
- Streamlit Community Cloud reads directly from the repo's `main` branch at runtime
- Processed/cached artifacts committed to `data/` in the repo — Refract equivalent: committed `taxonomy.json` and optionally cached evaluation results for the demo dataset

### API Access — What's Actually Free

**Anthropic API:** Claude Pro ($20/mo) is a chat subscription — it does **not** include API access or credits. API is billed separately at `console.anthropic.com`. New accounts receive a small starter credit on signup (~$5), but there is no ongoing free tier. For a hobby POC this is the primary cost: Sonnet 3.5 runs ~$3/MTok input, ~$15/MTok output; a 2,000-word article evaluation costs roughly $0.01–0.03 per article. 100 articles ≈ $1–3 total.

**Free LLM API options (viable for Refract):**

| Provider | Free tier | Models | Structured JSON | Notes |
|---|---|---|---|---|
| **Google Gemini** | 1,500 req/day, 1M token context | Gemini 2.0 Flash | Yes | Best free option; verify current limits at ai.google.dev before relying on them |
| **Groq** | 1,000 req/day, 30 req/min | Llama 3.1 70B, Mixtral 8x7B | Yes | Fastest inference; 70B model capable enough for bias detection |
| **OpenRouter** | $0/M token free models | Llama 3.1 8B, Qwen 2.5 72B | Varies by model | Routes to community-hosted models; no credit card |

**Approach — RESOLVED:** Gemini 2.0 Flash is the primary evaluator for MVP. 1,500 req/day free tier is sufficient for development and the 100-article POC run. LLM client is abstracted behind a single interface (model name + API key via config) so swapping providers requires no code changes. Model comparison (Gemini vs. Claude Sonnet vs. Groq/Llama) is a defined post-MVP phase — see Phase 3 below.

**Guardian API:** Free, 500 req/day, no credit card. Key at `open-platform.theguardian.com`.

**trafilatura:** Local Python library, no API, no cost.

### Stack
- **Frontend:** Streamlit (Community Cloud deployment)
- **LLM Backend:** Configurable — Gemini 2.0 Flash (free dev/POC), Claude Sonnet/Opus (production quality); abstracted behind a single client interface
- **Article Fetching:** `trafilatura` for URL scraping; Guardian API for programmatic search
- **Data Storage:** JSON files committed to repo (see Data Persistence below)
- **Automation:** GitHub Actions for batch pipeline runs

### End-to-End Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│  INPUT                                                              │
│  User pastes URL  ──or──  Guardian API search  ──or──  batch list  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  INGEST  (src/refract/ingest.py)                                    │
│  trafilatura fetches and cleans article text                        │
│  Guardian API returns structured article JSON with metadata         │
│  Output: article record { url, text, title, date, source, hash }   │
│  Hash checked against data/processed/ — skip if already evaluated  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  EVALUATION  (src/refract/bias_eval.py)                             │
│  Pass 1: Category classification (LLM, small prompt)               │
│  Pass 2: Bias identification for flagged categories (LLM)          │
│  Pass 3: Recall probes for undetected categories (LLM)             │
│  Pass 4: LLM judge review of detections (different model/tier)     │
│  Output: evaluation JSON (schema defined in Evaluation Framework)  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PERSIST  (every article, no exceptions)                            │
│  Write to data/processed/{article_hash}.json                        │
│  Append to data/processed/index.json (manifest of all evaluations) │
│  On GitHub Actions runs: git commit + push the new files            │
│  On Streamlit UI runs: files written locally; user can download     │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                      ┌────┴─────┐
                      │          │
                      ▼          ▼
              ┌──────────┐  ┌────────────────┐
              │  REFRAME │  │  DISPLAY / STATS│
              │(optional)│  │                │
              │ Pass eval │  │ Bias cards     │
              │ results + │  │ Prevalence     │
              │ article   │  │ charts         │
              │ to LLM    │  │ Category       │
              │ reframe   │  │ breakdown      │
              │ prompt    │  │ Judge verdicts │
              └──────────┘  └────────────────┘
```

**Key invariant:** Every article that completes evaluation is persisted. The pipeline never discards a processed article. Re-running the UI on the same URL returns the cached result from `data/processed/` without an API call.

---

### Data Persistence Strategy

Every evaluated article is a permanent asset. The repo is the database for the POC.

**Per-article record** (`data/processed/{article_hash}.json`):
```json
{
  "article_id": "sha256 of url+text",
  "url": "string",
  "title": "string",
  "source": "string",
  "fetched_at": "ISO8601",
  "article_text": "string",
  "word_count": "integer",
  "evaluation": { ... },
  "judge_review": { ... },
  "reframe": { "mode": "string", "text": "string" }
}
```

**Manifest** (`data/processed/index.json`) — lightweight index of all evaluations, no article text:
```json
[
  {
    "article_id": "string",
    "url": "string",
    "source": "string",
    "fetched_at": "ISO8601",
    "framework_version": "string",
    "bias_count": "integer",
    "dominant_categories": ["string"],
    "word_count": "integer"
  }
]
```

The manifest is what the stats page and Framework Dashboard read — it's fast to load and query without pulling all article text into memory. Full records are lazy-loaded only when a specific article is opened.

**GitHub Actions automation:**
- `batch_eval.yml`: Triggered manually (workflow_dispatch) or on schedule. Reads a URL list from `data/input/batch_urls.txt`, runs `scripts/batch_eval.py`, commits new files in `data/processed/` to main. Uses repo secrets for API keys.
- `update_index.yml`: Rebuilds `index.json` from all files in `data/processed/` — run after any batch or as a separate reconcile step.

**What this gives you over time:**
- Every article ever evaluated is replayable with a different framework version
- The 100-article stats run is just a query over `index.json`
- Re-evaluating all articles with a new framework version is a batch job, not a rebuild from scratch
- The dataset grows automatically every time anyone uses the UI and hits a new URL

---

### Key Modules
```
refract/
├── app.py                            # Streamlit entrypoint
├── pages/
│   ├── 1_bias_index.py               # Bias taxonomy browser
│   ├── 2_article_eval.py             # Single article evaluation
│   ├── 3_reframe.py                  # Article reframing
│   └── 4_framework_dashboard.py     # Eval scores, version history, feedback, example review
├── components/
│   ├── eval_display.py               # Renders bias instance cards
│   ├── reframe_display.py            # Side-by-side original / reframed
│   └── stats_display.py              # Prevalence charts, category breakdowns
├── src/refract/
│   ├── ingest.py                     # Article fetch: trafilatura + Guardian API
│   ├── bias_eval.py                  # 4-pass LLM evaluation — loads precomputed blocks only
│   ├── reframe.py                    # LLM reframing pipeline
│   └── llm_client.py                 # Thin abstraction: model + key → structured call
│                                     # Swappable: Gemini / Claude / Groq via config
├── bias_index/
│   ├── taxonomy.json                 # Canonical bias taxonomy (versioned)
│   └── CHANGELOG.md                 # Taxonomy change history
├── data/
│   ├── precomputed/                  # Committed: all precomputed prompt blocks + embeddings
│   │   ├── bias_blocks/              # {bias_id}_{taxonomy_version}.txt
│   │   ├── category_triage_blocks/   # {category_id}_{taxonomy_version}.txt
│   │   ├── recall_probe_blocks/      # {category_id}_probe_{taxonomy_version}.txt
│   │   ├── judge_blocks/             # {criterion_id}_{framework_version}.txt
│   │   ├── reframe_blocks/           # {mode}_{taxonomy_version}.txt
│   │   ├── embeddings.npy            # Bias embedding vectors for Mode B similarity filter
│   │   └── taxonomy_index.json       # Flat lookup: bias_id → category, status, prominence
│   ├── cache/                        # Gitignored: article text + intermediate pass results
│   │   ├── {hash}_raw.json           # Cleaned article text (fetched once, never re-fetched)
│   │   └── {hash}_{version}.json     # Per-pass cached results
│   └── processed/                    # Committed: final evaluation records + indexes
│       ├── {article_hash}_{fw_version}.json  # Full evaluation record
│       ├── index.json                # Manifest: all evaluations, no article text
│       ├── stats.json                # Precomputed aggregations
│       └── bias_frequency.json       # Per-bias hit count/rate by framework version
├── eval/
│   ├── test_set/                     # Labeled articles + gold-standard annotations
│   ├── results/                      # F1 scores per framework version
│   └── scoring.py                    # Automated scoring (post-POC)
├── scripts/
│   ├── precompute.py                 # Regenerates all data/precomputed/ artifacts
│   ├── batch_eval.py                 # Headless N-article pipeline
│   └── build_index.py                # Rebuilds index.json, stats.json, bias_frequency.json
├── config.py                         # API keys, framework version, model selection
├── requirements.txt
└── .env.example
```

### LLM Prompt Design Principles
- All evaluation prompts reference the canonical taxonomy by category name and definition
- Output is requested as structured JSON with defined schema (bias name, excerpt, explanation, confidence, severity)
- Reframing prompts explicitly constrain the model: preserve facts, do not add claims, flag gaps
- System prompts are versioned alongside the taxonomy

---

## Evaluation Framework

### Overview

The evaluation pipeline is not a one-off LLM call — it is a **versioned, tunable prompt framework** that can be applied consistently across articles, publications, and GenAI outputs. The framework must be:
- **Reproducible:** the same article + same framework version produces the same evaluation
- **Auditable:** every evaluation records which prompt version and taxonomy version were used
- **Improvable:** there is a defined process for measuring framework quality and iterating on it

---

### The Standard Evaluation Prompt

The evaluation prompt is a structured template, not freeform instructions. It has three layers:

**Layer 1 — System prompt (stable)**
Sets the evaluator role, grounds the task in cognitive psychology (not political/ideological framing), defines the output contract (structured JSON), and states the evaluation constraints:
- Only identify biases with textual evidence; do not infer intent
- Quote the specific excerpt, not a paraphrase
- Distinguish between the author exhibiting a bias vs. the author reporting on a biased source
- Flag low-confidence detections separately; do not suppress them

**Layer 2 — Taxonomy injection (versioned per taxonomy release)**
For each bias in the active taxonomy, injects the `identification_criteria` and `linguistic_signals` fields as a structured reference block. This is the mechanism by which taxonomy improvements automatically improve evaluations — the prompt is regenerated from the taxonomy JSON at runtime, not hardcoded.

**Layer 3 — Article context (per-call)**
The article text, source metadata, and any user-supplied context (e.g., "this is an opinion piece" vs. "this is a reported news article") that affects how the evaluation criteria are applied.

**Prompt versioning:**
- Each combination of system prompt template version + taxonomy version is assigned a `framework_version` identifier (e.g., `v1.2.0`)
- All evaluation results record their `framework_version`
- When the framework changes, prior evaluations are not retroactively updated — they remain as-is with their version tag, enabling comparison across versions

---

### Evaluation Output Schema (JSON)

```json
{
  "article_id": "string",
  "source_url": "string | null",
  "evaluated_at": "ISO8601 timestamp",
  "framework_version": "string",
  "taxonomy_version": "string",
  "model": "string",
  "bias_instances": [
    {
      "bias_id": "string",
      "bias_name": "string",
      "category": "string",
      "excerpt": "string",
      "explanation": "string",
      "confidence": "high | medium | low",
      "severity": "high | medium | low",
      "author_exhibiting": true,
      "source_reporting": false
    }
  ],
  "summary": {
    "dominant_categories": ["string"],
    "overall_severity": "high | medium | low",
    "bias_count": "integer",
    "low_confidence_count": "integer"
  }
}
```

---

### Meta-Evaluation: Assessing Assessment Quality

The system must support evaluation of its own evaluations. This is how framework quality is measured and how iteration is grounded in evidence rather than intuition.

#### Ground Truth Dataset

- A curated set of **labeled test articles** stored in `eval/test_set/`
- Each test article has a human-authored gold-standard annotation:
  - Which biases are present (by `bias_id`)
  - Which excerpts exhibit each bias
  - Confidence and severity ratings
  - Rationale for each annotation
- Test set is versioned; new articles can be added but existing annotations are not modified without a changelog entry
- Initial test set target: 20–30 articles spanning categories, bias types, and publication styles

#### Automated Scoring

For each framework version run against the test set, compute:

| Metric | Description |
|---|---|
| **Precision** | Of the biases the framework detected, what fraction match the gold standard? |
| **Recall** | Of the biases in the gold standard, what fraction did the framework detect? |
| **F1** | Harmonic mean of precision and recall |
| **Excerpt match rate** | When a bias is correctly identified, does the quoted excerpt match the gold-standard excerpt (fuzzy match)? |
| **Category accuracy** | When a bias instance is detected, is the category label correct? |
| **False positive rate** | How often does the framework flag a bias that is not in the gold standard? |
| **Confidence calibration** | Are high-confidence detections more likely to be correct than low-confidence ones? |

Scores are stored in `eval/results/{framework_version}.json` and displayed in the UI's framework dashboard.

#### Human Feedback Loop

In addition to the automated test set, the UI supports lightweight human feedback on live evaluations:
- User can mark any detected bias instance as: **Agree / Disagree / Partially agree**
- User can add a note explaining disagreement
- Feedback is stored locally (MVP) or in the database (Phase 2)
- Aggregate feedback per bias type surfaces in the framework dashboard as a signal for which bias categories have low human agreement

---

### Framework Iteration Process

Improvements to the framework follow a defined cycle to prevent regressions:

1. **Identify a gap** — from meta-evaluation scores, human feedback, or manual review, identify a specific failure mode (e.g., "framework misses availability cascade in economic reporting" or "too many false positives for narrative fallacy")

2. **Hypothesize a fix** — the fix is one of:
   - Update a taxonomy entry (`identification_criteria`, `linguistic_signals`, or `common_confusions`)
   - Update the system prompt template
   - Add new test articles to the test set that cover the gap

3. **Implement on a branch** — taxonomy and prompt changes are made on a feature branch; the `framework_version` minor version is incremented

4. **Run the test set** — automated scoring is run against the full test set on the new version; results are compared to the prior version

5. **Accept or reject** — the change is accepted if overall F1 improves or holds, and the targeted failure mode improves; it is rejected (or revised) if it causes regressions elsewhere

6. **Merge and tag** — merged changes increment the version; a changelog entry describes what changed and why

This process applies to both taxonomy changes and prompt template changes. It ensures the framework improves systematically and that every change is traceable to a specific quality signal.

---

### Framework Dashboard (UI)

A dedicated page in the app displaying:
- Current `framework_version` and `taxonomy_version` in use
- Test set scores for the current version (precision, recall, F1 per bias category)
- Version history: scores across all prior framework versions (trend chart)
- Human feedback summary: which bias categories have the most disagreements
- Links to the test set, taxonomy JSON, and prompt templates (read-only in UI, editable in repo)

This page is the operational home for anyone iterating on the framework — it surfaces where the framework is strong, where it is weak, and whether a proposed change helped.

---

## Non-Goals (MVP)
- Real-time streaming news ingestion
- User accounts or authentication
- Political or ideological scoring (this is cognitive psychology framing only)
- Fact-checking or claim verification

---

## Open Questions / Decisions Needed

### Resolved

**Q1 — Taxonomy source:** Start from the full Wikipedia Cognitive Bias Codex (~180 biases) as the seed list. Filter for textual detectability (see 1a), then apply three categorization dimensions to each retained entry:

1. **Psychological category** — grouping by shared mechanism, behavioral pattern, or neural underpinning (e.g., all availability-family biases share the same fluency/retrieval mechanism; attribution biases share causal reasoning errors). This is the primary grouping used in the evaluation pipeline.
2. **Wikipedia prominence** — flag whether the bias has its own dedicated Wikipedia article (vs. being a redirect or subsection). Biases with dedicated articles are better documented, more likely to have primary source citations, and more recognizable to non-specialist users. Use this as a proxy for "well-established enough to include in MVP."
3. **Literature prominence** — score each bias by frequency of mention in psychology paper titles and abstracts (via a title search of PsycINFO, Google Scholar, or Semantic Scholar). Biases with higher literature presence are better validated, more likely to have clear identification criteria, and more worth investing in rich entries. Use this to prioritize enrichment order.

The combination of these three signals lets us tier the taxonomy: biases that are psychologically grouped, Wikipedia-prominent, and literature-prominent get full entries first; others are marked provisional and enriched over time.

---

### Still Open

**Q2 — LLM model selection (RESOLVED):** Sonnet for evaluation, Opus for judging. Model is set via environment variable (`EVAL_MODEL`, `JUDGE_MODEL`) so it can be swapped without code changes. HF free inference tier is not viable for this task — as of 2025 the free serverless API focuses on CPU inference and smaller legacy models (BERT, GPT-2 era); it does not support the nuanced structured output needed for bias detection. HF Inference Providers (Together, Fireworks, etc.) are pay-per-token with no meaningful cost advantage over Claude for this use case.

**Q3 — Article fetching (RESOLVED):** Three-tier approach, ordered by POC practicality:

*Tier 1 — Direct URL scraping (POC primary):* Use `trafilatura` (preferred over `newspaper3k` — better extraction quality, actively maintained) to fetch and clean article text from any URL the user provides. Free, no API key, works on most non-paywalled major outlets. Handles the paste-or-URL input for the single-article evaluation UI. Fails gracefully on paywalled content with a clear error message.

*Tier 2 — The Guardian API (POC secondary, free):* 500 requests/day, 5,000/month, full article text, structured JSON response with section, tags, and publication date. Free developer key at `open-platform.theguardian.com`. Best option for programmatic article browsing and search — useful for selecting articles to add to the test set, and as a known-quality corpus for initial evaluation. Single source limitation is acceptable for POC; quality journalism is a good test bed.

*Tier 3 — RSS feed aggregation (Phase 2):* Curate a list of RSS feeds from major outlets (BBC, Reuters, AP, etc.). Pull recent articles, extract text via trafilatura. Free, no rate limits, multi-source. Better suited to Phase 2 publication inventory and multi-article event analysis than to MVP single-article review.

NewsAPI and GDELT deferred: NewsAPI free tier returns headlines only (no full text) and 100 requests/day; paid tier is $449/month — not appropriate for a hobby project. GDELT is powerful but complex to query and returns document metadata, not clean article text.

**Q4 — Severity scoring (RESOLVED):** Dual-mode scoring:
- **Detection pass:** Binary — the bias is either present or not. A bias instance is either anchoring or it isn't. Binary detection avoids the calibration problem of asking the model to grade severity without a reference standard, and is more defensible for the initial test set.
- **Severity rating:** Graduated (high/medium/low) recorded as a separate field, populated by the evaluation model but treated as informational rather than a detection gate. Used during eval framework iteration to study where the model's severity judgments align or diverge from human judgment — i.e., severity is a calibration target, not a classification output.
- Schema: `detected: true`, `severity: "high" | "medium" | "low"` — both fields always present; severity is always recorded but only used analytically once enough examples exist to calibrate against.

**Q5 — Reframe quality flagging (RESOLVED):** No AI labeling, no confidence indicator. The reframe feature is a prompt that attempts a rewrite — the output speaks for itself. Keep the UI simple: show the reframed text, let the user judge it.

**Q6 — Prompt context window management (RESOLVED):** *(see full resolution above)*

**Q7 — Test set annotation process:** Deferred to post-POC. For POC, single annotator (the developer), informal markdown log per the POC eval section of EVALUATION_FRAMEWORK.md.

**Q8 — Article type differentiation:** Should the evaluation prompt behave differently for news reports vs. opinion pieces vs. headlines vs. social media posts? The author-exhibiting vs. source-reporting distinction (already in the schema) becomes especially important for opinion content. Does the system need an article-type classifier as a preprocessing step?

**Q9 — Reframe evaluation rubric:** Informal for POC: re-run the evaluation on the reframed article and compare bias_count to the original. Formal rubric (factual preservation, completeness, readability) deferred to Phase 2.

**Q10 — Taxonomy governance:** Deferred. Single developer, git history is sufficient for POC.

**Q8 — Article type differentiation (RESOLVED):** No prompt differentiation by article type. The goal is a universal bias detector applicable across domains — the same cognitive biases manifest in news reports, opinion pieces, and GenAI output, and the detection criteria should be domain-agnostic. The `author_exhibiting` vs. `source_reporting` distinction in the schema already handles the most important contextual difference (is this the author's bias or a bias they're reporting on) without requiring separate prompts. If a specific article type proves problematic during POC testing, address it with a taxonomy entry refinement, not a prompt fork.

**Q11 — Taxonomy seeding (RESOLVED):** Start with programmatic seed from the Wikipedia Cognitive Bias Codex. Write a one-time script to pull all entries and create provisional taxonomy JSON records. Most entries will be thin initially (name, category, Wikipedia definition only). Hand-label the most important entries first — prioritize by literature prominence and Wikipedia prominence scores (per the three-dimension categorization in Feature 1c). The taxonomy is always a work in progress; the seed gives full coverage, hand-labeling gives quality where it matters most.

**Q12 — Deployment (RESOLVED):** Streamlit Cloud. Free tier, public URL, no infrastructure overhead. API keys stored as Streamlit secrets. Article fetching via trafilatura from the cloud container is standard and well-supported.

**Q13 — POC Success Definition (RESOLVED):** The POC is successful when:
1. User can point the app at a news article URL and get a structured bias evaluation end-to-end
2. Initial classification runs against all bias categories (via two-pass pipeline) on short articles without timeout or failure
3. High-level stats are compiled across 100 articles: most prevalent biases, frequency by category, severity distribution
4. LLM-as-judge eval runs on detected instances and produces a reviewable verdict
5. The developer, reading 10 evaluated articles alongside the output, agrees with the majority of detections

The 100-article stat compilation is the key deliverable — it tests the pipeline at scale and produces something substantively interesting (what biases actually appear most in news?).

---

## The False Negative Problem

The hardest eval challenge is not assessing hits — it's assessing misses. When the model detects a bias, a judge (human or LLM) can review the excerpt and verdict. When the model returns nothing for a bias category, there's no excerpt to review. You don't know what you missed.

This is asymmetric by design: precision (are detections correct?) is easy to evaluate; recall (did we catch everything?) requires ground truth that doesn't exist at POC scale.

### Approaches to estimating false negatives

**1. Adversarial test articles (best signal, most setup)**
Construct or source articles known to contain specific biases — either expert-labeled examples from the literature, or articles deliberately written to exemplify a bias type. If the model misses a known-present bias in a purpose-built example, that's a confirmed false negative. The Guardian API corpus can support this: search for articles on topics known to elicit specific biases (economic policy coverage for anchoring and framing effects; crime reporting for availability heuristic and in-group bias).

**2. Targeted recall probe (good signal, moderate cost)**
After the primary evaluation, run a second pass of targeted yes/no probes for each category the model did not flag: *"Does this article contain any example of [bias name]? If yes, quote the excerpt. If no, explain briefly why not."* This forces the model to articulate absence rather than silently skip. A well-reasoned "no" is more trustworthy than silence. Cost: one additional API call per undetected category per article — practical for a small test set, expensive at scale.

**3. Recall sampling on "clean" articles (statistical estimate, no setup)**
Randomly sample 10–20 articles the full pipeline marked as having zero or very few biases. Have a human (or Opus judge) read them and check for obvious misses. The miss rate in this sample estimates the overall false negative rate without requiring a labeled ground truth corpus. Quick and cheap; statistically noisy but useful as a sanity check.

**4. Contrastive pairs (elegant, naturally available)**
Find two articles covering the same news event — one from a source with a known editorial stance, one from a more neutral wire service (AP, Reuters). The model should detect more and different biases in the opinionated version. If it doesn't, that's a recall signal. The Guardian API makes this easy: compare a Guardian opinion piece to a Reuters wire story on the same story. No ground truth required — the comparison is the signal.

**POC approach:** Targeted recall probes are the primary false negative strategy for the POC. After the main two-pass evaluation, run a targeted yes/no probe for each bias category the model did not flag: *"Does this article contain any example of [bias name]? If yes, quote the excerpt and explain. If no, explain briefly why not."* This forces the model to reason about absence rather than silently skip — a well-reasoned "no" is auditable; silence is not. Contrastive pairs (same story, Guardian opinion vs. Reuters wire) serve as a secondary check at the 100-article scale. Adversarial test articles and recall sampling deferred to Phase 2.

---

## UI Roadmap

The UI is built in Streamlit multipage format. Pages are delivered in two waves: the pipeline MVP gets the minimum UI needed to run and inspect evaluations; the UI MVP adds the article selection, QA, and global review surfaces that make the tool usable beyond a single-article demo.

---

### Wave 1 — Pipeline MVP UI (needed to ship the POC)

These pages are the minimum needed to demonstrate the pipeline end-to-end.

**Page 1 — Article Evaluation (`2_article_eval.py`)**

The core page. Everything else depends on this working.

- **Input:** URL text field + "Fetch & Evaluate" button; secondary text area for paste input
- **Status display:** Step-by-step progress as passes run (Pass 1 → Pass 2 → Pass 3 → Pass 4); spinner per pass with pass name and model shown
- **Cache indicator:** If the article was previously evaluated, show "Loaded from cache (v{framework_version})" with option to re-run
- **Results — bias instance cards:** One card per bias type detected. Each card shows:
  - Bias name, category badge, severity indicator
  - All occurrences listed: each with the quoted excerpt highlighted, paragraph location, text region label, confidence
  - `author_exhibiting` / `source_reporting` label
  - `recall_probe` flag if found by Pass 3
  - Judge verdict (confirmed / suspect) if Pass 4 ran
- **Results — article view:** Original article text rendered with all detected excerpts highlighted inline, color-coded by bias category. Clicking a highlight opens the corresponding bias card.
- **Results — summary bar:** `bias_type_count`, `total_occurrences`, dominant categories, by-region breakdown
- **Export:** Download full evaluation JSON; download summary as markdown

**Page 2 — Article Reframe (`3_reframe.py`)**

Only accessible after an evaluation has run on the current article.

- **Mode selector:** Neutralize / Steelman / Annotated (radio buttons)
- **Reframe button:** Runs the reframe pipeline; shows spinner
- **Side-by-side view:** Original text (left) with bias highlights; reframed text (right)
- **Bias coverage indicator:** Which of the detected biases were addressed in the reframe
- **Export:** Download reframed text as plain text or markdown

---

### Wave 2 — UI MVP (article selection, QA, global review)

These pages make the tool usable as a research instrument, not just a demo. Build after the pipeline is stable.

**Page 3 — Article Browser & Selection (`5_article_browser.py`)**

Allows users to find and queue articles without manual URL hunting.

- **Guardian API search:** Search field, date range, section filter (news / opinion / world / etc.)
- **Results list:** Article title, section, date, word count; checkbox to select for evaluation
- **Batch queue:** Selected articles are added to an evaluation queue; "Run Queue" button triggers `batch_eval.py` on the selected set
- **Previously evaluated indicator:** Articles already in `data/processed/index.json` are flagged so the user doesn't re-run them
- **Manual URL add:** Still available as a fallback for non-Guardian sources

**Page 4 — QA Review (`6_qa_review.py`)**

Human review interface for evaluating evaluation quality. This is where the eval log lives in the UI.

- **Queue view:** Articles evaluated in the current session (or all articles, filterable by date/source/framework version)
- **Per-article review panel:**
  - Original article text with all highlights
  - Each bias instance card with a verdict input: **Confirm / Reject / Partially confirm** + freetext note
  - Judge verdicts shown alongside (if Pass 4 ran) so human can see where they agree/disagree with the LLM judge
- **Running tally:** TP / FP / partial count for the current review session
- **Save & export:** Writes review verdicts to `eval/test_set/{article_id}_review.json`; exportable as CSV

**Page 5 — Global Article Review & Stats (`7_global_review.py`)**

The 100-article view. Reads from `data/processed/stats.json` and `index.json`.

- **Corpus summary:** Total articles evaluated, date range, sources represented, framework version(s) used
- **Bias prevalence chart:** Bar chart of bias types by frequency across all articles; filterable by source, date range, article type
- **Category heatmap:** Articles × bias categories, colored by occurrence count — shows which categories cluster together
- **Source comparison:** Side-by-side bias profiles for multiple sources (only appears when ≥2 sources have ≥5 articles each)
- **Per-article table:** Sortable list of all evaluated articles with columns for bias_type_count, total_occurrences, dominant_category, source, date; click row to open that article's evaluation in Page 1
- **Contrastive pair finder:** Given a topic keyword, surfaces article pairs (Guardian opinion vs. wire service) for manual comparison
- **Export:** Download stats.json; download filtered subset as CSV

**Page 6 — Bias Index (`1_bias_index.py`)**

Already in the module layout. Browsable taxonomy reference.

- Searchable card view of all bias entries
- Filter by category, status (canonical / provisional), examples_status (verified / pending)
- Full entry detail panel: definition, mechanism, identification criteria, linguistic signals, reference examples, sources
- **Framework Dashboard tab** (within this page or as a sub-page):
  - Current framework_version and taxonomy_version
  - examples_status summary: how many entries have verified examples vs. pending
  - Pending example review queue (from `data/pending_examples/`) — accept/reject interface for the precompute human review step
  - Eval scores per framework version (post-POC, once scoring.py exists)
  - bias_frequency.json chart: which biases appear most in the corpus

---

### Page Build Order

```
Pipeline MVP (Wave 1):
  1. Page 1 — Article Evaluation     ← build first; everything depends on this
  2. Page 2 — Article Reframe        ← build second; depends on Page 1 output

UI MVP (Wave 2):
  3. Page 6 — Bias Index             ← can build in parallel with pipeline MVP
  4. Page 4 — QA Review              ← build after Page 1 is stable
  5. Page 5 — Global Review          ← build after batch_eval.py produces data
  6. Page 3 — Article Browser        ← build last; Guardian API integration
```

**Note on Page 1 priority:** The highlighted article view (original text with inline bias highlights using `char_start`/`char_end` offsets) is the single most important UI element. It makes bias detection tangible and reviewable in a way that a card list alone cannot. This should be the first component built and the first thing tested on real articles.

---
- Taxonomy covers all major cognitive bias categories recognized in the literature
- Evaluation correctly identifies bias type and excerpt with >80% agreement against human-labeled test set
- Reframes preserve factual content (verifiable against original) in >95% of cases
- UI is usable without documentation for a non-technical user

