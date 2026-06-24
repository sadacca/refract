"""
Headless batch evaluation pipeline.
Reads data/input/article_urls.txt, runs ingest + eval per article.
Skips articles already in data/processed/ by default.

Usage:
  python scripts/batch_eval.py [--url-file path] [--skip-cached] [--max N] [--model name]
"""
import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import (
    INPUT_DIR,
    PROCESSED_DIR,
    FRAMEWORK_VERSION,
    EVAL_MODEL,
    JUDGE_MODEL,
    TRIAGE_MODEL,
    RATE_LIMIT_DELAY,
    model_abbrev,
    _cross_family_default,
)
from src.refract.ingest import fetch_url, _already_evaluated
from src.refract.bias_eval import evaluate_article

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_urls(url_file: Path) -> list[str]:
    urls = []
    for line in url_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def verify_precomputed() -> bool:
    from config import PRECOMPUTED_DIR, TAXONOMY_VERSION
    index_path = PRECOMPUTED_DIR / "taxonomy_index.json"
    if not index_path.exists():
        logger.error(
            "data/precomputed/taxonomy_index.json not found. "
            "Run scripts/precompute.py before batch_eval."
        )
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url-file",
        type=Path,
        default=INPUT_DIR / "article_urls.txt",
    )
    parser.add_argument(
        "--skip-cached",
        action="store_true",
        default=True,
        help="Skip articles already in data/processed/",
    )
    parser.add_argument(
        "--no-skip-cached",
        action="store_false",
        dest="skip_cached",
        help="Re-evaluate articles even if already in data/processed/",
    )
    parser.add_argument("--max", type=int, default=None, dest="max_articles")
    parser.add_argument("--model", default=EVAL_MODEL, dest="model")
    parser.add_argument(
        "--judge-model",
        default="",
        dest="judge_model",
        help=(
            "Judge model for Pass 4. Empty (default) = auto cross-family: "
            "Groq eval → Gemini judge, Gemini eval → Llama judge."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["deep", "flat"],
        default="deep",
        help="deep: Pass 1 triage + Pass 3 recall probes; flat: Pass 2 on all categories directly",
    )
    args = parser.parse_args()

    effective_judge = args.judge_model if args.judge_model else _cross_family_default(args.model)

    if not verify_precomputed():
        sys.exit(1)

    if not args.url_file.exists():
        logger.error("URL file not found: %s", args.url_file)
        sys.exit(1)

    urls = load_urls(args.url_file)
    if args.max_articles:
        urls = urls[: args.max_articles]

    model_sig = f"{model_abbrev(TRIAGE_MODEL)}_{model_abbrev(args.model)}_{model_abbrev(effective_judge)}"
    logger.info(
        "Loaded %d URLs from %s | triage=%s eval=%s judge=%s mode=%s (sig: %s)",
        len(urls), args.url_file, TRIAGE_MODEL, args.model, effective_judge, args.mode, model_sig,
    )

    processed = 0
    skipped = 0
    failed = 0

    for i, url in enumerate(urls, 1):
        logger.info("[%d/%d] %s", i, len(urls), url)

        try:
            article = fetch_url(url)
            article_id = article["article_id"]

            if args.skip_cached and _already_evaluated(article_id, FRAMEWORK_VERSION, model_sig, args.mode):
                logger.info("  Skipped (already evaluated with %s/%s)", model_sig, args.mode)
                skipped += 1
                continue

            logger.info("  Evaluating (%d words)...", article.get("word_count", 0))
            evaluate_article(
                article,
                eval_model=args.model,
                judge_model=effective_judge,
                triage_model=TRIAGE_MODEL,
                mode=args.mode,
            )
            processed += 1
            logger.info("  Done.")

        except Exception as e:
            logger.error("  Failed: %s", e)
            failed += 1

        if i < len(urls):
            time.sleep(RATE_LIMIT_DELAY)

    logger.info(
        "\nBatch complete: %d processed, %d skipped, %d failed",
        processed,
        skipped,
        failed,
    )


if __name__ == "__main__":
    main()
