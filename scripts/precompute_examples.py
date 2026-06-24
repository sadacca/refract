"""
Generate candidate reference examples for bias entries with examples_status: "pending".
Writes to data/pending_examples/{bias_id}.json.
Does NOT update taxonomy.json — human review via Framework Dashboard required first.

Usage:
  python scripts/precompute_examples.py [--status pending] [--bias-id confirmation-bias]
"""
import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import (
    GEMINI_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, MISTRAL_API_KEY,
    PRECOMPUTE_CHAIN, PENDING_EXAMPLES_DIR,
)
from src.refract.llm_client import call_llm, select_from_chain

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TAXONOMY_PATH = ROOT / "bias_index" / "taxonomy.json"

EXAMPLES_SYSTEM = """You are a cognitive psychology expert and journalism scholar.
Your task is to generate reference examples for a cognitive bias taxonomy.
These examples will be used as few-shot anchors in an evaluation pipeline.
Generate realistic journalism excerpts — they should read like actual news writing.
Output structured JSON only."""

EXAMPLES_PROMPT = """Generate reference examples for the following cognitive bias:

Name: {name}
Definition: {definition}
Identification criteria:
{criteria}
Linguistic signals:
{signals}
Common confusions: {confusions}

Generate:
1. THREE positive examples: short journalism excerpts (2-4 sentences each) that clearly exhibit
   this bias. Each should use a different linguistic mechanism from the signals above, and span
   different topic domains (politics, economics, crime, science, sport, health).
2. TWO near-miss examples: journalism excerpts that look like this bias but are NOT instances of it.
   Include a brief why_not explanation for each.
3. ONE contrast example: an excerpt exhibiting the most commonly confused bias ({contrast_bias}),
   with a distinction explanation.

Return JSON:
{{
  "bias_id": "{bias_id}",
  "positive": [
    {{"excerpt": "text", "mechanism": "which linguistic signal this exemplifies", "domain": "topic domain"}},
    {{"excerpt": "text", "mechanism": "...", "domain": "..."}},
    {{"excerpt": "text", "mechanism": "...", "domain": "..."}}
  ],
  "near_miss": [
    {{"excerpt": "text", "why_not": "one sentence explanation"}},
    {{"excerpt": "text", "why_not": "..."}}
  ],
  "contrast": {{
    "bias": "{contrast_bias}",
    "excerpt": "text",
    "distinction": "one sentence distinguishing from {name}"
  }}
}}"""


def generate_examples(bias: dict, model: str) -> dict:
    criteria = "\n".join(f"  - {c}" for c in bias.get("identification_criteria", []))
    signals = "\n".join(f"  - {s}" for s in bias.get("linguistic_signals", []))
    confusions = bias.get("common_confusions", [])
    contrast_bias = confusions[0]["bias"] if confusions else "a similar bias"

    prompt = EXAMPLES_PROMPT.format(
        name=bias["name"],
        bias_id=bias["id"],
        definition=bias["definition"],
        criteria=criteria,
        signals=signals,
        confusions=", ".join(c["bias"] for c in confusions) if confusions else "none noted",
        contrast_bias=contrast_bias,
    )
    return call_llm(prompt, model, system=EXAMPLES_SYSTEM)


def generate_examples_with_fallback(bias: dict, chain: list[tuple[str, int]]) -> dict:
    """Try each model in `chain`, starting with the RPD-aware pick, falling
    through to the rest on failure (HTTP error, decommissioned model, etc.)."""
    chain_models = [m for m, _ in chain]
    primary = select_from_chain(chain)
    ordered = [primary] + [m for m in chain_models if m != primary]

    last_err: Exception | None = None
    for model in ordered:
        try:
            return generate_examples(bias, model)
        except Exception as e:
            logger.warning("    %s failed: %s — trying next model in chain", model, e)
            last_err = e
    raise last_err


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", default="pending", help="Only process entries with this examples_status")
    parser.add_argument("--bias-id", default=None, help="Process only this bias ID")
    args = parser.parse_args()

    if not any([GEMINI_API_KEY, GROQ_API_KEY, CEREBRAS_API_KEY, MISTRAL_API_KEY]):
        logger.error("No LLM API key set (GEMINI/GROQ/CEREBRAS/MISTRAL_API_KEY)")
        sys.exit(1)

    taxonomy = json.loads(TAXONOMY_PATH.read_text())
    biases = taxonomy["biases"]

    if args.bias_id:
        biases = [b for b in biases if b["id"] == args.bias_id]
    else:
        biases = [b for b in biases if b.get("examples_status") == args.status]

    if not biases:
        logger.info("No entries matched filter. Nothing to do.")
        return

    PENDING_EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Generating examples for %d bias entries...", len(biases))

    for bias in biases:
        logger.info("  Generating: %s", bias["name"])
        try:
            result = generate_examples_with_fallback(bias, PRECOMPUTE_CHAIN)
            out_path = PENDING_EXAMPLES_DIR / f"{bias['id']}.json"
            out_path.write_text(json.dumps(result, indent=2))
            logger.info("  Written: %s", out_path)
        except Exception as e:
            logger.error("  Failed for %s: %s", bias["name"], e)

    logger.info("\nDone. Review candidates in data/pending_examples/ before accepting into taxonomy.json.")


if __name__ == "__main__":
    main()
