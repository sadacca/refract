# Refract

Cognitive bias analysis and reframing for news articles.

Refract runs a multi-pass LLM evaluation pipeline against article text, identifies specific instances of cognitive bias with exact excerpts and explanations, and surfaces patterns across a corpus. It is built as a research and journalism tool, not an editorial judgment system — cognitive bias is a normal feature of human cognition.

---

## Overview

The core problem: cognitive bias in journalism is pervasive but hard to measure systematically. A human reader can sense framing or selective emphasis, but cataloguing it across dozens of articles at the excerpt level requires significant effort. Refract automates that cataloguing using a structured taxonomy and a tiered LLM pipeline designed for precision over recall.

Key design principles:
- **Taxonomy-first**: all bias definitions, identification criteria, and reference examples live in `bias_index/taxonomy.json`. The pipeline has no hardcoded bias knowledge — swap or extend the taxonomy and the pipeline adapts.
- **Determinism where possible**: prompt blocks are precomputed from the taxonomy and stored in `data/precomputed/`. Only the LLM labeling calls are probabilistic.
- **Precision over recall**: a four-pass pipeline with an independent LLM judge filters false positives before results are written. It is better to miss an instance than to misattribute one.
- **Token efficiency**: paragraph-level triage (Pass 0) means each LLM call receives only the article text relevant to its task, not the full article every time.

---

## How to Use

### Prerequisites

```bash
pip install -r requirements.txt
cp .env.example .env   # add your API keys
```

API keys needed:
- `GROQ_API_KEY` — primary LLM provider (free tier sufficient for development)
- `GEMINI_API_KEY` — optional fallback/judge model

### Precompute taxonomy artifacts

Must be run once before any evaluation, and again after any taxonomy change:

```bash
python scripts/precompute.py
```

Produces prompt blocks in `data/precomputed/` used by the evaluation pipeline.

### Evaluate articles (batch)

Add article URLs (one per line) to `data/input/article_urls.txt`, then:

```bash
python scripts/batch_eval.py --max 5
python scripts/batch_eval.py --no-skip-cached   # re-evaluate already-processed articles
python scripts/batch_eval.py --mode flat        # skip category triage, run all categories directly
```

Results are written to `data/processed/<article_id>_<framework_version>.json`.

### Rebuild the index

```bash
python scripts/build_index.py
```

Updates `data/processed/index.json`, `stats.json`, and `bias_frequency.json`.

### Generate a text report

```bash
python scripts/report.py                  # all articles
python scripts/report.py --min-words 300  # skip short articles
python scripts/report.py --out report.txt
```

### Run the Streamlit app locally

```bash
streamlit run app.py
```

### GitHub Actions (automated)

| Workflow | Trigger | Purpose |
|---|---|---|
| `smoke_test.yml` | Push to `claude/**`, `main` | Imports, taxonomy schema, artifact counts |
| `precompute.yml` | Manual | Rebuild `data/precomputed/` from taxonomy |
| `batch_eval.yml` | Manual | Evaluate articles from `article_urls.txt` |
| `build_index.yml` | Manual | Rebuild index/stats from processed results |
| `precompute_examples.yml` | Manual | Generate candidate reference examples for review |

The `batch_eval` workflow exposes inputs for `eval_mode` (deep/flat), `skip_cached`, and `max_articles`.

---

## Architecture

### Evaluation pipeline

```
Article URL
    │
    ▼
Pass 0: Paragraph triage          [small model — 1 call]
    │   Chunk article → map categories to relevant paragraph indices
    │   Zero-paragraph gate: skip Pass 2 for categories with no relevant paragraphs
    │
    ├─ deep mode ──────────────────────────────────────────────────────────────
    │   Pass 1: Category triage   [small model — 1 call]
    │       Flag broad categories plausibly present
    │   Pass 2: Bias identification [large model — 1 call per flagged category]
    │       Identify specific instances using paragraph-filtered article text
    │   Pass 3: Recall probes     [small model — 1 call per unflagged category]
    │       Batched yes/no sweep to surface missed instances
    │
    └─ flat mode ──────────────────────────────────────────────────────────────
        Pass 2: Bias identification [large model — 1 call per category]
            All categories, no triage, paragraph-filtered article text

Pass 4: LLM judge                 [large model — 1 call]
    │   Pointwise verdict on all detections: confirmed / suspect / rejected
    │   Rejected instances filtered before output is written
    │
    ▼
data/processed/<article_id>_<framework_version>.json
```

### Model tiers

| Pass | Model | Rationale |
|---|---|---|
| 0, 1, 3 | `llama-3.1-8b-instant` | Simple classification/yes-no — fast, low token cost |
| 2, 4 | `llama-3.3-70b-versatile` | Complex identification and judgment |

Both configurable via `TRIAGE_MODEL` and `EVAL_MODEL` / `JUDGE_MODEL` env vars.

### Token efficiency

At current taxonomy size (7 biases, 6 categories) on an 8,000-word article:

