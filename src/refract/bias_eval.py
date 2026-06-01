"""
4-pass cognitive bias evaluation pipeline.

Pass 1: Category triage — which of the 10 bias categories are present?
Pass 2: Bias identification — one call per flagged category, injecting
        precomputed bias blocks and reference examples as few-shot anchors.
Pass 3: Recall probes — one yes/no call per unflagged category to surface misses.
Pass 4: LLM judge — pointwise quality check on all detections.

All prompt blocks are loaded from data/precomputed/ — no prompt assembly at runtime.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import (
    PRECOMPUTED_DIR,
    PROCESSED_DIR,
    FRAMEWORK_VERSION,
    TAXONOMY_VERSION,
    EVAL_MODEL,
    JUDGE_MODEL,
    TRIAGE_MODEL,
)
from src.refract.llm_client import call_llm

logger = logging.getLogger(__name__)

BIAS_INDEX_PATH = Path("bias_index/taxonomy.json")


def _load_taxonomy() -> dict:
    return json.loads(BIAS_INDEX_PATH.read_text())


def _load_block(subdir: str, filename: str) -> str:
    path = PRECOMPUTED_DIR / subdir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"Precomputed block missing: {path}. Run scripts/precompute.py first."
        )
    return path.read_text()


def _all_categories(taxonomy: dict) -> list[str]:
    return sorted({b["category"] for b in taxonomy["biases"]})


def _biases_for_category(taxonomy: dict, category: str) -> list[dict]:
    return [b for b in taxonomy["biases"] if b["category"] == category]


# ---------------------------------------------------------------------------
# Pass 1: Category triage
# ---------------------------------------------------------------------------

PASS1_SYSTEM = """You are a cognitive psychology expert evaluating written text for cognitive bias patterns.
Your task is to identify which broad bias categories are likely present in the article.
Be inclusive: flag a category if there is any plausible reason to investigate it further.
Output structured JSON only."""

PASS1_PROMPT = """Article text:
\"\"\"
{article_text}
\"\"\"

Available categories:
{categories}

Return JSON:
{{
  "flagged_categories": ["list of category names that may contain bias instances"],
  "rationale": {{
    "<category_name>": "one sentence why this category may be present"
  }}
}}"""


def pass1_category_triage(article_text: str, taxonomy: dict, model: str) -> dict:
    categories = _all_categories(taxonomy)
    prompt = PASS1_PROMPT.format(
        article_text=article_text[:6000],
        categories="\n".join(f"- {c}" for c in categories),
    )
    result = call_llm(prompt, model, system=PASS1_SYSTEM)
    return result


# ---------------------------------------------------------------------------
# Pass 2: Bias identification per flagged category
# ---------------------------------------------------------------------------

PASS2_SYSTEM = """You are a cognitive psychology expert identifying specific cognitive bias instances in written text.
You will be given a bias definition block with identification criteria, linguistic signals, and reference examples.
Your task is to find all instances of these biases in the article — quote the exact excerpt, give its location, and explain the bias mechanism.
Be precise: only flag instances that clearly match the identification criteria. Do not infer intent.
Output structured JSON only."""

PASS2_PROMPT = """Bias reference block:
{bias_block}

Article text:
\"\"\"
{article_text}
\"\"\"

For each bias listed in the reference block, identify all instances in the article.

Return JSON:
{{
  "bias_instances": [
    {{
      "bias_id": "string",
      "bias_name": "string",
      "occurrences": [
        {{
          "excerpt": "exact quoted text from article",
          "char_start": integer,
          "char_end": integer,
          "paragraph_index": integer,
          "text_region": "headline|lede|body|closing",
          "explanation": "how this excerpt exhibits the bias per the identification criteria",
          "confidence": "high|medium|low"
        }}
      ],
      "severity": "high|medium|low",
      "author_exhibiting": true,
      "source_reporting": false
    }}
  ]
}}

