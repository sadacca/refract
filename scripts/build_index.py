"""
Rebuild data/processed/index.json, stats.json, and bias_frequency.json
from all evaluation records in data/processed/.

Usage:
  python scripts/build_index.py
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import PROCESSED_DIR


_INDEX_FILES = {
    "index.json", "stats.json", "bias_frequency.json", "model_provenance.json",
}


def load_evaluations() -> list[dict]:
    records = []
    for f in PROCESSED_DIR.glob("*.json"):
        if f.name in _INDEX_FILES:
            continue
        try:
            records.append(json.loads(f.read_text()))
        except Exception as e:
            print(f"  Warning: could not parse {f.name}: {e}")
    return records


def build_index(records: list[dict]) -> list[dict]:
    index = []
    for r in records:
        summary = r.get("summary", {})
        index.append({
            "article_id": r.get("article_id"),
            "url": r.get("source_url"),
            "title": r.get("title"),
            "source": r.get("source"),
            "evaluated_at": r.get("evaluated_at"),
            "framework_version": r.get("framework_version"),
            "taxonomy_version": r.get("taxonomy_version"),
            "model": r.get("model"),
            "models": r.get("models", {"eval": r.get("model"), "judge": None, "triage": None}),
            "bias_type_count": summary.get("bias_type_count", 0),
            "total_occurrences": summary.get("total_occurrences", 0),
            "dominant_categories": summary.get("dominant_categories", []),
            "word_count": len(r.get("article_text", "").split()),
        })
    return sorted(index, key=lambda x: x.get("evaluated_at", ""), reverse=True)


def build_stats(records: list[dict]) -> dict:
    if not records:
        return {}

    sources = Counter()
    fw_versions = Counter()
    total_instances = 0
    total_occurrences = 0
    category_counts: Counter = Counter()

    for r in records:
        sources[r.get("source", "unknown")] += 1
        fw_versions[r.get("framework_version", "unknown")] += 1
        for inst in r.get("bias_instances", []):
            total_instances += 1
            cat = inst.get("category", "Unknown")
            occs = len(inst.get("occurrences", []))
            category_counts[cat] += occs
            total_occurrences += occs

    return {
        "total_articles": len(records),
        "total_bias_instances": total_instances,
        "total_occurrences": total_occurrences,
        "sources": dict(sources.most_common()),
        "framework_versions": dict(fw_versions),
        "category_distribution": dict(category_counts.most_common()),
    }


def build_bias_frequency(records: list[dict]) -> dict:
    bias_counts: Counter = Counter()
    bias_names: dict[str, str] = {}
    bias_categories: dict[str, str] = {}
    total_articles = len(records)

    for r in records:
        seen_in_article: set = set()
        for inst in r.get("bias_instances", []):
            bid = inst.get("bias_id", "")
            if bid:
                bias_names[bid] = inst.get("bias_name", bid)
                bias_categories[bid] = inst.get("category", "")
                if bid not in seen_in_article:
                    bias_counts[bid] += 1
                    seen_in_article.add(bid)

    result = {}
    for bid, count in bias_counts.most_common():
        result[bid] = {
            "name": bias_names.get(bid, bid),
            "category": bias_categories.get(bid, ""),
            "article_count": count,
            "prevalence_pct": round(100 * count / total_articles, 1) if total_articles else 0,
        }
    return result


def build_model_provenance(records: list[dict]) -> dict:
    """
    Build a dual-indexed model provenance map:
      by_article: article_id → {eval, judge, triage}
      by_model:   model_id  → {eval_articles: [...], judge_articles: [...], counts}

    Lets you answer:
      "Which model evaluated article X?"   → by_article[article_id]
      "Which articles did Cerebras eval?"  → by_model["cerebras/qwen-3-32b"]["eval_articles"]
    """
    by_article: dict[str, dict] = {}
    by_model: dict[str, dict] = {}

    def _record_model(model_id: str, article_id: str, role: str) -> None:
        if not model_id or not article_id:
            return
        if model_id not in by_model:
            by_model[model_id] = {"eval_articles": [], "judge_articles": [], "triage_articles": [],
                                  "eval_count": 0, "judge_count": 0, "triage_count": 0}
        key = f"{role}_articles"
        if article_id not in by_model[model_id][key]:
            by_model[model_id][key].append(article_id)
            by_model[model_id][f"{role}_count"] += 1

    for r in records:
        aid = r.get("article_id", "")
        models = r.get("models", {})
        eval_m  = models.get("eval")  or r.get("model", "")
        judge_m = models.get("judge", "")
        triage_m = models.get("triage", "")

        by_article[aid] = {
            "eval":   eval_m,
            "judge":  judge_m,
            "triage": triage_m,
            "evaluated_at": r.get("evaluated_at", ""),
        }
        _record_model(eval_m,   aid, "eval")
        _record_model(judge_m,  aid, "judge")
        _record_model(triage_m, aid, "triage")

    # Sort article lists by recency so the most recent evaluation is first
    for m in by_model.values():
        for key in ("eval_articles", "judge_articles", "triage_articles"):
            m[key].sort(
                key=lambda aid: by_article.get(aid, {}).get("evaluated_at", ""),
                reverse=True,
            )

    return {"by_article": by_article, "by_model": by_model}


def main() -> None:
    print("Building index from", PROCESSED_DIR)
    records = load_evaluations()
    print(f"  Found {len(records)} evaluation records")

    index = build_index(records)
    (PROCESSED_DIR / "index.json").write_text(json.dumps(index, indent=2))
    print(f"  index.json ({len(index)} entries)")

    stats = build_stats(records)
    (PROCESSED_DIR / "stats.json").write_text(json.dumps(stats, indent=2))
    print("  stats.json")

    freq = build_bias_frequency(records)
    (PROCESSED_DIR / "bias_frequency.json").write_text(json.dumps(freq, indent=2))
    print(f"  bias_frequency.json ({len(freq)} biases)")

    provenance = build_model_provenance(records)
    (PROCESSED_DIR / "model_provenance.json").write_text(json.dumps(provenance, indent=2))
    models_seen = len(provenance.get("by_model", {}))
    print(f"  model_provenance.json ({models_seen} models, {len(records)} articles)")

    print("\nDone.")


if __name__ == "__main__":
    main()
