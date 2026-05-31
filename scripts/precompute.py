"""
Build all data/precomputed/ artifacts from the current taxonomy.
Run this after any taxonomy.json update before running batch_eval.

Artifacts produced:
  - data/precomputed/taxonomy_index.json
  - data/precomputed/bias_blocks/{bias_id}_{taxonomy_version}.txt
  - data/precomputed/category_triage_blocks/{category_id}_{taxonomy_version}.txt
  - data/precomputed/recall_probe_blocks/{bias_id}_probe_{taxonomy_version}.txt
  - data/precomputed/reframe_blocks/{mode}_{taxonomy_version}.txt
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import PRECOMPUTED_DIR, TAXONOMY_VERSION

TAXONOMY_PATH = ROOT / "bias_index" / "taxonomy.json"


def _slugify(s: str) -> str:
    return s.lower().replace(" ", "-").replace("&", "and").replace("/", "-")


def load_taxonomy() -> dict:
    return json.loads(TAXONOMY_PATH.read_text())


def build_taxonomy_index(taxonomy: dict) -> None:
    index = {}
    for b in taxonomy["biases"]:
        index[b["id"]] = {
            "name": b["name"],
            "category": b["category"],
            "subcategory": b.get("subcategory", ""),
            "status": b.get("status", "provisional"),
            "examples_status": b.get("examples_status", "pending"),
            "severity_signal": b.get("severity_signal", "medium"),
        }
    out = PRECOMPUTED_DIR / "taxonomy_index.json"
    out.write_text(json.dumps(index, indent=2))
    print(f"  taxonomy_index.json ({len(index)} entries)")


def build_bias_blocks(taxonomy: dict) -> None:
    out_dir = PRECOMPUTED_DIR / "bias_blocks"
    out_dir.mkdir(parents=True, exist_ok=True)

    for b in taxonomy["biases"]:
        lines = [
            f"=== {b['name']} (id: {b['id']}) ===",
            f"Definition: {b['definition']}",
            f"Mechanism: {b.get('mechanism', '')}",
            "",
            "Identification criteria:",
        ]
        for c in b.get("identification_criteria", []):
            lines.append(f"  - {c}")
        lines.append("")
        lines.append("Linguistic signals:")
        for s in b.get("linguistic_signals", []):
            lines.append(f"  - {s}")

        ref = b.get("reference_examples", {})
        positives = ref.get("positive", [])
        if positives:
            lines.append("")
            lines.append("Positive examples:")
            for i, ex in enumerate(positives, 1):
                excerpt = ex.get("excerpt", ex) if isinstance(ex, dict) else str(ex)
                lines.append(f"  [{i}] {excerpt}")

        near_misses = ref.get("near_miss", [])
        if near_misses:
            lines.append("")
            lines.append("Near-miss examples (these are NOT instances of this bias):")
            for ex in near_misses:
                if isinstance(ex, dict):
                    lines.append(f"  - {ex.get('excerpt', '')} [Why not: {ex.get('why_not', '')}]")
                else:
                    lines.append(f"  - {ex}")

        contrast = ref.get("contrast")
        if contrast and isinstance(contrast, dict):
            lines.append("")
            lines.append(
                f"Contrast (most confused with — {contrast.get('bias', '')}):\n"
                f"  {contrast.get('excerpt', '')}\n"
                f"  Distinction: {contrast.get('distinction', '')}"
            )

        text = "\n".join(lines)
        fname = f"{b['id']}_{TAXONOMY_VERSION}.txt"
        (out_dir / fname).write_text(text)

    print(f"  bias_blocks/ ({len(taxonomy['biases'])} files)")


def build_category_triage_blocks(taxonomy: dict) -> None:
    out_dir = PRECOMPUTED_DIR / "category_triage_blocks"
    out_dir.mkdir(parents=True, exist_ok=True)

    categories: dict[str, list] = {}
    for b in taxonomy["biases"]:
        cat = b["category"]
        categories.setdefault(cat, []).append(b)

    for category, biases in categories.items():
        slug = _slugify(category)
        lines = [
            f"Category: {category}",
            f"Biases in this category ({len(biases)}):",
        ]
        for b in biases:
            lines.append(f"  - {b['name']}: {b['definition'][:120]}...")
        text = "\n".join(lines)
        fname = f"{slug}_{TAXONOMY_VERSION}.txt"
        (out_dir / fname).write_text(text)

    print(f"  category_triage_blocks/ ({len(categories)} files)")


def build_recall_probe_blocks(taxonomy: dict) -> None:
    out_dir = PRECOMPUTED_DIR / "recall_probe_blocks"
    out_dir.mkdir(parents=True, exist_ok=True)

    for b in taxonomy["biases"]:
        criteria = "\n".join(f"  - {c}" for c in b.get("identification_criteria", []))
        text = (
            f"Bias to probe: {b['name']}\n"
            f"Definition: {b['definition']}\n"
            f"Identification criteria:\n{criteria}\n"
        )
        fname = f"{b['id']}_probe_{TAXONOMY_VERSION}.txt"
        (out_dir / fname).write_text(text)

    print(f"  recall_probe_blocks/ ({len(taxonomy['biases'])} files)")


def build_reframe_blocks(taxonomy: dict) -> None:
    out_dir = PRECOMPUTED_DIR / "reframe_blocks"
    out_dir.mkdir(parents=True, exist_ok=True)

    for mode in ["neutralize", "steelman", "annotated"]:
        lines = [f"Reframe mode: {mode}", ""]
        for b in taxonomy["biases"]:
            strategy = b.get("reframing_strategy", "")
            example = b.get("reframing_example", "")
            if strategy:
                lines.append(f"[{b['name']}]")
                lines.append(f"Strategy: {strategy}")
                if example:
                    lines.append(f"Example: {example}")
                lines.append("")
        fname = f"{mode}_{TAXONOMY_VERSION}.txt"
        (out_dir / fname).write_text("\n".join(lines))

    print("  reframe_blocks/ (3 files)")


def main() -> None:
    print(f"Building precomputed artifacts for taxonomy {TAXONOMY_VERSION}...")
    taxonomy = load_taxonomy()
    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)

    build_taxonomy_index(taxonomy)
    build_bias_blocks(taxonomy)
    build_category_triage_blocks(taxonomy)
    build_recall_probe_blocks(taxonomy)
    build_reframe_blocks(taxonomy)

    print(f"\nDone. All artifacts written to {PRECOMPUTED_DIR}")


if __name__ == "__main__":
    main()