| Pipeline | Tokens | Calls |
|---|---|---|
| Original (no optimization) | ~19,700 | 9 |
| + Pass 0 paragraph triage + batched Pass 3 + zero-paragraph gate | ~12,200 | 9 |

At 10× scale (70 biases, 15 categories): ~57% token reduction, 22 fewer calls.

---

## Repository Organization

```
refract/
├── app.py                          # Streamlit entry point
├── config.py                       # Central config — paths, models, versions
├── requirements.txt
│
├── pages/
│   ├── 1_analysis.py               # Bias analysis dashboard (3 tabs)
│   ├── 2_bias_index.py             # Taxonomy browser
│   ├── 3_article_eval.py           # Live article evaluation UI
│   ├── 4_reframe.py                # Article reframing UI
│   └── 5_framework_dashboard.py    # Taxonomy status and corpus metrics
│
├── src/refract/
│   ├── bias_eval.py                # 4-pass evaluation pipeline
│   ├── llm_client.py               # Provider-agnostic LLM client (Groq + Gemini)
│   └── ingest.py                   # Article fetching (trafilatura + requests)
│
├── scripts/
│   ├── batch_eval.py               # Headless batch evaluation
│   ├── build_index.py              # Rebuild processed/ index and stats
│   ├── precompute.py               # Build prompt blocks from taxonomy
│   ├── precompute_examples.py      # Generate candidate reference examples
│   └── report.py                   # Plain-text cross-article report
│
├── bias_index/
│   └── taxonomy.json               # Cognitive bias taxonomy (source of truth)
│
├── data/
│   ├── input/article_urls.txt      # URLs for batch evaluation
│   ├── precomputed/                # Prompt blocks built from taxonomy
│   ├── processed/                  # Evaluation results (JSON per article)
│   └── pending_examples/           # Candidate reference examples awaiting review
│
└── .github/workflows/              # GitHub Actions automation
```

---

## Taxonomy

Seven Tier 1 biases across six categories (all `status: provisional`):

| Bias | Category |
|---|---|
| Confirmation Bias | Confirmation & Belief Perseverance |
| Framing Effect | Framing & Anchoring |
| Anchoring | Framing & Anchoring |
| Availability Heuristic | Availability & Salience |
| Fundamental Attribution Error | Attribution & Causation |
| Negativity Bias | Affect & Emotional Reasoning |
| In-Group Bias | In-Group & Social |

Each bias entry includes: definition, identification criteria, linguistic signals, and reference examples (positive, near-miss, contrast). Examples are currently pending human review.

---

## Analysis

Results from the first batch of 5 news articles (NPR, ABC News, Yahoo Sports):

**Cross-article patterns:**
- Framing Effect appeared in 100% of articles — the most pervasive bias in the corpus
- Availability Heuristic appeared in 80% of articles, often co-occurring with Framing
- In-Group Bias and Negativity Bias were prominent in sports coverage specifically
- Judge quality was uniformly "medium" — no article scored "high", suggesting the identification criteria may still be over-inclusive for some biases (Anchoring in particular)

**What works well:**
- Excerpt-level detection is specific enough to be actionable — the exact quoted text makes verification easy
- The drug-boat strike article showed the most substantive detection: in-group/out-group language and numerical anchoring around cumulative death toll figures
- Sports journalism shows consistent and plausible Framing and Availability patterns

**Known issues with current results:**
- Short articles (under 300 words) have thin signal — most text is lede, leaving little body content for the pipeline to analyze
- Anchoring is the most over-detected bias; the judge flags it frequently as "suspect" or "rejected"
- The "Unknown" category in older results reflects a pre-fix bug where category was not stamped on instances — fixed in current pipeline

---

## Limitations

**Pipeline:**
- Pass 0 paragraph selection quality depends on the small model's ability to match abstract category names to concrete paragraph content — this mapping has not been formally evaluated
- The zero-paragraph gate in flat mode silently skips categories; in deep mode they fall to Pass 3, but the recall probe uses compact definitions which may miss nuanced instances
- Pass 4 judge verdict quality is untested at scale — "medium" overall quality across all articles may reflect judge calibration issues as much as detection quality

**Taxonomy:**
- All 7 biases are `status: provisional` — definitions and identification criteria have not been validated against the literature through formal review
- Reference examples are pending human review; the few-shot anchors used in Pass 2 are placeholder quality
- The taxonomy covers only Tier 1 biases. Many important biases (selection bias, false balance, source bias) are not yet modeled

**Scope:**
- Evaluated only on English-language text
- Tested primarily on short-to-medium news articles (200–700 words); pipeline behavior on long-form journalism (3,000+ words) is not characterized
- No ground-truth labeled dataset exists for precision/recall measurement — all quality assessment is currently LLM-self-evaluation (Pass 4), which has known limitations

**Infrastructure:**
- Groq free tier TPM limits constrain batch throughput; the per-model 6-second call interval and tiered model routing mitigate but do not eliminate 429 errors on long articles
- `data/processed/` results are committed to the repository — appropriate for a small research corpus, not for production scale
