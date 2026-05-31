# Refract — Cognitive Bias Analysis & Reframing Tool
## Product Requirements Document

---

## Overview

**Refract** is a Streamlit web application that identifies, evaluates, and reframes cognitive biases in written text — starting with news articles and expanding to broader media and GenAI output. The tool is grounded in cognitive psychology (not equity/DEI framing) and is designed to build a standardized framework for bias evaluation and automated reframing.

---

## Goals

1. Establish a canonical, indexed taxonomy of cognitive biases drawn from cognitive psychology literature.
2. Evaluate written text for the presence and severity of identified cognitive biases.
3. Reframe biased text to present the same information with reduced or removed cognitive distortion.
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
| `journalism_example` | A concrete example as it would appear in a news article, headline, or op-ed — written or sourced specifically for journalism context |
| `reframing_strategy` | How to rewrite or restructure text exhibiting this bias to reduce it; what information needs to be added, removed, or restructured |
| `reframing_example` | The `journalism_example` rewritten using the `reframing_strategy` |
| `common_confusions` | Other biases this one is frequently mistaken for, and how to distinguish them |
| `severity_signal` | Typical severity when present in journalism: high / medium / low, with rationale |
| `sources` | List of primary citations (author, year, title, DOI or URL if available) |
| `status` | `canonical` (cited primary source) or `provisional` (needs source) |

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

#### 1d. Index as Evaluation Substrate

The index is the direct input to the LLM evaluation pipeline:
- The evaluator prompt includes the full `identification_criteria` and `linguistic_signals` for each candidate bias
- The reframing prompt uses the `reframing_strategy` and `reframing_example` as few-shot examples
- Confidence scores in evaluations are calibrated against the `severity_signal` and `common_confusions` fields
- When a new bias is added to the index, the evaluation and reframing pipelines automatically gain coverage for it — no prompt changes required

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

### Stack
- **Frontend:** Streamlit
- **LLM Backend:** Anthropic Claude API (claude-sonnet or claude-opus, configurable)
- **Article Fetching:** `newspaper3k` or `trafilatura` for URL parsing
- **Data Storage (MVP):** In-memory / session state; JSON files for bias taxonomy
- **Data Storage (Phase 2):** SQLite or Postgres for article cache and evaluation history

### Key Modules
```
refract/
├── app.py                          # Streamlit entrypoint (mirrors balt311 app/app.py)
├── pages/
│   ├── 1_bias_index.py             # Bias taxonomy browser
│   ├── 2_article_eval.py           # Single article evaluation
│   ├── 3_reframe.py                # Article reframing
│   └── 4_framework_dashboard.py   # Eval scores, version history, feedback
├── components/                     # Shared UI components (mirrors balt311 components/)
│   ├── eval_display.py             # Renders bias instance cards
│   ├── reframe_display.py          # Side-by-side original / reframed
│   └── stats_display.py            # Prevalence charts, category breakdowns
├── src/refract/
│   ├── ingest.py                   # Article fetch: trafilatura URL scrape + Guardian API
│   │                               # (exponential backoff retry, mirrors balt311 ingest.py)
│   ├── bias_eval.py                # Two-pass LLM evaluation pipeline + recall probes
│   ├── reframe.py                  # LLM reframing pipeline
│   └── prompts/
│       ├── system_prompt.txt       # Versioned system prompt
│       ├── taxonomy_injection.py   # Builds taxonomy block from taxonomy.json at runtime
│       └── reframe_prompt.txt      # Versioned reframing prompt
├── bias_index/
│   ├── taxonomy.json               # Canonical bias taxonomy (versioned, committed)
│   └── CHANGELOG.md               # Taxonomy change history
├── data/
│   ├── processed/                  # Committed: demo eval results, cached 100-article stats
│   └── raw/                        # Gitignored: fetched article text cache
├── eval/
│   ├── test_set/                   # Labeled articles + annotations
│   ├── results/                    # Stored scores per framework version
│   └── scoring.py                  # F1 scoring (post-POC)
├── scripts/
│   └── batch_eval.py               # Headless 100-article pipeline (mirrors balt311 pipeline.py)
├── config.py                       # API key management, framework version, feature flags
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

**Q5 — Reframe quality flagging:** Should reframes be explicitly labeled as AI-generated in the UI, and should there be a confidence indicator on the reframe quality?

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

## Success Metrics
- Taxonomy covers all major cognitive bias categories recognized in the literature
- Evaluation correctly identifies bias type and excerpt with >80% agreement against human-labeled test set
- Reframes preserve factual content (verifiable against original) in >95% of cases
- UI is usable without documentation for a non-technical user

