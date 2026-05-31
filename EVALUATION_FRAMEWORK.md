# Refract — Evaluation Framework
## Technical Overview

---

## Scope Note: POC vs. Production

This document describes the full evaluation framework, including a production-grade section and a **POC-scoped section** that is the actual implementation target for the initial build. The full framework is documented for reference and to inform future iteration — not as a requirement for the first working version.

**The POC target:** A single developer, hobby project, proof of concept. The goal is to demonstrate that the detection and reframing pipeline works at all, get real examples in front of humans, and establish a baseline. Rigorous statistical validation comes later if the concept proves out.

**Rule of thumb for the POC:** If a step requires more than one additional API call per article, or more than 30 minutes of setup, it belongs in the full framework section, not the POC section.

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

## Precompute Phase: Reference Example Library

### The Core Problem with Probabilistic Detection

The original prompt design asked the model to evaluate an article against bias definitions and criteria — relying on the model's in-context, probabilistic understanding of what each bias looks like in text. This is wrong for two reasons:

1. **Non-deterministic:** Two runs of the same article may produce different detections, not because the article changed, but because the model generates a different internal representation of the bias each time.
2. **Unauditable:** When the model identifies confirmation bias in an excerpt, you cannot inspect *why* — what mental template it compared against. You can only see the output.

The fix: precompute a verified reference example set for every bias and inject it as few-shot anchors. Detection becomes **pattern-matching against a fixed reference**, not probabilistic generation.

---

### Precompute Pipeline

Before the evaluation pipeline runs on any article, a separate one-time (and periodically updated) precompute phase builds the reference library. This is a human-in-the-loop pipeline, not automated.

**Step 1 — Generate candidate examples**

For each bias entry in `taxonomy.json`, run a generation prompt:

```
You are building a reference library for detecting cognitive bias in journalism.

Bias: {name}
Definition: {definition}
Mechanism: {mechanism}
Identification criteria: {identification_criteria}

Generate the following, each as a separate JSON field:

positive_examples: 3 short excerpts (2-4 sentences each) from realistic news 
article text that clearly exhibit this bias. Vary the topic domain across examples 
(politics, economics, crime, science, sports). Each excerpt should exhibit the bias 
through a different linguistic mechanism.

near_miss_examples: 2 short excerpts that a reader might initially mistake for 
this bias but that do not actually exhibit it. Explain briefly why each is not 
an instance of the bias.

contrast_bias: 1 example that shows the most commonly confused bias 
({common_confusions}) to distinguish this bias from it.
```

**Step 2 — Human review**

Every generated example is reviewed by a human before entering the reference library:
- Positive examples: confirm the excerpt genuinely exhibits the bias mechanism (not just mentions bias-adjacent topics)
- Near-miss examples: confirm they are genuinely not instances of the bias
- Contrast examples: confirm they correctly illustrate the confusion boundary

Accepted examples are stored in the taxonomy entry. Rejected examples are logged with a rejection reason — useful for improving the generation prompt.

**Step 3 — Version and commit**

Updated `taxonomy.json` with populated `reference_examples` fields is committed. The `framework_version` minor version increments when any reference example changes.

---

### Updated Taxonomy Entry Schema

Add `reference_examples` to each bias entry:

```json
{
  "id": "confirmation-bias",
  "name": "Confirmation Bias",
  ...
  "reference_examples": {
    "positive": [
      {
        "text": "The senator's long record of supporting renewable energy legislation was prominently featured, while her three votes against climate bills went unmentioned.",
        "domain": "politics",
        "mechanism": "selective omission of disconfirming evidence",
        "verified": true,
        "verified_by": "human",
        "verified_at": "2025-06-01"
      }
    ],
    "near_miss": [
      {
        "text": "The report covered both sides of the debate, quoting experts who supported and opposed the policy in roughly equal measure.",
        "why_not": "Balanced sourcing is not confirmation bias even if the reporter personally agrees with one side — the bias requires selective presentation of evidence, not personal belief.",
        "verified": true
      }
    ],
    "contrast": {
      "confused_with": "myside-bias",
      "text": "...",
      "distinction": "..."
    }
  }
}
```

---

### How Reference Examples Change the Prompt

**Pass 2 (Bias Identification) — with examples injected:**

