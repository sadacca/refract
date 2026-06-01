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


def load_evaluations() -> list[dict]:
    records = []
    for f in PROCESSED_DIR.glob("*.json"):
        if f.name in ("index.json", "stats.json", "bias_frequency.json"):
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

    print("\nDone.")


if __name__ == "__main__":
    main()
