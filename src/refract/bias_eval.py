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
    COMPRESS_PASS2,
    COMPRESSION_RATE,
    JUDGE_SWAP_AUGMENTATION,
)
from src.refract.llm_client import call_llm

logger = logging.getLogger(__name__)

BIAS_INDEX_PATH = Path("bias_index/taxonomy.json")

# ---------------------------------------------------------------------------
# T4 / TODO 6.9: Optional LLMLingua-2 compression for Pass 2 article slices.
# Lazy-loaded so the import cost and model download only hit when COMPRESS_PASS2=true.
# Falls back silently if llmlingua is not installed.
# ---------------------------------------------------------------------------
_compressor: object = None


def _get_compressor():
    global _compressor
    if _compressor is None:
        try:
            from llmlingua import PromptCompressor  # type: ignore[import]
            _compressor = PromptCompressor(
                model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
                use_llmlingua2=True,
            )
            logger.info("LLMLingua-2 compressor loaded")
        except ImportError:
            logger.warning("llmlingua not installed; COMPRESS_PASS2 disabled. Run: pip install llmlingua")
            _compressor = False
        except Exception as e:
            logger.warning("LLMLingua-2 load failed (%s) — compression disabled", e)
            _compressor = False
    return _compressor if _compressor is not False else None


def _compress_text(text: str, rate: float) -> str:
    """Compress text to ~rate fraction of original tokens via LLMLingua-2."""
    compressor = _get_compressor()
    if compressor is None or not text.strip():
        return text
    try:
        result = compressor.compress_prompt(text, rate=rate, force_tokens=["\n"])
        return result.get("compressed_prompt", text)
    except Exception as e:
        logger.warning("LLMLingua compression failed (%s) — using original text", e)
        return text


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


def pass1_category_triage(
    article_text: str,
    taxonomy: dict,
    model: str,
    categories: list[str] | None = None,
) -> dict:
    # T3/6.7: accepts a pre-filtered category list so zero-paragraph categories
    # (already routed to Pass 3 by the Pass 0 short-circuit) are excluded.
    if categories is None:
        categories = _all_categories(taxonomy)
    if not categories:
        return {"flagged_categories": [], "rationale": {}}
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

PASS3_SYSTEM = """You are a cognitive psychology expert auditing whether specific biases are absent from an article.
For each bias listed, answer whether any instance is present in the article.
Be honest: it is acceptable to confirm absence for most or all biases.
Output structured JSON only."""

PASS3_PROMPT = """Article text:
\"\"\"
{article_text}
\"\"\"

For each bias below, determine if any instance is present in the article.

{bias_blocks}

Return JSON:
{{
  "findings": [
    {{
      "bias_id": "string",
      "found": true | false,
      "excerpt": "exact quoted text if found, else null",
      "explanation": "one sentence: why this is or is not present"
    }}
  ]
}}"""


def _format_bias_block_compact(bias: dict) -> str:
    criteria = "; ".join(bias.get("identification_criteria", [])[:2])
    return f"- {bias['name']} (id: {bias['id']}): {bias['definition']} Criteria: {criteria}"