```
BIAS: Confirmation Bias [Confirmation & Belief Perseverance]
Definition: ...
Mechanism: ...
Identification criteria: ...
Linguistic signals: ...

REFERENCE EXAMPLES — this is what confirmation bias looks like in journalism:
Example 1 (selective omission): "The senator's long record of supporting renewable 
energy legislation was prominently featured, while her three votes against climate 
bills went unmentioned."
Example 2 (source selection): ...
Example 3 (framing): ...

NEAR MISSES — these are NOT confirmation bias:
Near miss 1: "The report covered both sides..." — Why not: balanced sourcing is 
not confirmation bias even if the reporter personally agrees with one side.

CONTRAST — distinguish from myside bias:
...

Now evaluate the article below. Quote verbatim excerpts that match the pattern 
of the reference examples above. Do not flag excerpts that match the near-miss 
patterns.
```

The model is no longer generating its own representation of confirmation bias at inference time — it is comparing the article against a fixed, human-verified set of examples. Detection is anchored, auditable, and consistent across runs.

---

### Prompt Architecture (Updated)

### System Prompt (stable, versioned)

Sets evaluator role and hard constraints:

1. Only identify biases with direct textual evidence — do not infer author intent
2. Quote the specific excerpt verbatim — not a paraphrase
3. Distinguish `author_exhibiting` from `source_reporting`
4. Flag low-confidence detections — do not suppress them
5. Output must be valid JSON — no prose outside the schema
6. When an excerpt could match two bias types, report the most specific one and note the alternative
7. **Only flag excerpts that match the pattern of the provided reference examples — do not identify bias patterns not represented in the reference set**

### Taxonomy Injection (runtime, generated from `taxonomy.json`)

For each bias in the call, inject the full entry including reference examples:

```
BIAS: {name} [{category}]
Definition: {definition}
Mechanism: {mechanism}
Identification criteria: {identification_criteria}
Linguistic signals: {linguistic_signals}
Common confusions: {common_confusions}

REFERENCE EXAMPLES:
[positive_examples — text + mechanism label]

NEAR MISSES (do not flag these patterns):
[near_miss_examples — text + why_not]

CONTRAST WITH {confused_with}:
[contrast example + distinction]
---
```

This is larger per bias than the original injection (roughly 3–4× the tokens), but the number of biases per call is controlled by the category filter (Pass 1), so total prompt size remains within the effective context window.

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

### What the Research Says

The LLM-as-judge literature has matured significantly since 2023. Key findings directly relevant to Refract:

**Known failure modes of LLM judges:**
- **Position bias** — judges systematically prefer candidates presented first or last; swapping presentation order in pairwise tasks shifts accuracy by >10%
- **Verbosity bias** — longer, more formal outputs score higher regardless of correctness; artifact of RLHF training
- **Self-enhancement bias** — an LLM judge scores its own outputs higher than equally good outputs from other models; bias strength correlates linearly with self-recognition capability (NeurIPS 2024)
- **Criterion conflation / halo effect** — when a judge is asked to evaluate multiple criteria in a single call, scores on one criterion bleed into others

**What works:**
- **Rubric-anchored, criterion-separated evaluation** — evaluating each criterion in a separate call (or at minimum, separate prompt sections) substantially reduces halo effects and improves calibration. "RULERS" (2025) shows locked rubrics with evidence-anchored scoring produce significantly more robust evaluations than vague quality prompts
- **Ensemble / panel judging** — multi-model panels outperform single judges by 8–15% reliability; the gain comes from error independence across models. Majority vote captures most of the gain; minority-veto (any single dissent triggers "uncertain") increases true negative rate
- **Cross-model judging** — always use a different model family as judge than was used for evaluation; same-model judging inflates scores and introduces self-enhancement bias
- **Few-shot calibration** — providing the judge with 3–5 scored examples from the test set, with balanced verdicts, substantially improves consistency. Without calibration examples, judge base-rate prior dominates
- **Specialized evaluator models** — Prometheus 2 (open source, EMNLP 2024) is specifically trained for rubric-conditioned evaluation and achieves higher human correlation than GPT-4 on structured evaluation tasks. Worth considering as the judge model for cost-sensitive bulk evaluation

