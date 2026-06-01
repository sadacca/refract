"""
4-pass cognitive bias evaluation pipeline with optional Pass 0 paragraph triage.

Pass 0: Paragraph triage — chunk article into paragraphs, map each category to
        the paragraph indices worth deep review. Cached per article.
Pass 1: Category triage — which bias categories are present? (deep mode only)
Pass 2: Bias identification — one call per flagged category, using only the
        paragraphs selected in Pass 0 instead of the full article.
Pass 3: Recall probes — one batched call per unflagged category (deep mode only).
Pass 4: LLM judge — pointwise quality check on all detections.

# TODO — alternatives to Pass 0 paragraph triage worth researching:
#   A) Extend Pass 1 to return paragraph-level assignments per category in a
#      single call (saves one round-trip; risk: overloads Pass 1 prompt quality).
#   B) Embedding-based pre-filter: embed paragraphs + bias definitions, select
#      top-K by cosine similarity before any LLM call. Zero LLM cost for selection;
#      requires an embedding model/API and adds infrastructure complexity.

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
# Pass 0: Paragraph chunking + category-to-paragraph mapping
# ---------------------------------------------------------------------------

def _chunk_paragraphs(text: str) -> list[dict]:
    """Split text into paragraphs, preserving original char offsets."""
    paragraphs = []
    pos = 0
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            pos = text.find("\n\n", pos) + 2
            continue
        start = text.find(block, pos)
        end = start + len(block)
        paragraphs.append({"idx": len(paragraphs), "char_start": start, "char_end": end, "text": block})
        pos = end
    return paragraphs


PASS0_SYSTEM = """You are a cognitive psychology expert doing rapid relevance triage.
Given a list of article paragraphs and a set of bias categories, identify which paragraphs
are worth deep review for each category. Be inclusive but efficient — only include paragraphs
that contain language, claims, or framing plausibly related to the category.
Output structured JSON only."""

PASS0_PROMPT = """Bias categories to map:
{categories}

Article paragraphs (index | char range | preview):
{paragraph_list}

Return JSON mapping each category to the paragraph indices that warrant deep review:
{{
  "category_paragraphs": {{
    "<category_name>": [0, 3, 7]
  }}
}}

If a category has no relevant paragraphs, map it to an empty list."""


def pass0_paragraph_triage(
    paragraphs: list[dict], categories: list[str], model: str
) -> dict[str, list[int]]:
    para_list = "\n".join(
        f"[{p['idx']}] chars {p['char_start']}-{p['char_end']}: {p['text'][:120].replace(chr(10), ' ')}..."
        for p in paragraphs
    )
    prompt = PASS0_PROMPT.format(
        categories="\n".join(f"- {c}" for c in categories),
        paragraph_list=para_list,
    )
    result = call_llm(prompt, model, system=PASS0_SYSTEM)
    return result.get("category_paragraphs", {})


def _paragraphs_for_pass2(paragraphs: list[dict], indices: list[int]) -> str:
    """Reconstruct article text subset with original char offsets embedded as anchors."""
    selected = [p for p in paragraphs if p["idx"] in set(indices)]
    if not selected:
        return ""
    blocks = []
    for p in selected:
        blocks.append(f"[chars {p['char_start']}-{p['char_end']}]\n{p['text']}")
    return "\n\n".join(blocks)


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
    # article_text may be full article or a paragraph-filtered subset (from Pass 0).
    # When filtered, char offsets embedded in the text let the LLM report accurate positions.
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
    all_cats = sorted(_all_categories(taxonomy))

    p0: dict = {}
    p1: dict = {}
    recall_finds = 0

    # Pass 0: paragraph triage — always runs to reduce Pass 2 article payload.
    # Maps each category to the paragraph indices worth deep review.
    paragraphs = _chunk_paragraphs(text)
    logger.info(
        "Pass 0: paragraph triage — %d paragraphs, %d categories [%s]",
        len(paragraphs), len(all_cats), triage_model,
    )
    category_paragraphs = pass0_paragraph_triage(paragraphs, all_cats, triage_model)
    p0 = {"paragraph_count": len(paragraphs), "category_paragraphs": category_paragraphs}

    bias_instances = []

    if mode == "flat":
        # Skip category triage and recall probes — run Pass 2 on every category.
        # Fewer total calls at small taxonomy sizes; useful for comparing against deep mode.
        logger.info("Mode=flat: running Pass 2 on all %d categories [%s]", len(all_cats), eval_model)
        for category in all_cats:
            indices = category_paragraphs.get(category, [])
            article_slice = _paragraphs_for_pass2(paragraphs, indices) if indices else text[:8000]
            logger.info(
                "Pass 2: category '%s' — %d/%d paragraphs selected",
                category, len(indices), len(paragraphs),
            )
            instances = pass2_identify(article_slice, category, taxonomy, eval_model)
            for inst in instances:
                inst["category"] = category
            bias_instances.extend(instances)
    else:
        # deep mode: Pass 1 category triage → Pass 2 flagged → Pass 3 recall probes
        logger.info("Pass 1: category triage [%s] for article %s", triage_model, article_id)
        p1 = pass1_category_triage(text, taxonomy, triage_model)
        flagged = set(p1.get("flagged_categories", []))
        unflagged = set(all_cats) - flagged

        logger.info("Flagged categories: %s", flagged)

        for category in sorted(flagged):
            indices = category_paragraphs.get(category, [])
            article_slice = _paragraphs_for_pass2(paragraphs, indices) if indices else text[:8000]
            logger.info(
                "Pass 2: category '%s' — %d/%d paragraphs [%s]",
                category, len(indices), len(paragraphs), eval_model,
            )
            instances = pass2_identify(article_slice, category, taxonomy, eval_model)
            for inst in instances:
                inst["category"] = category
            bias_instances.extend(instances)

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

        # Filter instances the judge rejected — they are false positives.
        # TODO: accumulate rejected excerpts as near-miss examples in the taxonomy
        #       so future Pass 2 calls have better few-shot anchors. Needs a human
        #       review loop before writing back (scripts/review_pending_examples.py).
        rejected_ids = {
            j["bias_id"]
            for j in judge_result.get("judgments", [])
            if j.get("verdict") == "rejected"
        }
        if rejected_ids:
            logger.info("Pass 4 rejected %d bias type(s): %s", len(rejected_ids), rejected_ids)
            bias_instances = [i for i in bias_instances if i["bias_id"] not in rejected_ids]

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
        "pass0_result": p0,
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
            "pass0_paragraph_count": len(paragraphs),
            "pass0_avg_paragraphs_per_category": (
                round(sum(len(v) for v in category_paragraphs.values()) / len(all_cats), 1)
                if all_cats else 0
            ),
        },
    }

    # Persist
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{article_id}_{FRAMEWORK_VERSION}.json"
    out_path.write_text(json.dumps(evaluation, indent=2))
    logger.info("Evaluation written to %s", out_path)

    return evaluation
