"""
Generate a plain-text cross-article bias evaluation report.

Usage:
  python scripts/report.py                    # all evaluated articles
  python scripts/report.py --min-words 300    # skip short articles
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import PROCESSED_DIR, FRAMEWORK_VERSION


def load_results(min_words: int = 0) -> list[dict]:
    results = []
    for p in sorted(PROCESSED_DIR.glob(f"*_{FRAMEWORK_VERSION}.json")):
        d = json.loads(p.read_text())
        wc = len(d.get("article_text", "").split())
        if wc >= min_words:
            d["_word_count"] = wc
            results.append(d)
    return results


def report(min_words: int = 0) -> str:
    results = load_results(min_words)
    if not results:
        return "No evaluated articles found."

    lines = []
    lines.append("=" * 72)
    lines.append("  REFRACT — COGNITIVE BIAS EVALUATION REPORT")
    lines.append(f"  Framework {FRAMEWORK_VERSION} · {len(results)} articles")
    lines.append("=" * 72)

    # ── Cross-article summary ────────────────────────────────────────────────
    all_instances = [inst for r in results for inst in r.get("bias_instances", [])]
    bias_counts: dict[str, int] = {}
    cat_counts: dict[str, int] = {}
    bias_names: dict[str, str] = {}
    article_hit: dict[str, set] = {}

    for r in results:
        aid = r["article_id"]
        for inst in r.get("bias_instances", []):
            bid = inst["bias_id"]
            bias_counts[bid] = bias_counts.get(bid, 0) + len(inst.get("occurrences", []))
            bias_names[bid] = inst["bias_name"]
            cat = inst.get("category", "Unknown")
            cat_counts[cat] = cat_counts.get(cat, 0) + len(inst.get("occurrences", []))
            article_hit.setdefault(bid, set()).add(aid)

    lines.append("")
    lines.append("CROSS-ARTICLE SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Articles evaluated:      {len(results)}")
    lines.append(f"  Total bias instances:    {len(all_instances)}")
    lines.append(f"  Total occurrences:       {sum(bias_counts.values())}")
    lines.append(f"  Distinct bias types:     {len(bias_counts)}")
    lines.append("")

    lines.append("  Occurrences by category:")
    for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
        bar = "█" * (cnt * 20 // max(cat_counts.values()))
        lines.append(f"    {cat:<35} {cnt:>4}  {bar}")

    lines.append("")
    lines.append("  Most prevalent bias types (% of articles):")
    for bid, cnt in sorted(bias_counts.items(), key=lambda x: -x[1]):
        pct = 100 * len(article_hit[bid]) // len(results)
        lines.append(f"    {bias_names[bid]:<35} {cnt:>3} occ  {pct:>3}% of articles")

    # ── Per-article breakdown ────────────────────────────────────────────────
    lines.append("")
    lines.append("=" * 72)
    lines.append("PER-ARTICLE BREAKDOWN")

    for r in results:
        s = r["summary"]
        wc = r["_word_count"]
        title = (r.get("title") or r.get("source_url") or r["article_id"])[:65]
        quality = r.get("judge_result", {}).get("overall_quality", "—")
        lines.append("")
        lines.append(f"  {title}")
        lines.append(f"  {r.get('source_url', '')}")
        lines.append(
            f"  {wc} words · {s['bias_type_count']} bias types · "
            f"{s['total_occurrences']} occurrences · judge: {quality}"
        )
        dominant = ", ".join(s.get("dominant_categories", [])) or "—"
        lines.append(f"  Dominant: {dominant}")

        for inst in r.get("bias_instances", []):
            for occ in inst.get("occurrences", []):
                excerpt = occ.get("excerpt", "")[:80].replace("\n", " ")
                conf = occ.get("confidence", "?")
                lines.append(f"    [{inst['bias_name']:<32} {conf}] \"{excerpt}\"")

        judge_notes = r.get("judge_result", {}).get("notes", "")
        if judge_notes:
            lines.append(f"  Judge: {judge_notes[:120]}")

    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-words", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    text = report(min_words=args.min_words)
    if args.out:
        args.out.write_text(text)
        print(f"Report written to {args.out}")
    else:
        print(text)