**The ceiling on LLM-only judgment:** In specialized domains, LLM judges agree with human experts only 60–70% of the time (vs. >80% on general tasks). Cognitive bias detection is a specialized domain. LLM-only judgment is therefore appropriate for fast iteration and bulk review, but cannot replace human oversight for test set construction or framework validation.

---

### Judge Design Principles for Refract

Given the above, the Refract judge layer is designed around five principles:

1. **One criterion per call** — the judge never evaluates excerpt validity, category correctness, explanation quality, and confidence calibration in a single call. Each is a separate evaluation with its own rubric section, to prevent halo effects.

2. **Locked rubric with evidence anchoring** — each criterion is scored against an explicit definition of what constitutes each score level, with a required evidence quote from the article. The judge cannot return a score without citing textual evidence.

3. **Cross-model by default** — the evaluator and judge are never the same model. Recommended pairing: evaluate with Claude Sonnet (speed), judge with a different provider or Prometheus 2 (independence).

4. **Few-shot calibration from the test set** — for each judging session, inject 2–3 examples from the test set with known correct verdicts, balanced across agree/disagree. This anchors the judge's scoring distribution.

5. **Ensemble for test set, single judge for bulk** — test set annotation uses a 3-model panel with majority vote (and minority-veto for uncertain flags); bulk/production review uses a single judge for cost reasons, with periodic audits against the panel result to detect drift.

---

### Judge Configuration A — Single LLM Judge (Production / Bulk)

Used in Mode B bulk evaluation and for fast iteration during framework development.

Each criterion is evaluated in a **separate structured call**:

**Call 1 — Excerpt validity**
```
RUBRIC: Excerpt Validity
Score 2 (Valid): The quoted excerpt appears verbatim or near-verbatim in the article.
Score 1 (Partial): The excerpt paraphrases the article text but the substance is present.
Score 0 (Invalid): The excerpt does not appear in the article or substantially misrepresents it.

CALIBRATION EXAMPLE (Valid, Score 2):
Article contains: "...experts warn the policy could devastate rural communities..."
Excerpt quoted: "experts warn the policy could devastate rural communities"
Verdict: 2 — verbatim match

CALIBRATION EXAMPLE (Invalid, Score 0):
Article contains: "the study found mixed results"
Excerpt quoted: "the study confirmed the hypothesis"
Verdict: 0 — contradicts the source

TASK: For the excerpt below, return score (0/1/2) and a one-sentence evidence citation.
```

**Call 2 — Category correctness**
```
RUBRIC: Category Correctness
Score 2 (Correct): The bias category assigned matches the mechanism described in the definition.
Score 1 (Plausible): The category is defensible but another category is equally or more appropriate.
Score 0 (Incorrect): The category does not match the mechanism in the excerpt.

[Inject the named bias definition + the two most common confusions from taxonomy]
```

**Call 3 — Explanation quality**
```
RUBRIC: Explanation Quality
Score 2 (Clear): The explanation identifies the specific distortion, names the mechanism, and is non-circular.
Score 1 (Partial): The explanation describes the excerpt but does not name the mechanism, or is circular.
Score 0 (Poor): The explanation restates the bias name without analysis, or is factually incorrect.
```

**Call 4 — Confidence calibration**
```
RUBRIC: Confidence Calibration
Score 2 (Appropriate): The confidence level matches the strength of the textual evidence.
Score 1 (Slightly off): Confidence is one level too high or low given the evidence.
Score 0 (Miscalibrated): Confidence is clearly wrong (e.g., "high" for an ambiguous excerpt).
```

Each call returns `{"score": int, "evidence": "string", "notes": "string | null"}`. An instance passes judge review if all four criteria score ≥ 1, with at least two scoring 2.

---

### Judge Configuration B — Ensemble Panel (Test Set / Validation)

Used for test set construction and framework version validation. Three models judge independently; results are aggregated.

**Models:** Use three models from different provider/family combinations to maximize error independence. Example: Claude Opus, Gemini Pro, Prometheus 2.

**Aggregation rules:**
- **Majority vote (2/3):** Default for accept/reject on individual instances
- **Minority veto:** If any one model scores 0 on Excerpt Validity, the instance is flagged as uncertain regardless of other scores — a false evidence citation is disqualifying
- **Unanimous required for test set admission:** An instance enters the gold-standard test set only if all three judges score it ≥ 1 on all criteria

