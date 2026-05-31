# Refract — Evaluation Framework
## Technical Overview

---

## Purpose

This document specifies how Refract evaluates articles for cognitive bias, how it evaluates its own evaluations, and how the framework improves over time. It is the operational companion to the product requirements — where REQUIREMENTS.md says *what* to build, this document says *how the core analytical pipeline works*.

---

## The Core Problem: 180 Classes, One Article

A naive approach — inject all ~180 bias definitions into a single prompt and ask the model to identify which are present — fails at scale. Research on large-taxonomy LLM classification is clear:

- On benchmarks with 174 classes, most LLMs achieve **zero accuracy** under single-pass full-taxonomy prompting (LongICLBench, 2024)
- LLM performance degrades measurably when prompts exceed 70–80% of the context window
- GPT-4 shows ~15% accuracy degradation extending from 4K to 128K tokens
- Multi-pass approaches with verification improve F1 from ~0.30 to ~0.44–0.46 vs. single-pass alone
- Beyond a minimal effective context size, adding more class definitions yields marginal or negative returns

The solution is a **two-mode architecture** that matches evaluation depth to the use case.

---

## Two Evaluation Modes

### Mode A — Deep Evaluation

*Used for: building and validating the test set, gold-standard annotation, single-article detailed review in the UI*

**Goal:** Maximize recall. Find every bias that is present. Accept higher latency and cost.

**Pipeline:**

```
Article text
     │
     ▼
┌─────────────────────────────────────┐
│  Pass 1: Category Classification    │
│  Prompt: article + 10 category      │
│  descriptions (~500 tokens)         │
│  Output: top 2-3 likely categories  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Pass 2: Bias Identification        │
│  Prompt: article + full entries     │
│  for biases in selected categories  │
│  (~15-25 biases, ~3,000-5,000 tokens│
│  of taxonomy content)               │
│  Output: detected bias instances    │
│  with excerpts, confidence, severity│
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Pass 3: Self-Verification          │
│  Prompt: article + detected         │
│  instances + verification rubric    │
│  "For each finding, confirm: is     │
│  the excerpt genuine? Is the        │
│  category label correct? Could this │
│  be confused with another bias?"    │
│  Output: confirmed / revised /      │
│  rejected instances                 │
└──────────────┬──────────────────────┘
               │
               ▼
        Structured JSON result
        (framework_version, mode: "deep")
```

**Why three passes:**
- Pass 1 is cheap (small prompt) and gates the expensive Pass 2 to a focused subset
- Pass 2 uses full `identification_criteria` and `linguistic_signals` from the taxonomy — the richness that makes detection reliable
- Pass 3 addresses the known weakness of single-pass LLM classification: low inter-instance consistency and conflation of similar biases. Research shows self-verification improves F1 by ~14 points.

---

### Mode B — Bulk Evaluation

*Used for: multi-article event analysis, publication inventory, GenAI batch review*

**Goal:** Balance speed and cost. Accept some recall loss for throughput.

**Pipeline:**

```
Article text
     │
     ▼
┌─────────────────────────────────────┐
│  Embedding Pre-Filter               │
│  Embed article text                 │
│  Compute cosine similarity to each  │
│  bias entry's definition + signals  │
│  Rank and select top N=25 biases    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  Single Evaluation Call             │
│  Prompt: article + top 25 bias      │
│  entries (~4,000-6,000 tokens of    │
│  taxonomy content)                  │
│  Output: detected bias instances    │
└──────────────┬──────────────────────┘
               │
               ▼
        Structured JSON result
        (framework_version, mode: "bulk")
```

**Trade-offs:**
- Eliminates Pass 1 and Pass 3; replaces Pass 1's category filter with embedding similarity
- Embedding pre-filter is fast and cheap (local model or small API call)
- Known recall risk: biases that are present but don't surface in embedding similarity may be missed. This is acceptable for trend/inventory use cases, but not for ground-truth annotation.
- Mode B results are always tagged as `mode: "bulk"` in the output schema; they are not used to populate the gold-standard test set

---

## Evaluation Output Schema

All evaluations, regardless of mode, produce the same JSON structure:

```json
{
  "article_id": "string",
  "source_url": "string | null",
  "evaluated_at": "ISO8601 timestamp",
  "framework_version": "string",
  "taxonomy_version": "string",
  "model": "string",
  "mode": "deep | bulk",
  "bias_instances": [
    {
      "bias_id": "string",
      "bias_name": "string",
      "category": "string",
      "excerpt": "string",
      "explanation": "string",
      "confidence": "high | medium | low",
      "severity": "high | medium | low",
      "verified": true,
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

The `verified` field is `true` for instances that passed Pass 3 in Mode A; always `null` in Mode B.

---

## Prompt Architecture

### System Prompt (stable, versioned)

Sets evaluator role and hard constraints. Key constraints baked into every evaluation:

1. Only identify biases with direct textual evidence — do not infer author intent
2. Quote the specific excerpt, not a paraphrase
3. Distinguish `author_exhibiting` (the author's own framing exhibits the bias) from `source_reporting` (the author is accurately reporting on a biased source)
4. Flag low-confidence detections — do not suppress them
5. Output must be valid JSON matching the schema above — no prose explanation outside the schema
6. If a bias could plausibly be categorized under two bias types, report the most specific one and note the alternative in `explanation`

### Taxonomy Injection (runtime, generated from `taxonomy.json`)

For each bias included in the call, inject:

```
BIAS: {name} [{category}]
Definition: {definition}
Mechanism: {mechanism}
Identification criteria: {identification_criteria}
Linguistic signals: {linguistic_signals}
Common confusions: {common_confusions}
---
```

The `journalism_example` and `reframing_example` fields from the taxonomy are **not** injected at evaluation time — they are used in Pass 3 verification and in the reframing pipeline, not in the initial detection pass. This keeps the evaluation prompt lean.

### Per-Call Context

- Article text (trimmed to configurable max, default 8,000 words)
- Article type if known: `news_report | opinion | headline | social_media | genai_output`
- Source publication if known (affects how `author_exhibiting` vs. `source_reporting` is adjudicated)

---

## Evaluation of the Evaluations (Meta-Evaluation)

### Ground Truth: The Test Set

Stored in `eval/test_set/`. Each entry:

```json
{
  "article_id": "string",
  "source_url": "string",
  "article_text": "string",
  "article_type": "string",
  "annotations": [
    {
      "bias_id": "string",
      "excerpt": "string",
      "rationale": "string",
      "confidence": "high | medium | low",
      "severity": "high | medium | low",
      "annotator": "string",
      "annotation_date": "ISO8601"
    }
  ],
  "inter_rater_notes": "string | null"
}
```

Target: 30 articles for MVP, growing to 100+ over time. Articles should cover:
- All 10 bias categories (at least 3 articles each)
- Mix of article types (news report, opinion, headline)
- Mix of bias density (lightly biased, moderately biased, heavily biased)
- Mix of bias subtlety (obvious instances, ambiguous instances)

### Annotation Process

1. Single annotator produces initial annotation using the bias index as reference
2. A second annotator (or LLM judge, see below) reviews independently
3. Disagreements are resolved by discussion and recorded in `inter_rater_notes`
4. Target inter-rater agreement: Cohen's kappa ≥ 0.65 (substantial agreement) before an article is admitted to the test set
5. Articles that cannot reach kappa ≥ 0.65 after discussion are excluded or held as "ambiguous" examples

### Automated Scoring

Run `eval/scoring.py` against any framework version to produce:

| Metric | Formula | Notes |
|---|---|---|
| Precision | TP / (TP + FP) | Per-category and overall |
| Recall | TP / (TP + FN) | Per-category and overall |
| F1 | 2 × (P × R) / (P + R) | Primary headline metric |
| Excerpt match | Fuzzy match of quoted excerpt vs. gold | Threshold: 80% token overlap |
| Category accuracy | Correct category / all detected | When bias is detected, is category right? |
| False positive rate | FP / (FP + TN) | How noisy is the output? |
| Confidence calibration | P(correct \| high conf) vs. P(correct \| low conf) | Should be monotonically ordered |
| Mode A vs. Mode B delta | F1_A - F1_B | Quantifies the recall cost of bulk mode |

Results stored as `eval/results/{framework_version}_{mode}.json`.

---

## Evaluation Judges

Three judge configurations are supported, selectable per evaluation session:

### 1. Pure LLM Judge

A second LLM call reviews the evaluation output against the article text:

```
You are a bias evaluation reviewer. Given:
- The original article
- A set of detected bias instances (each with bias name, excerpt, explanation, confidence)

For each instance, assess:
1. Is the excerpt genuine (present verbatim or near-verbatim in the article)? [yes/no]
2. Does the excerpt plausibly exhibit the named bias per the definition provided? [yes/no/partial]
3. Is the explanation accurate and non-circular? [yes/no]
4. Is the confidence rating appropriate? [appropriate/too-high/too-low]

