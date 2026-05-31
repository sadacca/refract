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

**Purpose:** Provide a browsable, searchable reference of cognitive bias categories and examples — the foundation for all downstream evaluation.

**Requirements:**
- Display a structured taxonomy of cognitive bias categories (e.g., attribution biases, availability heuristics, confirmation bias, framing effects, anchoring, in-group bias, narrative bias, etc.)
- Each bias entry includes:
  - Name and category
  - Cognitive psychology definition (plain language)
  - Mechanism: how the bias distorts perception or reasoning
  - Example in neutral prose
  - Example as it appears in journalism/written media
  - Severity signal: how detectable and distorting the bias typically is
- Index is searchable by name, category, and keyword
- Index is version-controlled and extensible (new biases can be added)
- Source taxonomy draws from established references (Kahneman, Tversky, Cialdini, Wikipedia cognitive bias codex, etc.)

**UI:**
- Sidebar nav or tabbed layout
- Card or table view with expandable detail panels
- Filter by category, severity, or type (cognitive vs. social vs. memory)

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

### Stack
- **Frontend:** Streamlit
- **LLM Backend:** Anthropic Claude API (claude-sonnet or claude-opus, configurable)
- **Article Fetching:** `newspaper3k` or `trafilatura` for URL parsing
- **Data Storage (MVP):** In-memory / session state; JSON files for bias taxonomy
- **Data Storage (Phase 2):** SQLite or Postgres for article cache and evaluation history

### Key Modules
```
refract/
├── app.py                  # Streamlit entrypoint
├── bias_index/
│   ├── taxonomy.json       # Canonical bias taxonomy
│   └── index.py            # Load, search, display taxonomy
├── evaluator/
│   ├── article_fetch.py    # URL → clean text
│   ├── bias_eval.py        # LLM bias evaluation pipeline
│   └── prompts.py          # Structured prompts for eval and reframe
├── reframer/
│   └── reframe.py          # LLM reframing pipeline
├── ui/
│   ├── pages/
│   │   ├── 1_bias_index.py
│   │   ├── 2_article_eval.py
│   │   └── 3_reframe.py
│   └── components.py       # Shared UI components
├── config.py               # App config, API key management
├── requirements.txt        # Python dependencies
└── .env.example            # Environment variable template
```

### LLM Prompt Design Principles
- All evaluation prompts reference the canonical taxonomy by category name and definition
- Output is requested as structured JSON with defined schema (bias name, excerpt, explanation, confidence, severity)
- Reframing prompts explicitly constrain the model: preserve facts, do not add claims, flag gaps
- System prompts are versioned alongside the taxonomy

### Evaluation Output Schema (JSON)
```json
{
  "article_id": "string",
  "source_url": "string | null",
  "evaluated_at": "ISO8601 timestamp",
  "bias_instances": [
    {
      "bias_name": "string",
      "category": "string",
      "excerpt": "string",
      "explanation": "string",
      "confidence": "high | medium | low",
      "severity": "high | medium | low"
    }
  ],
  "summary": {
    "dominant_categories": ["string"],
    "overall_severity": "high | medium | low",
    "bias_count": "integer"
  }
}
```

---

## Non-Goals (MVP)
- Real-time streaming news ingestion
- User accounts or authentication
- Political or ideological scoring (this is cognitive psychology framing only)
- Fact-checking or claim verification

---

## Open Questions / Decisions Needed
1. **Taxonomy source:** Use an existing codex (e.g., Wikipedia's cognitive bias codex, ~180 biases) as the base, or curate a smaller focused set (~30-50) for journalism-specific relevance?
2. **LLM model selection:** Claude Sonnet (faster/cheaper) vs. Opus (more nuanced) — or make it user-configurable?
3. **News API:** Use a service (NewsAPI, GDELT) for multi-article fetch, or require manual URL input for MVP?
4. **Severity scoring:** Binary (present/absent) or graduated scale for MVP?
5. **Reframe quality:** Should reframes be flagged as AI-generated in the UI?

---

## Success Metrics
- Taxonomy covers all major cognitive bias categories recognized in the literature
- Evaluation correctly identifies bias type and excerpt with >80% agreement against human-labeled test set
- Reframes preserve factual content (verifiable against original) in >95% of cases
- UI is usable without documentation for a non-technical user