**Ensemble output schema:**
```json
{
  "instance_id": "string",
  "judge_scores": {
    "model_a": {"excerpt_validity": 2, "category": 2, "explanation": 1, "confidence": 2},
    "model_b": {"excerpt_validity": 2, "category": 1, "explanation": 2, "confidence": 2},
    "model_c": {"excerpt_validity": 2, "category": 2, "explanation": 2, "confidence": 1}
  },
  "aggregate": {
    "verdict": "accept | uncertain | reject",
    "minority_veto": false,
    "mean_score": 1.83,
    "disagreement_flags": ["category"]
  }
}
```

Instances with `disagreement_flags` on category or explanation are routed to human review regardless of overall verdict.

---

### Judge Configuration C — Hybrid Human / LLM (Recommended for Test Set Bootstrap)

The initial test set cannot be annotated using LLM judge output alone — anchoring the gold standard on LLM judgments would corrupt the benchmark. The bootstrap process is:

1. Human annotator produces initial annotation independently (no LLM output shown)
2. Ensemble panel (Config B) runs independently on the same article
3. Human reviews only instances where panel and human annotation **disagree**
4. Human makes final call on disagreements; rationale recorded in `inter_rater_notes`
5. Instances with unresolvable disagreement (human cannot justify a clear verdict after seeing panel reasoning) are held as "ambiguous" — tracked separately, not used in F1 scoring but useful for calibration analysis

After the initial test set is established, new articles can use Config B + human spot-check (random 20% of agreed instances) rather than full human-first annotation.

**Human interface in the UI:** For each flagged instance, show:
- Original article with excerpt highlighted
- Bias name, category, and definition
- Evaluator's explanation
- Each panel judge's scores and evidence citations
- Simple verdict buttons: **Confirm / Reject / Mark ambiguous** + freetext note

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

## POC Implementation: What to Actually Build First

The full framework above is the north star — it's right, and it will matter once the concept is proven. But for a hobby POC, most of it is premature. Here's the minimum viable eval stack that gives you real signal without over-engineering.

### What to cut for POC

| Full Framework | POC Reality |
|---|---|
| 3-pass Mode A pipeline | 2-pass: category → identify (skip self-verification) |
| Embedding pre-filter (Mode B) | Skip for now — just use Mode A for everything |
| 4 separate judge criterion calls | 1 combined judge call with 2 criteria |
| 3-model ensemble panel | You, reading the output |
| Formal test set with Cohen's kappa | 5–10 articles you've hand-labeled yourself |
| Automated F1 scoring infrastructure | A markdown table you update manually |
| Minority-veto aggregation logic | Not needed |
| Prometheus 2 setup | Use Claude as judge with a different model tier |

### What to keep

These are cheap to implement and provide real value even at POC scale:

1. **Versioned prompts** — store prompts as text files, not hardcoded strings. One `framework_version` field in output. Takes 10 minutes, pays off immediately when you want to compare before/after a prompt change.

2. **Structured JSON output** — the schema is already defined. Getting this right from day one means every future feature (judge, dashboard, export) has clean data to work with.

3. **The author_exhibiting / source_reporting distinction** — this is a real cognitive task that the model needs explicit instruction on. Keep it in the system prompt.

4. **Two-pass pipeline (no verification)** — category first, then biases in that category. This is what actually prevents the zero-accuracy failure at full taxonomy scale. It's two API calls, not three. Not optional.

5. **Human-readable output in the UI** — the point of a POC is to look at real results. Invest in displaying output clearly so you can actually judge whether the detections are good.

### POC Judge: Just You

For a 5–10 article test set, the judge is you reading the output and noting:

- **Right bias, right excerpt** — counts as TP
- **Right category, wrong specific bias** — counts as partial
- **Plausible but wrong** — counts as FP
- **Missed something obvious** — counts as FN

Keep a simple markdown log:

```markdown
## Eval Log — Framework v0.1

### Article: [title/url]
- Confirmed: availability heuristic (excerpt match ✓), framing effect (excerpt match ✓)
- False positive: narrative fallacy — excerpt doesn't support it
- Missed: anchoring in paragraph 3

Overall: 2 TP, 1 FP, 1 FN
```

After 5–10 articles you'll have a real sense of which bias categories the framework handles well and which need taxonomy work. That's enough signal to drive iteration without any scoring infrastructure.

