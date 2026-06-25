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
- `GEMINI_API_KEY` — judge model (cross-family default)
- `CEREBRAS_API_KEY` — optional fallback eval/triage provider
- `MISTRAL_API_KEY` — optional fallback eval/triage provider; primary for `precompute_examples.py`

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
| 2, 4 | `groq/gpt-oss-120b` | Complex identification and judgment |

`llama-3.3-70b-versatile` and `llama-3.1-8b-instant` were deprecated by Groq on the free/dev tier on 2026-06-17; `groq/gpt-oss-120b` is Groq's recommended replacement and is now the `EVAL_CHAIN` primary (see below). Groq's free tier is also tighter than it used to be — per-model RPD dropped from 14,400 to ~1,000, and tokens-per-day (TPD) is the binding constraint for Pass 2's full-article prompts (`MODEL_TPD_LIMITS` in `config.py`).

Both configurable via `TRIAGE_MODEL` and `EVAL_MODEL` / `JUDGE_MODEL` env vars. `llm_client.py` is provider-agnostic — Groq, Gemini, Cerebras, and Mistral models can all serve as eval, triage, or judge.

### Model fallback chains

Defined in `config.py`, used by `select_from_chain()` to pick the least-used model under its free-tier daily RPD *and* TPD limit (the latter via `MODEL_TPD_LIMITS`, where listed):

| Chain | Order | Used by |
|---|---|---|
| `EVAL_CHAIN` | Groq `gpt-oss-120b` → Groq `llama-3.3-70b-versatile` (deprecated, fallback only) → Cerebras `gpt-oss-120b` → Mistral `mistral-large-latest` | Pass 2 identification (high-volume; Groq-primary for throughput) |
| `TRIAGE_CHAIN` | Groq `llama-3.1-8b-instant` → Cerebras `llama-3.1-8b` → Mistral `mistral-small-latest` | Pass 0/1/3 (small-model calls) |
| `PRECOMPUTE_CHAIN` | Mistral `mistral-large-latest` → Groq `llama-3.3-70b-versatile` → Cerebras `gpt-oss-120b` | `precompute_examples.py` (low-volume one-shot generation; Mistral-primary since throughput doesn't matter at this scale) |
| `GEMINI_JUDGE_CHAIN` | `gemini-3.1-flash-lite` → `gemma-4-31b-it` → `gemma-4-26b-a4b-it` | Pass 4 judge (cross-family default) |

`precompute_examples.py` additionally falls through the chain on a hard failure (HTTP error, decommissioned model, missing key), not just proactive RPD-based selection — if the primary model errors, it retries the next one in order rather than failing the bias entry outright. Pass 2 (`evaluate_article`) does the same: a 429 mid-article switches to the next `EVAL_CHAIN` model for the rest of that article instead of failing it outright, and `call_llm` distinguishes a transient per-minute throttle (short `Retry-After`, worth a short sleep-and-retry) from a daily cap (long or missing `Retry-After`, fails fast so the chain fallback can act immediately).

Each provider is paced according to its actual free-tier RPM cap (`llm_client._PROVIDER_MIN_INTERVALS`): Groq/Cerebras/Gemini at 6s between calls, Mistral at 31s (its 2 RPM hard limit). Override globally with `LLM_CALL_INTERVAL`.

### Rate-limit tracking

`config.MODEL_LIMITS` flattens `MODEL_REGISTRY` into a per-model RPM/RPD/TPM/TPD lookup — single source of truth, no duplicated numbers across dicts. Cerebras and Mistral cap usage at the account level (not per model), so every model on those providers maps to a shared `scope_key` (`"cerebras:account"`, `"mistral:account"`); `llm_client.py`'s daily usage tracking and `select_from_chain()`'s TPD checks key off this `scope_key`, so switching between e.g. `cerebras/gpt-oss-120b` and `cerebras/qwen-3-32b` correctly pools against one shared daily budget instead of two independent ones. Groq and Gemini remain per-model.

On top of the static per-call pacing (`_min_interval_for`), `llm_client._wait_for_rpm()` enforces each model's actual RPM cap with a sliding 60s window keyed by `scope_key` — this catches bursts that static pacing alone would miss when multiple models share an account-wide RPM limit (e.g. Mistral's 2 RPM applies across all five Mistral models, not five separate 2 RPM allowances).

