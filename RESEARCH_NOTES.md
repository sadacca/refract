# Refract — Research Notes

Compiled findings from research sessions conducted during requirements and evaluation framework development. Organized by topic. Links verified at time of research.

---

## Session 1: Context Window Management for Large-Taxonomy LLM Classification

**Research question:** What are the most effective strategies for managing context window efficiency in LLM-based multi-class classification when the taxonomy is large (100–200 classes)?

### Key Findings

**Single-pass full-taxonomy injection fails at scale**
- On LongICLBench (174 classes), most LLMs achieved **zero accuracy** under single-pass full-taxonomy prompting — complete task failure, not just degradation
- Performance degrades measurably when prompts exceed 70–80% of the context window
- GPT-4 shows ~15% accuracy degradation from 4K → 128K tokens
- Beyond a minimal effective context size, adding more class definitions yields marginal or negative returns on classification performance

**Hierarchical / cascaded approaches work**
- Breaking classification into a coarse-to-fine hierarchy (category first, then specific classes) is well-established and reduces per-call label space to a manageable subset
- Three algorithmic variants studied: hierarchical, single-path, and path-traversal — all outperform flat single-pass approaches on large taxonomies
- Modified single-pass prompts (where only a filtered subset of classes is injected) mitigate inefficiencies without requiring multi-call pipelines, at some recall cost

**Multi-pass verification meaningfully improves reliability**
- Multi-pass approaches with a self-verification step improve F1 from ~0.30 → ~0.44–0.46 vs. single-pass alone (~14 point gain)
- Self-verification is most valuable for catching conflation between similar classes and instances where the model's confidence is miscalibrated

**SALSA (Single-pass Autoregressive LLM Structured Classification)**
- Maps each class label to a distinct output token; projects logits only onto class-token subspace
- Enables efficient single-forward-pass classification with fine-tuning
- Not directly applicable to a zero-shot/few-shot setup without fine-tuning, but relevant if Refract ever moves toward a fine-tuned evaluator model

