# Refract — Research Notes

Compiled findings from two research sessions conducted during requirements and evaluation framework development. Organized by topic. Links verified at time of research.

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

## Open Research Questions (for future sessions)

- **Embedding models for pre-filtering (Mode B):** Which embedding models perform best for semantic similarity between bias definitions and news article text? Sentence-transformers? OpenAI embeddings? Domain-specific?
- **Fine-tuned evaluator feasibility:** At what scale does fine-tuning a Prometheus-style evaluator on Refract's test set annotations become worthwhile vs. continued prompt engineering?
- **Taxonomy coverage validation:** Is there existing NLP work on automatically checking whether a taxonomy covers a text corpus (i.e., are there biases present in the wild that the taxonomy doesn't capture)?
- **Reframe quality evaluation:** Limited research found on automated evaluation of debiased text quality. What metrics exist beyond factual preservation and readability?