If no instances of a bias are found, omit it from the list entirely."""


def _build_bias_block(biases: list[dict]) -> str:
    lines = []
    for b in biases:
        lines.append(f"=== {b['name']} (id: {b['id']}) ===")
        lines.append(f"Definition: {b['definition']}")
        lines.append("Identification criteria:")
        for c in b.get("identification_criteria", []):
            lines.append(f"  - {c}")
        lines.append("Linguistic signals:")
        for s in b.get("linguistic_signals", []):
            lines.append(f"  - {s}")

        ref = b.get("reference_examples", {})
        positives = ref.get("positive", [])
        if positives:
            lines.append("Positive examples (text that DOES exhibit this bias):")
            for i, ex in enumerate(positives, 1):
                excerpt = ex.get("excerpt", ex) if isinstance(ex, dict) else ex
                lines.append(f"  [{i}] {excerpt}")

        near_misses = ref.get("near_miss", [])
        if near_misses:
            lines.append("Near-miss examples (text that looks like this bias but is NOT):")
            for ex in near_misses:
                if isinstance(ex, dict):
                    lines.append(f"  - {ex.get('excerpt', '')} [Why not: {ex.get('why_not', '')}]")
                else:
                    lines.append(f"  - {ex}")

        contrast = ref.get("contrast")
        if contrast and isinstance(contrast, dict):
            lines.append(
                f"Contrast example (most commonly confused bias — {contrast.get('bias', '')}): "
                f"{contrast.get('excerpt', '')} [Distinction: {contrast.get('distinction', '')}]"
            )

        lines.append("")
    return "\n".join(lines)


def pass2_identify(
    article_text: str, category: str, taxonomy: dict, model: str
) -> list[dict]:
    biases = _biases_for_category(taxonomy, category)
    if not biases:
        return []

    bias_block = _build_bias_block(biases)
    prompt = PASS2_PROMPT.format(
        bias_block=bias_block,
        article_text=article_text[:8000],
    )
    result = call_llm(prompt, model, system=PASS2_SYSTEM)
    return result.get("bias_instances", [])


# ---------------------------------------------------------------------------
# Pass 3: Recall probes for unflagged categories
# ---------------------------------------------------------------------------

PASS3_SYSTEM = """You are a cognitive psychology expert auditing whether a specific bias category is absent from an article.
Answer whether any instance of the specified bias is present.
If yes, provide the excerpt and explanation. If no, briefly explain why not.
Be honest: it is acceptable to confirm absence.
Output structured JSON only."""

PASS3_PROMPT = """Bias to probe: {bias_name}
Definition: {definition}
Identification criteria:
{criteria}

Article text:
\"\"\"
{article_text}
\"\"\"

Return JSON:
{{
  "found": true | false,
  "excerpt": "exact quoted text if found, else null",
  "explanation": "why this is or is not an instance of {bias_name}"
}}"""


def pass3_recall_probe(
    article_text: str, bias: dict, model: str
) -> Optional[dict]:
    criteria = "\n".join(f"  - {c}" for c in bias.get("identification_criteria", []))
    prompt = PASS3_PROMPT.format(
        bias_name=bias["name"],
        definition=bias["definition"],
        criteria=criteria,
        article_text=article_text[:6000],
    )
    result = call_llm(prompt, model, system=PASS3_SYSTEM)
    if result.get("found"):
        return {
            "bias_id": bias["id"],
            "bias_name": bias["name"],
            "occurrences": [
                {
                    "excerpt": result.get("excerpt", ""),
                    "char_start": None,
                    "char_end": None,
                    "paragraph_index": None,
                    "text_region": "body",
                    "explanation": result.get("explanation", ""),
                    "confidence": "low",
                }
            ],
            "severity": "low",
            "author_exhibiting": True,
            "source_reporting": False,
            "recall_probe": True,
        }
    return None


# ---------------------------------------------------------------------------
# Pass 4: LLM judge
# ---------------------------------------------------------------------------

PASS4_SYSTEM = """You are an independent cognitive psychology evaluator reviewing bias detection outputs.
Your task is to assess whether each detected bias instance is correctly identified.
Criteria: (1) Does the quoted excerpt actually exhibit the stated bias per the definition?
(2) Is the explanation accurate and well-grounded?
You must provide a verdict and specific evidence for each instance.
Output structured JSON only."""

PASS4_PROMPT = """Review the following bias detection results for this article.

Article text:
\"\"\"
{article_text}
\"\"\"

Detected instances:
{instances_json}