### Token efficiency

Measured at the original taxonomy size (7 biases, 6 categories; superseded by the current 14-bias/8-category taxonomy) on an 8,000-word article:

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
│   ├── llm_client.py               # Provider-agnostic LLM client (Groq, Gemini, Cerebras, Mistral)
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

Fourteen biases across eight categories (taxonomy `v0.2.0`), sourced from "Cognitive Biases in Written Text: Operationalized Definitions, Diagnostic Criteria, and Examples" — see `bias_index/CHANGELOG.md` for the full revision history:

| Bias | Category |
|---|---|
| Availability Heuristic | Attention & Memory |
| Hindsight Bias | Memory |
| Anchoring Effect | Judgment & Decision-Making |
| Conjunction Fallacy | Probability Reasoning |
| Base Rate Neglect | Probability Reasoning |
| Framing Effect | Judgment & Decision-Making |
| Fundamental Attribution Error | Social Cognition |
| Sunk Cost Fallacy | Judgment & Decision-Making |
| Overconfidence Bias | Judgment & Metacognition |
| Scope Insensitivity | Judgment & Moral Reasoning |
| Gambler's Fallacy | Probability Reasoning |
| Hyperbolic Discounting | Judgment & Decision-Making |
| Actor-Observer Asymmetry | Social Cognition |
| Dunning-Kruger Effect (Overestimation Variant) | Metacognition |

Each bias entry includes: definition, identification criteria, linguistic signals, common confusions, a `contrast_statement`, and reference examples (positive, near-miss, contrast). All entries are currently `examples_status: "pending"` — candidate examples are generated by `scripts/precompute_examples.py` into `data/pending_examples/` and require human review via the Framework Dashboard before being accepted into `taxonomy.json`.

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
- All 14 biases have `examples_status: "pending"` — reference examples are LLM-generated candidates awaiting human review, not yet verified against the source literature
- Pass 2 currently falls back to criteria-only detection (no few-shot anchors) until candidate examples are reviewed and accepted into `taxonomy.json`
- The taxonomy covers only the biases in the source document. Many important biases (selection bias, false balance, source bias) are not yet modeled

**Scope:**
- Evaluated only on English-language text
- Tested primarily on short-to-medium news articles (200–700 words); pipeline behavior on long-form journalism (3,000+ words) is not characterized
- No ground-truth labeled dataset exists for precision/recall measurement — all quality assessment is currently LLM-self-evaluation (Pass 4), which has known limitations

**Infrastructure:**
- Groq free tier TPM/TPD limits constrain batch throughput — as of 2026-06 these are tighter than this codebase originally assumed (per-model RPD dropped from 14,400 to ~1,000), and Pass 2's full-article prompts can trip the tokens-per-day cap after only a handful of articles, well before the request count looks high. `MODEL_TPD_LIMITS` (`config.py`) and per-call token tracking (`llm_client.get_daily_tokens`) make this visible to `select_from_chain()`; per-provider call pacing and cross-provider fallback chains (`EVAL_CHAIN`, `TRIAGE_CHAIN`, `PRECOMPUTE_CHAIN`) mitigate but do not eliminate 429 errors on long articles
- Provider model catalogs change without notice — Groq decommissioned `deepseek-r1-distill-llama-70b` (a prior `EVAL_MODEL` default) without a deprecation window, and deprecated `llama-3.3-70b-versatile`/`llama-3.1-8b-instant` on the free/dev tier on 2026-06-17; `call_llm` now fails fast on HTTP 400 (unrecoverable) and on HTTP 429 with a long/missing `Retry-After` (daily cap, not worth retrying the same model), so callers can fail over to the next chain model instead of burning the retry budget — but model IDs in `config.py` should still be spot-checked periodically
- `data/processed/` results are committed to the repository — appropriate for a small research corpus, not for production scale