def pass3_recall_probe_batch(
    article_text: str, biases: list[dict], model: str
) -> list[dict]:
    """Probe multiple biases in one call. Returns a list of found bias instances."""
    if not biases:
        return []
    bias_blocks = "\n".join(_format_bias_block_compact(b) for b in biases)
    prompt = PASS3_PROMPT.format(
        article_text=article_text[:6000],
        bias_blocks=bias_blocks,
    )
    result = call_llm(prompt, model, system=PASS3_SYSTEM)
    findings = result.get("findings", [])

    # Build a lookup so we can hydrate full bias metadata from the id
    bias_by_id = {b["id"]: b for b in biases}
    instances = []
    for f in findings:
        if not f.get("found"):
            continue
        bias = bias_by_id.get(f.get("bias_id", ""))
        if not bias:
            continue
        instances.append({
            "bias_id": bias["id"],
            "bias_name": bias["name"],
            "occurrences": [
                {
                    "excerpt": f.get("excerpt", ""),
                    "char_start": None,
                    "char_end": None,
                    "paragraph_index": None,
                    "text_region": "body",
                    "explanation": f.get("explanation", ""),
                    "confidence": "low",
                }
            ],
            "severity": "low",
            "author_exhibiting": True,
            "source_reporting": False,
            "recall_probe": True,
        })
    return instances


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
      "rationale": "one or two sentences explaining the verdict with specific reference to the excerpt",
      "verdict": "confirmed|suspect|rejected"
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

    def _run(ordered: list[dict]) -> dict:
        prompt = PASS4_PROMPT.format(
            article_text=article_text[:6000],
            instances_json=json.dumps(ordered, indent=2),
        )
        return call_llm(prompt, judge_model, system=PASS4_SYSTEM)

    result_a = _run(instances_with_ids)

    # Swap augmentation (TODO 6.2): run the judge a second time with instance order
    # reversed. A verdict that flips based solely on list position is position-biased
    # rather than content-grounded; those instances are downgraded to "suspect".
    # Wang et al. ACL 2024 (arXiv:2305.17926): reordering alone flips 66/80 rankings.
    if not JUDGE_SWAP_AUGMENTATION or len(instances_with_ids) <= 1:
        return result_a

    result_b = _run(list(reversed(instances_with_ids)))

    # Match both runs by instance_id (stable across both orderings).
    verdicts_b = {j["instance_id"]: j for j in result_b.get("judgments", [])}

    quality_rank = {"high": 2, "medium": 1, "low": 0}
    merged = []
    disagreements = 0

    for j_a in result_a.get("judgments", []):
        iid = j_a.get("instance_id")
        j_b = verdicts_b.get(iid)
        v_a = j_a.get("verdict")
        v_b = j_b.get("verdict") if j_b else None

        if v_b is None or v_a == v_b:
            merged.append({**j_a, "swap_agreement": True})
        else:
            disagreements += 1
            merged.append({
                **j_a,
                "verdict": "suspect",
                "swap_agreement": False,
                "swap_verdicts": {"forward": v_a, "reversed": v_b},
            })

    q_a = result_a.get("overall_quality", "medium")
    q_b = result_b.get("overall_quality", "medium")
    overall_quality = q_a if quality_rank.get(q_a, 1) <= quality_rank.get(q_b, 1) else q_b

    return {
        "judgments": merged,
        "overall_quality": overall_quality,
        "notes": (
            f"Swap augmentation: {disagreements}/{len(merged)} instance(s) showed "
            f"position-dependent verdicts and were downgraded to 'suspect'."
        ),
        "swap_augmentation": True,
    }


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
            if not indices:
                logger.info("Pass 2: skipping '%s' — Pass 0 found 0 relevant paragraphs", category)
                continue
            article_slice = _paragraphs_for_pass2(paragraphs, indices)
            if COMPRESS_PASS2 and article_slice:
                orig_len = len(article_slice)
                article_slice = _compress_text(article_slice, COMPRESSION_RATE)
                logger.info(
                    "Pass 2: compressed slice %d→%d chars (%.1fx) for '%s'",
                    orig_len, len(article_slice), orig_len / max(len(article_slice), 1), category,
                )
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
        #
        # T3/6.7 Pass 0 short-circuit: categories where Pass 0 found zero relevant
        # paragraphs bypass Pass 1 entirely and go straight to the Pass 3 recall probe.
        # This avoids Pass 1 wasting capacity on categories with no textual signal,
        # and prevents those categories from being incorrectly flagged or missed.
        cats_with_paragraphs = sorted(c for c in all_cats if category_paragraphs.get(c))
        cats_without_paragraphs = sorted(c for c in all_cats if not category_paragraphs.get(c))
        if cats_without_paragraphs:
            logger.info(
                "Pass 1: bypassing %d category(ies) with 0 Pass 0 paragraphs → Pass 3: %s",
                len(cats_without_paragraphs), cats_without_paragraphs,
            )
        logger.info(
            "Pass 1: category triage on %d/%d categories [%s] for article %s",
            len(cats_with_paragraphs), len(all_cats), triage_model, article_id,
        )
        p1 = pass1_category_triage(text, taxonomy, triage_model, categories=cats_with_paragraphs)
        flagged = set(p1.get("flagged_categories", []))
        # Unflagged = not flagged among paragraph-present categories + all zero-paragraph categories
        unflagged = (set(cats_with_paragraphs) - flagged) | set(cats_without_paragraphs)

        logger.info("Flagged categories: %s", flagged)

        for category in sorted(flagged):
            indices = category_paragraphs.get(category, [])
            if not indices:
                # Shouldn't happen after the short-circuit above, but guard defensively.
                logger.info("Pass 2: skipping '%s' — no paragraphs (should have been short-circuited)", category)
                unflagged.add(category)
                continue
            article_slice = _paragraphs_for_pass2(paragraphs, indices)
            if COMPRESS_PASS2 and article_slice:
                orig_len = len(article_slice)
                article_slice = _compress_text(article_slice, COMPRESSION_RATE)
                logger.info(
                    "Pass 2: compressed slice %d→%d chars (%.1fx) for '%s'",
                    orig_len, len(article_slice), orig_len / max(len(article_slice), 1), category,
                )
            logger.info(
                "Pass 2: category '%s' — %d/%d paragraphs [%s]",
                category, len(indices), len(paragraphs), eval_model,
            )
            instances = pass2_identify(article_slice, category, taxonomy, eval_model)
            for inst in instances:
                inst["category"] = category
            bias_instances.extend(instances)

        # Pass 3: one batched call per unflagged category (all biases in category together)
        # Includes categories demoted from Pass 2 by the zero-paragraph gate.
        for category in sorted(unflagged):
            biases_to_probe = _biases_for_category(taxonomy, category)
            if not biases_to_probe:
                continue
            logger.info(
                "Pass 3: recall probe — %d biases in '%s' [%s]",
                len(biases_to_probe), category, triage_model,
            )
            found_instances = pass3_recall_probe_batch(text, biases_to_probe, triage_model)
            for inst in found_instances:
                inst["category"] = category
            bias_instances.extend(found_instances)
            recall_finds += len(found_instances)

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