### Papers
- [Single-pass Hierarchical Text Classification with LLMs](https://payberah.github.io/files/download/papers/llm_classification.pdf) — three algorithmic variants, efficiency vs. accuracy tradeoffs
- [TELEClass: Taxonomy Enrichment and LLM-Enhanced Hierarchical Text Classification](https://arxiv.org/html/2403.00165v3) — minimal supervision hierarchical classification
- [Leveraging Taxonomy and LLMs for Improved Multimodal Hierarchical Classification](https://arxiv.org/html/2501.06827v1) — multimodal extension, 2025
- [SALSA: Single-pass Autoregressive LLM Structured Classification](https://arxiv.org/pdf/2510.22691) — efficient single-pass via class-token mapping
- [Optimizing LLM Annotation through Multi-Agent Orchestration](https://arxiv.org/pdf/2603.13353) — multi-agent orchestration for classroom discourse annotation; most relevant section is multi-pass verification improving F1
- [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://arxiv.org/html/2510.05381v1) — even with perfect retrieval, long context degrades performance
- [Why Does the Effective Context Length of LLMs Fall Short?](https://arxiv.org/pdf/2410.18745) — theoretical and empirical analysis of effective context limits
- [Large Language Models Do Multi-Label Classification Differently](https://arxiv.org/pdf/2505.17510) — softmax normalization incompatibility with multi-label settings; important for understanding why LLMs undercount co-occurring biases

### Design Decisions Informed
- Ruled out single-pass full-taxonomy injection → two-mode architecture (hierarchical cascade for deep; embedding pre-filter for bulk)
- Mode A (deep): 3-pass pipeline — category classifier → bias identification → self-verification
- Mode B (bulk): embedding similarity pre-filter → single call with top-25 biases

---

## Session 2: LLM-as-Judge Design for Specialized Classification Tasks

**Research question:** What are the right evaluation considerations for LLM-as-judge in a specialized domain (cognitive bias detection), and what configurations are available?

### Key Findings

**The four failure modes of LLM judges**

1. **Position bias** — judges systematically prefer candidates presented first or last; swapping order in pairwise tasks shifts accuracy by >10%. Mitigated by: randomizing order, running both orderings and averaging, or using pointwise (not pairwise) evaluation
2. **Verbosity bias** — longer, more formal outputs score higher regardless of correctness; artifact of RLHF pretraining. Mitigated by: criterion-separated rubrics that require specific evidence, not overall quality impressions
3. **Self-enhancement bias** — an LLM judge scores its own outputs higher than equally good outputs from other models; bias strength correlates linearly with self-recognition capability (NeurIPS 2024). Mitigated by: always use a different model family as judge than as evaluator
4. **Criterion conflation / halo effect** — evaluating multiple criteria in one call causes scores on one criterion to bleed into others. Mitigated by: one criterion per call, or at minimum criterion-separated sections with independent evidence requirements

**Rubric design matters more than model choice**
- "RULERS" (2025): locked rubrics with evidence-anchored scoring produce significantly more robust evaluations than vague quality prompts
- Prometheus (ICLR 2024) and Prometheus 2 (EMNLP 2024): open-source models trained specifically for rubric-conditioned evaluation; Prometheus 2 achieves Pearson correlation of 0.897 with human evaluators; outperforms GPT-4 on structured evaluation tasks in some benchmarks
- AutoRubric (2025): frames rubric construction itself as a generation problem; useful if Refract expands to new text types with different bias profiles

**Pointwise vs. pairwise**
- Pointwise (score each instance against a rubric) is more appropriate for Refract — we're asking "is this instance correctly detected" not "which of these two detections is better"
- Pairwise amplifies biases and is more adversarially vulnerable ("The Comparative Trap", 2024)
- Pass/fail is a valid third option for binary verification tasks (excerpt validity in particular)

**Ensemble panels improve reliability but only if models are error-independent**
- Multi-model panels outperform single judges by 8–15% reliability; gain comes from error independence
- Majority vote captures most of the ensemble gain; minority-veto (any dissent triggers "uncertain") increases true negative rate further
- Gain is limited when models share training data or RLHF approaches — correlated errors don't cancel. Must use genuinely different model families for independence
- Concatenating independent evaluations focused on separate criteria improves error detection by up to 62% vs. single-evaluator

**The ceiling in specialized domains**
- On general tasks: LLM judges agree with humans >80% of the time
- In specialized expert domains (dietetics, mental health, etc.): agreement drops to 60–70%
- Cognitive bias detection is a specialized domain → LLM-only judgment is a floor, not a ceiling; human oversight is required for test set construction

**Few-shot calibration significantly improves judge consistency**
- Providing 3–5 scored examples with balanced verdicts (not all agrees or all rejects) anchors the judge's score distribution
- Without calibration examples, judge behavior is dominated by its implicit base-rate prior
- Regression-based bias correction calibrated on small human-annotated sets can halve residual judge error

### Papers
- [A Systematic Study of Position Bias in LLM-as-a-Judge](https://aclanthology.org/2025.ijcnlp-long.18.pdf) — quantifies position bias magnitude across model families
- [Self-Preference Bias in LLM-as-a-Judge](https://www.researchgate.net/publication/385353198_Self-Preference_Bias_in_LLM-as-a-Judge) — NeurIPS 2024; linear correlation between self-recognition and self-preference
- [The Comparative Trap: Pairwise Comparisons Amplify Biased Preferences](https://arxiv.org/pdf/2406.12319) — why pairwise is worse than pointwise for specialized tasks
- [RULERS: Locked Rubrics and Evidence-Anchored Scoring](https://arxiv.org/html/2601.08654v1) — rubric locking and evidence anchoring for robust evaluation
- [AutoRubric: Unifying Rubric-based LLM Evaluation](https://arxiv.org/html/2603.00077v2) — automated rubric generation
- [Prometheus: Inducing Fine-Grained Evaluation Capability in LLMs](https://arxiv.org/pdf/2310.08491) — ICLR 2024; rubric-conditioned open evaluator
- [Prometheus 2: Open Source LLM Specialized in Evaluation](https://aclanthology.org/2024.emnlp-main.248/) — EMNLP 2024; Pearson 0.897 with humans; outperforms GPT-4 on structured eval
- [LLMs-as-Judges: A Comprehensive Survey](https://arxiv.org/html/2412.05579v2) — comprehensive survey of paradigms, biases, and mitigation strategies
- [Auditing Multi-Agent LLM Reasoning Trees Outperforms Majority Vote and LLM-as-Judge](https://arxiv.org/html/2602.09341v1) — ensemble vs. single judge accuracy; 8–15% reliability gain
- [Human-Centered Design Recommendations for LLM-as-a-Judge](https://aclanthology.org/2024.hucllm-1.2.pdf) — human factors in judge design
- [LLM-as-a-Judge: Automated Evaluation of Search Query Parsing](https://pmc.ncbi.nlm.nih.gov/articles/PMC12319771/) — ~90% agreement with humans in structured classification; practical reference

### Design Decisions Informed
- Pointwise (not pairwise) evaluation throughout
- One criterion per judge call to prevent halo effects
- Locked rubric with evidence anchoring required for every score
- Cross-model judging enforced (evaluator and judge always different families)
- Few-shot calibration from test set included in every judge call
- Three configurations defined: single judge (production), ensemble panel (test set), hybrid human/LLM (bootstrap)

---

## Session 3: Related Work — Cognitive Biases in LLMs (Malberg et al.)

**Source:** https://github.com/simonmalberg/cognitive-biases-in-llms

**Research question:** What can Refract learn from this existing systematic evaluation of cognitive biases in LLMs?

### What They Built

A research benchmark evaluating whether LLMs *exhibit* cognitive biases in their own decision-making — 30 biases × 20 LLMs × 200 scenarios = 30,000 test instances. Published on HuggingFace. Core methodology:

- **Control/treatment pairs:** Each bias is tested via matched scenario pairs. The control presents a neutral decision context; the treatment introduces the bias-inducing condition. The delta between control and treatment response is the bias signal.
- **XML-configured test templates:** Each bias has a `config.xml` defining the scenario template, custom value sampling, and response options, plus a `test.py` with a `TestGenerator` and `Metric` class.
- **Scoring:** `𝔅(â₁, â₂) = (â₁ - â₂) / max(â₁, â₂) ∈ [-1, 1]` — normalized ratio of treatment vs. control response difference. Produces a quantitative bias magnitude score per model per bias.
- **Scenario diversity:** 200 scenarios grounded in GICS industry classification (25 industry groups × 8 managerial roles) to avoid domain-specific confounds.
- **Reproducibility:** MD5-hashed scenario seeds for deterministic instance generation.

### 30 Biases Tested

Anchoring, Anthropomorphism, Availability Heuristic, Bandwagon Effect, Confirmation Bias, Conservatism, Disposition Effect, Endowment Effect, Escalation of Commitment, Framing Effect, Fundamental Attribution Error, Halo Effect, Hindsight Bias, Hyperbolic Discounting, Illusion of Control, In-Group Bias, Information Bias, Loss Aversion, Mental Accounting, Negativity Bias, Not Invented Here, Optimism Bias, Planning Fallacy, Reactance, Risk Compensation, Self-Serving Bias, Social Desirability Bias, Status Quo Bias, Stereotyping, Survivorship Bias.

Key finding: evidence of all 30 biases found in at least some of the 20 models tested.

### How This Differs from Refract

| Dimension | Malberg et al. | Refract |
|---|---|---|
| **What is being evaluated** | Whether LLMs *exhibit* bias in their decisions | Whether *written text* exhibits cognitive bias patterns |
| **Subject** | The LLM itself (does Gemini show anchoring?) | The article/text (does this article use anchoring?) |
| **Methodology** | Control/treatment decision scenarios | Pattern-matching against precomputed reference examples |
| **Bias signal** | Delta between control and treatment responses | Verbatim excerpt identification + explanation |
| **Output** | Quantitative bias magnitude score per model | Structured inventory: excerpts, locations, explanations |
| **Purpose** | Research benchmark — how biased are models? | Operational tool — what biases are in this text? |
| **Scale** | 30,000 test instances across 20 models | Per-article evaluation of natural text |
| **Bias taxonomy** | 30 decision-making biases | ~80-100 text-detectable biases from full codex |
| **Context** | Controlled synthetic scenarios | Real journalism, uncontrolled |

### Insights to Take from Malberg et al.

**1. Control/treatment pairing as a reference example strategy**

Their most valuable methodological contribution for Refract is the **control/treatment structure**. Each test explicitly shows: *here is text without the bias (control), here is text with the bias (treatment)*. This is a rigorous operationalization of "what the bias looks like."

Refract's precomputed reference examples should adopt this structure explicitly:
- `positive_examples` in the taxonomy = treatment-equivalent: text that exhibits the bias
- `near_miss_examples` = control-equivalent: similar text without the bias
- The contrast should be as structurally parallel as possible (same topic, same length, same voice) so the model can isolate the bias signal rather than confounding it with domain or style

**2. The 30-bias list is a high-confidence starting subset**

Their list represents 30 biases with enough research grounding to operationalize as controlled experiments — each bias has a clear mechanism that produces measurable behavioral change. This is a natural priority tier for Refract's hand-labeling queue: these 30 are the ones most likely to have well-defined `identification_criteria` and the clearest reference examples.

Cross-reference: 23 of their 30 biases map directly to Refract's 10 categories. 7 (Disposition Effect, Mental Accounting, Hyperbolic Discounting, Risk Compensation, Not Invented Here, Conservatism, Reactance) are primarily decision-making biases that may be harder to detect in journalism text without explicit behavioral framing.

**3. Scenario diversity as a near-miss generation strategy**

Their 200-scenario approach (25 industries × 8 roles) exists to avoid domain confounds. For Refract, the analogous technique is ensuring `positive_examples` span multiple topic domains (politics, economics, crime, science, sport) — the same bias should be detectable regardless of whether the article is about a politician or a pharmaceutical company. Their GICS-based diversification is worth borrowing as a domain coverage checklist.

**4. Quantitative bias magnitude scoring**

Their `𝔅` formula produces a continuous score, not binary present/absent. Refract uses binary detection + graduated severity. Worth noting: their scoring works because control/treatment delta is measurable. In natural text without a control, continuous scoring is harder to ground. Refract's approach (binary detected + high/medium/low severity) is correct for the use case, but the Malberg et al. scoring could inform how severity levels are defined — e.g., "high" severity = would score >0.7 on their scale if tested as a decision scenario.

**5. The 30,000-instance dataset on HuggingFace**

This is directly usable as a validation resource. If Refract detects anchoring in an article, the Malberg et al. dataset provides independently verified examples of what anchoring looks like in a controlled decision context — useful for calibrating whether Refract's reference examples are in the right neighborhood. Worth downloading and cross-referencing when building reference examples for the overlapping 23 biases.

**6. XML template structure for reference example storage**

Their `config.xml` + `test.py` per-bias structure is clean and extensible. Refract uses JSON taxonomy entries — similar spirit. Worth reviewing their XML schema as a cross-check on what fields matter for a rigorous bias operationalization.

### What Malberg et al. Does Not Address (Refract's Distinct Contribution)

- Detection in natural, uncontrolled text (their scenarios are synthetic)
- Multi-label detection (one article, many simultaneous bias patterns)
- Text position and excerpt identification (they score responses, not locate bias in source text)
- Reframing (no equivalent — they measure, don't remediate)
- Journalism-specific bias patterns (their scenarios are managerial/decision-making)
- The author-exhibiting vs. source-reporting distinction

### Recommended Actions

1. **Download HuggingFace dataset** and extract the 23 overlapping biases. Use their control/treatment pairs as candidate `near_miss` / `positive` examples for the precompute phase — they're already human-designed to be structurally parallel.
2. **Adopt the control/treatment framing** in Refract's reference example schema — rename or annotate `positive` and `near_miss` to make the structural parallel explicit.
3. **Use their 30-bias list as the priority queue** for hand-labeling in Phase 1. These are the best-operationalized biases in the literature.
4. **Cross-reference their bias magnitude scores** when defining Refract's severity levels — "high severity" in Refract should correspond to biases that produce large `𝔅` scores in their framework.
5. **Note the 7 decision-biases** (Disposition Effect, Mental Accounting, etc.) that may not manifest detectably in journalism text — consider marking these `provisional` in the taxonomy with a note about detectability limitations.

---

## Open Research Questions (for future sessions)

- **Embedding models for pre-filtering (Mode B):** Which embedding models perform best for semantic similarity between bias definitions and news article text? Sentence-transformers? OpenAI embeddings? Domain-specific?
- **Fine-tuned evaluator feasibility:** At what scale does fine-tuning a Prometheus-style evaluator on Refract's test set annotations become worthwhile vs. continued prompt engineering?
- **Taxonomy coverage validation:** Is there existing NLP work on automatically checking whether a taxonomy covers a text corpus (i.e., are there biases present in the wild that the taxonomy doesn't capture)?
- **Reframe quality evaluation:** Limited research found on automated evaluation of debiased text quality. What metrics exist beyond factual preservation and readability?
- **Malberg et al. dataset integration:** Can their 30,000 control/treatment pairs be adapted as reference examples for the Refract taxonomy, or do they require significant reworking for journalism context?
