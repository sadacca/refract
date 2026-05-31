"""
Article reframing pipeline.
Three modes: neutralize, steelman, annotated.
Loads strategy blocks from data/precomputed/reframe_blocks/.
"""
import json
import logging

from config import EVAL_MODEL
from src.refract.llm_client import call_llm

logger = logging.getLogger(__name__)

REFRAME_SYSTEM = """You are an expert editor trained in cognitive psychology. You are rewriting a news article
to reduce identified cognitive bias patterns while preserving all factual content.

Rules:
- Do not add any factual claims not present in the source text.
- Do not remove any facts. If reducing a bias would require adding facts you don't have, note the gap.
- Do not change the meaning of direct quotes.
- If you cannot reduce a bias without distorting the facts, flag it explicitly.

Output structured JSON only."""

NEUTRALIZE_PROMPT = """Rewrite the following article to reduce the identified cognitive biases.
Apply these reframing strategies for each detected bias:
{strategies}

Original article:
\"\"\"
{article_text}
\"\"\"

Return JSON:
{{
  "reframed_text": "full rewritten article text",
  "biases_addressed": ["list of bias_ids that were reduced in the reframe"],
  "gaps": ["list of biases that could not be fully addressed and why"],
  "notes": "brief description of the main changes made"
}}"""

STEELMAN_PROMPT = """Rewrite the following article to present the strongest version of each competing
perspective mentioned or implied in the article. For each viewpoint in the article, ensure it is
represented in its most reasonable, evidence-supported form.

Detected biases that affect perspective balance:
{strategies}

Original article:
\"\"\"
{article_text}
\"\"\"

Return JSON:
{{
  "reframed_text": "full rewritten article text",
  "perspectives_steelmanned": ["list of viewpoints strengthened"],
  "biases_addressed": ["list of bias_ids reduced"],
  "gaps": ["information needed but unavailable in source"],
  "notes": "brief description of changes"
}}"""

ANNOTATED_PROMPT = """Return the original article text with inline annotations for each detected
bias instance. Insert annotations as [BIAS: <bias_name> — <brief explanation>] immediately after
the relevant excerpt.

Detected bias instances:
{instances_json}

Original article:
\"\"\"
{article_text}
\"\"\"

Return JSON:
{{
  "annotated_text": "full article text with [BIAS: ...] annotations inserted inline",
  "annotation_count": integer,
  "notes": "any patterns worth noting across the annotations"
}}"""


def _build_strategies(bias_instances: list[dict], taxonomy: dict) -> str:
    taxonomy_index = {b["id"]: b for b in taxonomy["biases"]}
    lines = []
    seen = set()
    for inst in bias_instances:
        bid = inst.get("bias_id", "")
        if bid in seen:
            continue
        seen.add(bid)
        b = taxonomy_index.get(bid, {})
        strategy = b.get("reframing_strategy", "")
        example = b.get("reframing_example", "")
        if strategy:
            lines.append(f"- {inst.get('bias_name', bid)}: {strategy}")
            if example:
                lines.append(f"  Example: {example}")
    return "\n".join(lines) if lines else "No specific strategies available; apply general bias reduction principles."


def reframe_article(
    article_text: str,
    bias_instances: list[dict],
    taxonomy: dict,
    mode: str = "neutralize",
    model: str = EVAL_MODEL,
) -> dict:
    """
    Generate a reframed version of the article.
    mode: 'neutralize' | 'steelman' | 'annotated'
    Returns the reframe result dict.
    """
    mode = mode.lower()

    if mode == "neutralize":
        strategies = _build_strategies(bias_instances, taxonomy)
        prompt = NEUTRALIZE_PROMPT.format(
            strategies=strategies,
            article_text=article_text[:8000],
        )
    elif mode == "steelman":
        strategies = _build_strategies(bias_instances, taxonomy)
        prompt = STEELMAN_PROMPT.format(
            strategies=strategies,
            article_text=article_text[:8000],
        )
    elif mode == "annotated":
        instances_json = json.dumps(
            [
                {
                    "bias_id": i.get("bias_id"),
                    "bias_name": i.get("bias_name"),
                    "excerpts": [o.get("excerpt") for o in i.get("occurrences", [])],
                    "explanation": (i.get("occurrences") or [{}])[0].get("explanation", ""),
                }
                for i in bias_instances
            ],
            indent=2,
        )
        prompt = ANNOTATED_PROMPT.format(
            instances_json=instances_json,
            article_text=article_text[:8000],
        )
    else:
        raise ValueError(f"Unknown reframe mode: {mode}")

    result = call_llm(prompt, model, system=REFRAME_SYSTEM)
    result["mode"] = mode
    return result