For each instance, return:
{{
  "judgments": [
    {{
      "instance_id": "string",
      "bias_id": "string",
      "verdict": "confirmed|suspect|rejected",
      "rationale": "one or two sentences explaining the verdict with specific reference to the excerpt"
    }}
  ],
  "overall_quality": "high|medium|low",
  "notes": "any patterns in the evaluation worth noting"
}}"""


def pass4_judge(
    article_text: str, bias_instances: list[dict], judge_model: str
) -> dict:
    if not bias_instances:
        return {"judgments": [], "overall_quality": "high", "notes": "No instances to judge."}

    instances_with_ids = []
    for i, inst in enumerate(bias_instances):
        inst_copy = dict(inst)
        inst_copy["instance_id"] = f"inst_{i:03d}"
        instances_with_ids.append(inst_copy)

    prompt = PASS4_PROMPT.format(
        article_text=article_text[:6000],
        instances_json=json.dumps(instances_with_ids, indent=2),
    )
    result = call_llm(prompt, judge_model, system=PASS4_SYSTEM)
    return result


# ---------------------------------------------------------------------------
# Full evaluation pipeline
# ---------------------------------------------------------------------------

def evaluate_article(
    article: dict,
    eval_model: str = EVAL_MODEL,
    judge_model: str = JUDGE_MODEL,
    triage_model: str = TRIAGE_MODEL,
    mode: str = "deep",
    run_judge: bool = True,
) -> dict:
    """
    Run the full 4-pass evaluation on an article record.
    Pass 1 + 3 use triage_model (small/fast); Pass 2 + 4 use eval_model/judge_model (large).
    Returns the complete evaluation dict; writes result to data/processed/.
    """
    taxonomy = _load_taxonomy()
    text = article["text"]
    article_id = article["article_id"]

    logger.info("Pass 1: category triage [%s] for article %s", triage_model, article_id)
    p1 = pass1_category_triage(text, taxonomy, triage_model)
    flagged = set(p1.get("flagged_categories", []))
    all_cats = set(_all_categories(taxonomy))
    unflagged = all_cats - flagged

    logger.info("Flagged categories: %s", flagged)

    # Pass 2: identify in flagged categories (large model)
    bias_instances = []
    for category in sorted(flagged):
        logger.info("Pass 2: identifying biases in category '%s' [%s]", category, eval_model)
        instances = pass2_identify(text, category, taxonomy, eval_model)
        for inst in instances:
            inst["category"] = category
        bias_instances.extend(instances)

    # Pass 3: recall probes for unflagged categories (small model — yes/no task)
    recall_finds = 0
    for category in sorted(unflagged):
        for bias in _biases_for_category(taxonomy, category):
            logger.info("Pass 3: recall probe for '%s' [%s]", bias["name"], triage_model)
            found = pass3_recall_probe(text, bias, triage_model)
            if found:
                found["category"] = category
                bias_instances.append(found)
                recall_finds += 1

    # Pass 4: judge
    judge_result = {}
    if run_judge and bias_instances:
        logger.info("Pass 4: LLM judge review")
        judge_result = pass4_judge(text, bias_instances, judge_model)

    # Build output
    now = datetime.now(timezone.utc).isoformat()
    by_region: dict[str, int] = {"headline": 0, "lede": 0, "body": 0, "closing": 0}
    by_category: dict[str, int] = {}
    total_occ = 0

    for inst in bias_instances:
        cat = inst.get("category", "Unknown")
        by_category[cat] = by_category.get(cat, 0) + len(inst.get("occurrences", []))
        for occ in inst.get("occurrences", []):
            region = occ.get("text_region", "body")
            if region in by_region:
                by_region[region] += 1
            total_occ += 1

    dominant = sorted(by_category, key=by_category.get, reverse=True)[:3]

    evaluation = {
        "article_id": article_id,
        "source_url": article.get("url"),
        "title": article.get("title"),
        "evaluated_at": now,
        "framework_version": FRAMEWORK_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "model": eval_model,
        "mode": mode,
        "article_text": text,
        "pass1_result": p1,
        "bias_instances": bias_instances,
        "judge_result": judge_result,
        "summary": {
            "dominant_categories": dominant,
            "bias_type_count": len({i["bias_id"] for i in bias_instances}),
            "total_occurrences": total_occ,
            "low_confidence_count": sum(
                1 for i in bias_instances
                for o in i.get("occurrences", [])
                if o.get("confidence") == "low"
            ),
            "recall_probe_finds": recall_finds,
            "by_region": by_region,
            "by_category": by_category,
        },
    }

    # Persist
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{article_id}_{FRAMEWORK_VERSION}.json"
    out_path.write_text(json.dumps(evaluation, indent=2))
    logger.info("Evaluation written to %s", out_path)

    return evaluation
