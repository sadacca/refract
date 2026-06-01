# Refract — Research Reference Corner

Categorized links to papers and resources grounding the evaluation framework,
bias taxonomy, and pipeline design decisions. Updated 2026-06-01.

---

## 1. LLM-as-Judge: Bias Taxonomy & Mitigation

The most important cluster for Refract's Pass 4 judge design.

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge](https://arxiv.org/abs/2410.02736) | 2024 | 12-bias taxonomy via CALM automated framework | Canonical bias taxonomy for judge design |
| [Large Language Models are not Fair Evaluators](https://arxiv.org/abs/2305.17926) | ACL 2024 | Reordering flips 66/80 rankings; proposes swap augmentation + multiple evidence calibration | Basis for TODO 6.2 (swap augmentation) |
| [Judging the Judges: A Systematic Study of Position Bias](https://arxiv.org/abs/2406.07791) | 2024 | 15 judges, 150k instances; >10% accuracy shift from order changes | Quantifies position bias severity |
| [LLM Evaluators Recognize and Favor Their Own Generations](https://arxiv.org/abs/2404.13076) | NeurIPS 2024 Oral | GPT-4 73.5% self-recognition; linear correlation between self-recognition and bias strength | Basis for TODO 6.1 (cross-family judge) |
| [Breaking the Mirror: Activation-Based Mitigation of Self-Preference](https://arxiv.org/abs/2509.03647) | NeurIPS 2025 | CAA steering vectors reduce unjustified self-preference by up to 97% | Advanced self-preference mitigation |
| [Judging the Judges: Systematic Evaluation of Bias Mitigation Strategies](https://arxiv.org/abs/2604.23178) | Apr 2026 | Compares 9 debiasing strategies; no single strategy sufficient; swap+rubric+cross-family is most robust | Synthesis of all judge bias mitigations |
| [CalibraEval: Calibrating Prediction Distribution to Mitigate Selection Bias](https://arxiv.org/abs/2410.15393) | ACL 2025 | Kappa 31%→39%; ICC 71%→83% on Llama-3-8B via distribution calibration | Quantified swap augmentation improvement |
| [Contrastive Decoding Mitigates Score Range Bias](https://arxiv.org/abs/2510.18196) | 2025 | Score range artifacts cancelled by contrastive decoding | Score normalization technique |
| [Making Bias Non-Predictive: RL-Trained Robust LLM Judges](https://arxiv.org/abs/2602.01528) | Feb 2026 | RL for bandwagon bias generalizes to authority and distraction bias | Transfer learning for bias robustness |
| [The Silent Judge: Unacknowledged Shortcut Bias](https://arxiv.org/abs/2509.26072) | 2025 | Documents shortcut biases judge doesn't flag in its own reasoning | Hidden judge bias patterns |
| [Self-Preference Bias in LLM-as-a-Judge](https://arxiv.org/html/2410.21819v2) | 2024 | Authorship obfuscation reduces self-preference | Practical mitigation without model change |
| [Evaluating Scoring Bias in LLM-as-a-Judge](https://arxiv.org/abs/2506.22316) | 2025 | Reference answer quality inflates all scores; rubric order matters | Reference answer contamination |

---

## 2. LLM-as-Judge: Calibration Methods

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment](https://arxiv.org/abs/2303.16634) | EMNLP 2023 | CoT steps + probability-weighted scoring; Spearman 0.514 on summarization | Basis for TODO 6.5 (logprob weighting); schema field order requirement |
| [AutoCalibrate: Calibrating LLM-Based Evaluator](https://arxiv.org/abs/2309.13308) | LREC-COLING 2024 | Criteria self-refinement against human labels; >20% Spearman gain over GPT-Score | Automated rubric calibration |
| [Calibrating Language Models with Adaptive Temperature Scaling](https://arxiv.org/abs/2409.19817) | EMNLP 2024 | Token-level adaptive temperature; 10–50% ECE improvement; orthogonal to accuracy | Post-hoc calibration for RLHF-trained judges |
| [Calibrating LLM Judges: Linear Probes for Uncertainty Estimation](https://arxiv.org/abs/2512.22245) | Dec 2025 | Linear probes on internal activations for AUROC-calibrated uncertainty | Uncertainty without logit access |
| [Calibrating Verbalized Probabilities for LLMs](https://arxiv.org/abs/2410.06707) | Oct 2024 | Invert-softmax trick for verbalized probability calibration | When logprobs unavailable |
| [Balancing Classification and Calibration via Calibration-Aware RL](https://arxiv.org/abs/2601.13284) | Jan 2026 | Joint reward: accuracy + ECE; resolves over-confident misclassification | Fine-tuning judges for calibration |
| [LLM-Rubric: A Multidimensional, Calibrated Approach](https://arxiv.org/abs/2501.00274) | Jan 2025 | Per-dimension multiple-choice rubric + neural calibration; RMS error < 0.5 | Full rubric design reference |
| [RULERS: Locked Rubrics and Evidence-Anchored Scoring](https://arxiv.org/abs/2601.08654) | 2025 | Locked rubrics with evidence anchoring outperform vague quality prompts | Rubric design principle for Pass 4 |

---

## 3. Multi-Judge Ensembles & Panel Design

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [ChatEval: Towards Better LLM-based Evaluators through Multi-Agent Debate](https://arxiv.org/abs/2308.07201) | ICLR 2024 | Multi-agent debate; Kendall Tau 0.52→0.57 vs. single GPT-4 | Ensemble design patterns |
| [Trust or Escalate: LLM Judges with Provable Guarantees](https://arxiv.org/abs/2407.18370) | ICLR 2025 Oral | Conformal prediction cascade; >80% human agreement guaranteed at 79.1% coverage | Cascade architecture for cost vs. quality |
| [SE-Jury: LLM-as-Ensemble-Judge for Software Engineering](https://arxiv.org/abs/2505.20854) | ASE 2025 | Dynamic per-instance judge selection; 34–113% Spearman improvement | Dynamic ensemble selection |
| [Who Judges the Judge? LLM Jury-on-Demand](https://arxiv.org/abs/2512.01786) | Dec 2024 | Instance-level reliability predictors for weighted jury composition | Learned reliability-based weighting |
| [Who can we trust? LLM-as-a-jury for Comparative Assessment](https://arxiv.org/abs/2602.16610) | Feb 2026 | Bradley-Terry model with judge inconsistency parameters | Pairwise jury design |
| [Auditing Multi-Agent LLM Reasoning Trees Outperforms Majority Vote](https://arxiv.org/abs/2602.09341) | 2026 | Reasoning tree auditing > majority vote and single LLM-judge | Advanced ensemble aggregation |
| [Prometheus 2: Open Source LLM Specialized in Evaluation](https://aclanthology.org/2024.emnlp-main.248/) | EMNLP 2024 | Open-source rubric-conditioned evaluator; higher human correlation than GPT-4 on structured tasks | Cost-effective judge alternative |
| [Human-Centered Design Recommendations for LLM-as-a-Judge](https://aclanthology.org/2024.hucllm-1.2.pdf) | 2024 | Human-in-loop design patterns for high-stakes evaluation | Test set annotation design |

---

## 4. LLM as Multi-Class Classifier

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [A Survey on LLM-as-a-Judge](https://arxiv.org/abs/2411.15594) | Nov 2024 | Comprehensive survey; few-shot CoT dramatically reduces inter-judge variance | Framework overview |
| [Token-Level Marginalization for Multi-Label LLM Classifiers](https://arxiv.org/abs/2511.22312) | Nov 2025 | Marginal probability via constrained DFS; highest AUROC for confidence estimation | Confidence scoring for classification |
| [TELEClass: Taxonomy Enrichment and LLM-Enhanced Hierarchical Text Classification](https://arxiv.org/abs/2403.00165) | 2024 | Hundreds of classes in one prompt causes collapse; coarse-to-fine routing is the fix | Basis for Refract's multi-pass architecture |
| [Evaluating LLMs for Demographic-Targeted Social Bias Detection](https://arxiv.org/abs/2510.04641) | Oct 2025 | Policy-based prompting + few-shot ICL; macro-F1 per demographic axis | Bias detection evaluation framework |
| [Fine-Grained Bias Detection in LLM](https://arxiv.org/abs/2503.06054) | Mar 2025 | Contextual LLM + attention interpretability + counterfactual augmentation | Subtle bias detection techniques |
| [Debiasing Fine-Grained Classification with Bias-Aware PEFT](https://aclanthology.org/2025.acl-long.717/) | ACL 2025 | Label-frequency bias accumulates in deeper layers; bias-aware PEFT improves rare-class recall | Rare bias category recall |
| [AutoRubric: Unifying Rubric-based LLM Evaluation](https://arxiv.org/abs/2603.00077) | Mar 2026 | Unified rubric framework for domain-grounded, reference-anchored evaluation | Rubric standardization |
| [RubricRAG: Interpretable LLM Evaluation via Domain Knowledge Retrieval](https://arxiv.org/abs/2603.20882) | Mar 2026 | RAG-augmented rubric generation; zero-shot rubric quality is poor | Domain-specific rubric design |

---

## 5. FActScore & Factual Evaluation

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [FActScore: Fine-grained Atomic Evaluation of Factual Precision](https://arxiv.org/abs/2305.14251) | EMNLP 2023 | Atomic fact decomposition + retrieval + verification; ChatGPT 58% factual precision | Atomic claim verification methodology |
| [An Analysis of Multilingual FActScore](https://aclanthology.org/2024.emnlp-main.247/) | EMNLP 2024 | All four pipeline components degrade in non-English; English Wikipedia most reliable source | Multilingual factual evaluation |
| [Face the Facts! RAG-based Pipelines for Professional Fact-Checking](https://arxiv.org/abs/2412.15189) | Dec 2024 | RAG + domain-specific fine-tuning for journalism-grade factual verification | Journalism factual verification |
| [Gaming the Judge: Unfaithful CoT Can Undermine Agent Evaluation](https://arxiv.org/abs/2601.14691) | Jan 2026 | Adversarial CoT rewrites inflate judge false-positive rates by up to 90% | CoT verification vulnerability; verify claims against evidence not just reasoning |

---

## 6. G-Eval, CoT Scoring & Chain-of-Thought Evaluation

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment](https://arxiv.org/abs/2303.16634) | EMNLP 2023 | Auto-generated CoT steps + probability re-weighting; Spearman 0.514–0.588 | Primary reference for Pass 4 design |
| [J1: Incentivizing Thinking in LLM-as-a-Judge via RL](https://arxiv.org/abs/2505.10320) | Meta AI, 2025 | GRPO-trained thinking judges; J1-Qwen-32B beats o1-mini and 671B DeepSeek-R1 | RL-trained judge state of the art |
| [Length-Controlled AlpacaEval: A Simple Way to Debias Automatic Evaluators](https://arxiv.org/abs/2404.04475) | 2024 | Regression to remove length effect; Spearman 0.98 with Chatbot Arena | Verbosity bias debiasing; benchmark design |
| [Applying LLMs and Chain-of-Thought for Automatic Scoring](https://www.sciencedirect.com/article/pii/S2666920X24000146) | 2024 | CoT scoring in educational contexts; structured rubric integration | CoT application patterns |
| [PEARL: A Rubric-Driven Multi-Metric Framework for LLM Evaluation](https://www.mdpi.com/2078-2489/16/11/926) | 2025 | Multi-metric rubric framework across NLP sub-tasks | Rubric-driven evaluation patterns |

---

## 7. Hierarchical & Large-Taxonomy Classification

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [TELEClass: Taxonomy Enrichment and LLM-Enhanced Hierarchical Classification](https://arxiv.org/abs/2403.00165) | 2024 | Coarse-to-fine routing essential for large taxonomies; flat single-prompt fails at scale | Core architecture justification for multi-pass pipeline |
| [Single-pass Hierarchical Text Classification with LLMs](https://payberah.github.io/files/download/papers/llm_classification.pdf) | 2024 | Single-pass limits; annotation at scale | Baseline comparison |
| [SALSA: Single-pass Autoregressive LLM Structured Classification](https://arxiv.org/abs/2510.22691) | 2024 | Autoregressive structured output for classification | Alternative architecture |
| [Optimizing LLM Annotation through Multi-Agent Orchestration](https://arxiv.org/abs/2603.13353) | 2026 | Multi-agent annotation pipelines | Multi-agent annotation patterns |
| [LongICLBench: LLM Performance Under Long In-Context Learning](https://arxiv.org/abs/2404.02060) | 2024 | Zero accuracy for most LLMs on 174-class single-prompt benchmarks | Quantifies taxonomy scale failure |

---

## 8. Token Efficiency: Prompt Compression

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [LLMLingua: Innovating LLM Efficiency with Prompt Compression](https://arxiv.org/abs/2310.05736) | EMNLP 2023 | Up to 20x compression; <1.5 point loss at 20x; 3x–9x practical working range | Primary compression reference; TODO 6.9 |
| [LLMLingua-2: Data Distillation for Efficient Task-Agnostic Prompt Compression](https://arxiv.org/abs/2403.12968) | ACL 2024 | GPT-4 distilled BERT classifier; 3x–6x faster than LLMLingua-1; pip install llmlingua | Implementation reference for TODO 6.9 |
| [LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios](https://arxiv.org/abs/2310.06839) | 2024 | 4x input reduction + 21.4% RAG accuracy gain via chunk reordering | RAG-specific compression; fixes lost-in-middle |
| [Prompt Compression for Large Language Models: A Survey](https://aclanthology.org/2025.naacl-long.368.pdf) | NAACL 2025 | Comprehensive survey of prompt compression techniques | Survey reference |
| [CompactPrompt: A Unified Pipeline for Prompt and Data Compression](https://arxiv.org/abs/2510.18043) | 2024 | Unified compression pipeline | Alternative compression approaches |
| [Efficient Prompt Compression with Evaluator Heads](https://openreview.net/forum?id=yOs12gdsaL) | NeurIPS 2025 Spotlight | Attention-head-based compression | Hardware-aware compression |
| [When Less is More: The LLM Scaling Paradox in Context Compression](https://arxiv.org/abs/2602.09789) | 2026 | Over-compression beyond task-relevant content degrades performance | Compression ceiling and risk |
| [DAST: Dynamic Allocation of Soft Tokens for Context-Aware Compression](https://arxiv.org/abs/2502.11493) | 2025 | Soft token dynamic allocation | Soft token compression |
| [Microsoft LLMLingua GitHub](https://github.com/microsoft/LLMLingua) | — | Reference implementation: pip install llmlingua | Installation and usage |

---

## 9. Token Efficiency: KV Cache & Prefix Reuse

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [RelayCaching: Accelerating LLM Collaboration via Decoding KV Cache Reuse](https://arxiv.org/abs/2603.13289) | 2026 | >80% KV cache reuse rate; 4.7x TTFT reduction in pipeline | Decoding-phase KV pass-through |
| [LMCache: An Efficient KV Cache Layer for Enterprise-Scale LLM Inference](https://arxiv.org/abs/2510.09665) | 2024 | Persistent KV cache on CPU/disk; drop-in vLLM layer | Production KV caching |
| [SemShareKV: Efficient KV Cache Sharing for Semantically Similar Prompts](https://arxiv.org/abs/2509.24832) | 2025 | LSH-based semantic matching for cache sharing beyond exact prefix | Semantic prefix sharing |
| [Towards More Economical Context-Augmented Generation by Reusing KV Cache](https://arxiv.org/abs/2503.14647) | 2025 | KV reuse strategies for RAG | RAG-specific KV reuse |
| [Prompt Caching Infrastructure Guide 2025](https://introl.com/blog/prompt-caching-infrastructure-llm-cost-latency-reduction-guide-2025) | 2025 | Anthropic 90% cost reduction / 85% latency; OpenAI 50% auto; 1,024 token minimum | Provider-level caching reference |
| [Prompt Caching: OpenAI, Anthropic, and Google](https://www.prompthub.us/blog/prompt-caching-with-openai-anthropic-and-google-models) | 2025 | Cross-provider caching comparison and implementation | Implementation guide for TODO 6.8 |

---

## 10. Token Efficiency: Structured Outputs & Constrained Decoding

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [Generating Structured Outputs from LLMs: Benchmark and Studies](https://arxiv.org/abs/2501.10868) | 2025 | Comprehensive benchmark of structured output methods | Reference for TODO 6.6 |
| [Pre3: Deterministic Pushdown Automata for Faster Structured LLM Generation](https://arxiv.org/abs/2506.03887) | 2026 | 40% time-per-output-token; 36% throughput increase with constrained decoding | Performance numbers for TODO 6.6 |
| [Token Efficiency with Structured Output from Language Models](https://medium.com/data-science-at-microsoft/token-efficiency-with-structured-output-from-language-models-be2e51d3d9d5) | 2024 | YAML uses fewer tokens than JSON for equivalent data; function calling more efficient | Format selection guidance |
| [Structured Outputs in vLLM](https://developer.hpe.com/blog/using-structured-outputs-in-vllm/) | 2024 | outlines library for guided decoding in vLLM | Implementation reference |
| [StructLM: Compact Schema Notation](https://github.com/nadeesha/structlm) | — | Token-efficient alternative to JSON Schema in prompts | Schema notation alternative |

---

## 11. Bias Detection in Journalism & NLP

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [Evaluating LLMs for Demographic-Targeted Social Bias Detection](https://arxiv.org/abs/2510.04641) | Oct 2025 | Policy-based prompting + few-shot ICL; 9-axis demographic taxonomy; macro-F1 per axis | Multi-axis bias taxonomy evaluation design |
| [Fine-Grained Bias Detection in LLM](https://arxiv.org/abs/2503.06054) | Mar 2025 | Contextual LLM + attention interpretability + counterfactual augmentation for subtle bias | Subtle bias detection techniques |
| [Face the Facts! RAG-based Pipelines for Professional Fact-Checking](https://arxiv.org/abs/2412.15189) | Dec 2024 | RAG + domain fine-tuning for journalism-grade verification | Journalism fact-checking pipeline |
| [Debiasing Fine-Grained Classification with Bias-Aware PEFT](https://aclanthology.org/2025.acl-long.717/) | ACL 2025 | Label-frequency bias in deeper layers; PEFT with label balance constraints for rare classes | Rare bias category precision |
| [LLM-Rubric: A Multidimensional, Calibrated Approach](https://arxiv.org/abs/2501.00274) | Jan 2025 | Frames large-scale document review (journalism, legal) as shared challenge | Journalism evaluation framing |
| [HealthBench: OpenAI Physician-Authored Rubrics](https://openai.com/index/healthbench/) | 2025 | 260+ physicians wrote 48,562 unique instance-specific criteria; gold standard for domain evaluation | Expert-authored rubric benchmark |

---

## 12. Context Window & Prompt Length

| Paper | Year | Key Finding | Relevance |
|---|---|---|---|
| [Context Length Alone Hurts LLM Performance Despite Perfect Retrieval](https://arxiv.org/abs/2510.05381) | 2024 | Long context degrades performance independent of retrieval quality | Pass 2 context length management |
| [Why Does the Effective Context Length of LLMs Fall Short?](https://arxiv.org/abs/2410.18745) | 2024 | Effective context significantly shorter than nominal; ~15% degradation 4K→128K | Context budget justification |
| [LongICLBench: LLMs Under Long In-Context Learning](https://arxiv.org/abs/2404.02060) | 2024 | Zero accuracy for most LLMs on 174-class single-prompt | Scale failure quantification |

---

## 13. Benchmark Frameworks Referenced

| Framework | Description | URL |
|---|---|---|
| **MT-Bench** | Multi-turn conversation benchmark; established LLM-as-judge for instruction-following | [github.com/lm-sys/FastChat](https://github.com/lm-sys/FastChat/tree/main/fastchat/llm_judge) |
| **AlpacaEval 2.0** | Length-controlled win rate; Spearman 0.98 with Chatbot Arena; <$10 to run | [tatsu-lab.github.io/alpaca_eval](https://tatsu-lab.github.io/alpaca_eval/) |
| **FActScore** | Atomic factual precision evaluation; pip install factscore | [github.com/shmsw25/FActScore](https://github.com/shmsw25/FActScore) |
| **RewardBench** | Reward model and judge evaluation benchmark | [allenai.github.io/reward-bench](https://allenai.github.io/reward-bench/) |
| **JudgeBench** | Benchmark for evaluating LLM judges | [arxiv.org/abs/2410.12784](https://arxiv.org/abs/2410.12784) |
| **Chatbot Arena** | Human preference benchmark; gold standard for judge calibration | [lmarena.ai](https://lmarena.ai/) |
| **HealthBench** | Physician-authored rubrics; instance-specific criteria at scale | [openai.com/index/healthbench](https://openai.com/index/healthbench/) |

---

## Reading Priority for Refract

**Start here (directly implement):**
1. arXiv:2305.17926 — position bias and swap augmentation (TODO 6.2)
2. arXiv:2303.16634 — G-Eval CoT + probability weighting (TODO 6.3, 6.5)
3. arXiv:2404.13076 — self-preference bias quantification (TODO 6.1)

**Read next (framework design):**
4. arXiv:2411.15594 — LLM-as-judge survey (comprehensive overview)
5. arXiv:2501.00274 — LLM-Rubric (calibrated multi-dimensional evaluation)
6. arXiv:2403.00165 — TELEClass (validates multi-pass architecture choice)

**Read when scaling (100+ articles, test set established):**
7. arXiv:2403.12968 — LLMLingua-2 (token compression, TODO 6.9)
8. arXiv:2407.18370 — Trust or Escalate (ensemble cascade design)
9. arXiv:2604.23178 — Judging the Judges 2026 (most comprehensive bias mitigation study)