### POC LLM Judge: One Call, Two Criteria

When you want a second opinion beyond your own reading, use a single judge call covering the two criteria that matter most:

```
You are reviewing a cognitive bias detection result. Given the original article and a list of
detected bias instances, assess each instance on two criteria only:

1. EXCERPT VALID: Does the quoted excerpt appear verbatim or near-verbatim in the article? (yes / partial / no)
2. BIAS PLAUSIBLE: Given the definition below, does the excerpt plausibly exhibit this bias? (yes / partial / no)

For each instance return: excerpt_valid, bias_plausible, and one sentence of evidence.
Do not add new detections. Do not assess explanation quality or confidence calibration.

[Inject bias definitions for the detected biases only — not the full taxonomy]
```

Use a different model tier from the evaluator (e.g., evaluate with Sonnet, judge with Opus). This takes one extra API call per article and catches the most common failure modes (hallucinated excerpts, wrong bias category) without the full criterion-separated rubric overhead.

### POC Iteration Trigger

Don't set up automated scoring thresholds. Instead, iterate when:
- You notice the same false positive pattern appearing in 3+ articles → tighten that bias's `identification_criteria`
- A bias you expected to find in an article was consistently missed → expand `linguistic_signals`
- Human and LLM judge disagree on the same bias category repeatedly → revise `common_confusions`

Bump the framework version string when you make a prompt or taxonomy change so you can compare before/after on the same articles.

### POC → Full Framework Migration Path

When the POC is working and you want more rigor, the migration order is:

1. Add Pass 3 self-verification to Mode A (one extra API call, ~14 point F1 gain per research)
2. Formalize the eval log into `eval/test_set/` JSON files (same structure, just persisted)
3. Write `scoring.py` to automate what you're doing manually in the markdown log
4. Add the embedding pre-filter for Mode B (only needed once Phase 2 multi-article features are built)
5. Add the 4-criterion judge calls (only needed once you have enough test articles to calibrate against)
6. Add ensemble panel (only needed if you want to publish results or share the framework)

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

**Hierarchical & Large-Taxonomy Classification**
- [Single-pass Hierarchical Text Classification with LLMs](https://payberah.github.io/files/download/papers/llm_classification.pdf)
- [TELEClass: Taxonomy Enrichment and LLM-Enhanced Hierarchical Text Classification](https://arxiv.org/html/2403.00165v3)
- [SALSA: Single-pass Autoregressive LLM Structured Classification](https://arxiv.org/pdf/2510.22691)
- [Optimizing LLM Annotation through Multi-Agent Orchestration](https://arxiv.org/pdf/2603.13353)

**Context Window & Prompt Length**
- [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://arxiv.org/html/2510.05381v1)
- [Why Does the Effective Context Length of LLMs Fall Short?](https://arxiv.org/pdf/2410.18745)

**LLM-as-Judge: Biases & Failure Modes**
- [A Systematic Study of Position Bias in LLM-as-a-Judge](https://aclanthology.org/2025.ijcnlp-long.18.pdf)
- [Self-Preference Bias in LLM-as-a-Judge](https://www.researchgate.net/publication/385353198_Self-Preference_Bias_in_LLM-as-a-Judge)
- [The Comparative Trap: Pairwise Comparisons Amplify Biased Preferences](https://arxiv.org/pdf/2406.12319)
- [LLMs-as-Judges: A Comprehensive Survey](https://arxiv.org/html/2412.05579v2)

**LLM-as-Judge: Rubrics & Calibration**
- [RULERS: Locked Rubrics and Evidence-Anchored Scoring](https://arxiv.org/html/2601.08654v1)
- [AutoRubric: Unifying Rubric-based LLM Evaluation](https://arxiv.org/html/2603.00077v2)
- [Prometheus 2: Open Source LLM Specialized in Evaluation (EMNLP 2024)](https://aclanthology.org/2024.emnlp-main.248/)

**Ensemble & Panel Judging**
- [Auditing Multi-Agent LLM Reasoning Trees Outperforms Majority Vote and LLM-as-Judge](https://arxiv.org/html/2602.09341v1)
- [Human-Centered Design Recommendations for LLM-as-a-Judge](https://aclanthology.org/2024.hucllm-1.2.pdf)