Return structured JSON. Do not add new detections — only review existing ones.
```

Use a **different model** from the evaluator when possible (e.g., evaluate with Claude Sonnet, judge with Claude Opus) to reduce self-consistency bias. Research shows LLM judges agree with humans >80% of the time on general tasks, dropping to 60–70% in specialized domains — cognitive bias detection is specialized, so LLM-only judgment is a floor, not a ceiling.

### 2. Hybrid Human / LLM Judge

LLM judge runs first (as above). Human reviewer sees:
- Original article
- Detected instances
- LLM judge's assessment of each instance
- Flags where LLM judge had low confidence or disagreed with the evaluator

Human reviews flagged instances only, plus a random 20% sample of agreed instances (to catch systematic LLM judge errors). Human marks: **Agree / Disagree / Partially agree** with optional note.

This is the recommended mode for test set construction — it keeps human effort focused on ambiguous cases while maintaining oversight of the full output.

### 3. Pure Human Judge

Human reviews all detected instances without LLM pre-screening. Used only for initial test set bootstrapping (to avoid anchoring on LLM output) and for periodic audits of the hybrid mode.

---

## Framework Iteration Cycle

```
1. SIGNAL
   Automated scores + human feedback surface a gap
   Example: "Narrative fallacy recall = 0.42 — framework is missing 58% of instances"

2. DIAGNOSE
   Pull false negatives from test set. Inspect: are identification_criteria too narrow?
   Are linguistic_signals missing key patterns? Is this a taxonomy entry problem or a
   prompt structure problem?

3. HYPOTHESIZE
   One of three fix types:
   A. Taxonomy entry update (identification_criteria, linguistic_signals, common_confusions)
   B. System prompt template update (constraints, output format, verification rubric)
   C. Test set expansion (add articles that cover the gap)
   Never fix A and B simultaneously — isolate variables

4. IMPLEMENT
   Changes on a feature branch. Increment minor version (v1.2.0 → v1.3.0).
   Update CHANGELOG.md with: what changed, why, which gap it targets.

5. EVALUATE
   Run full test set against new version (both modes).
   Compare to prior version on: overall F1, per-category F1, false positive rate.
   A change is accepted if:
   - Overall F1 improves or holds (within ±0.02)
   - Targeted category F1 improves
   - False positive rate does not increase by more than 0.05
   A change is rejected if it causes regression in a category not targeted by the fix.

6. MERGE
   Accepted changes merge to main. Framework version tag created.
   Prior evaluation results retain their version tag — never retroactively re-scored.
```

---

## Mode Comparison: When to Use Which

| | Mode A (Deep) | Mode B (Bulk) |
|---|---|---|
| **Use for** | Test set annotation, single-article UI review, validation | Multi-article sweeps, publication inventory, GenAI batch |
| **Passes** | 3 (category → identify → verify) | 1 (embedding filter → identify) |
| **Taxonomy coverage** | Category-filtered full entries (~15–25 biases) | Embedding-ranked top 25 biases |
| **Latency** | ~15–45s per article | ~3–8s per article |
| **Cost** | ~3–5× bulk | Baseline |
| **Recall** | High (maximized) | Medium (embedding filter introduces miss risk) |
| **Precision** | High (Pass 3 verification removes false positives) | Medium |
| **Output trustworthiness** | Gold-standard quality | Trend/inventory quality |
| **Used for test set?** | Yes | No |

---

## Reframe Quality Evaluation

The reframing pipeline needs its own scoring rubric, separate from the detection pipeline. Proposed rubric (to be validated):

| Dimension | Scoring | Method |
|---|---|---|
| **Factual preservation** | All facts in original present in reframe | LLM judge comparison + human spot-check |
| **Bias reduction** | Re-evaluate the reframe with Mode A; compare bias_count to original | Automated (run Mode A on reframe) |
| **No new claims** | Reframe introduces no claims absent from original | LLM judge: "Does the reframe assert anything not in the original?" |
| **Readability** | Flesch-Kincaid or similar; reframe should not be harder to read | Automated |
| **Completeness** | All identified biases addressed in reframe | Cross-reference bias_instances vs. reframe annotations | 

A reframe passes QA if: factual preservation = 100%, bias reduction > 50% (bias_count drops by at least half), no new claims, completeness ≥ 80% of identified biases addressed.

---

## Key References

- [Single-pass Hierarchical Text Classification with LLMs](https://payberah.github.io/files/download/papers/llm_classification.pdf)
- [TELEClass: Taxonomy Enrichment and LLM-Enhanced Hierarchical Text Classification](https://arxiv.org/html/2403.00165v3)
- [SALSA: Single-pass Autoregressive LLM Structured Classification](https://arxiv.org/pdf/2510.22691)
- [LLMs-as-Judges: A Comprehensive Survey on LLM-based Evaluation Methods](https://arxiv.org/html/2412.05579v2)
- [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://arxiv.org/html/2510.05381v1)
- [Why Does the Effective Context Length of LLMs Fall Short?](https://arxiv.org/pdf/2410.18745)
- [Optimizing LLM Annotation through Multi-Agent Orchestration](https://arxiv.org/pdf/2603.13353)
- [Human-Centered Design Recommendations for LLM-as-a-Judge](https://aclanthology.org/2024.hucllm-1.2.pdf)
