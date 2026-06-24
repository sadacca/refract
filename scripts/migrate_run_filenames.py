"""
Migrate data/processed/ evaluation files to the current run-filename scheme:

    {article_id}_{framework_version}_{triage}_{eval}_{judge}_{mode}.json

Earlier schemes omitted the triage model and/or the mode, so runs that differed
only in triage model or mode silently overwrote each other. This script brings
every existing result file up to the compliant name.

For each file:
  - If the JSON content records all three models (triage/eval/judge) and a mode,
    the compliant name is reconstructed and the file is renamed (content already
    holds the right data — only the filename was stale).
  - If the content cannot identify the triage or judge model (legacy records that
    predate the `models` block), the run is not reconstructable and is deleted so
    it gets re-run under the new scheme.

Runs dry by default; pass --apply to actually rename/delete. Index artifacts
(index.json, stats.json, ...) are left untouched — rerun scripts/build_index.py
afterwards to refresh them.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config import PROCESSED_DIR, model_abbrev  # noqa: E402

ARTIFACTS = {"index.json", "stats.json", "bias_frequency.json", "model_provenance.json"}


def _compliant_name(r: dict) -> str | None:
    """Return the compliant filename for a result dict, or None if it can't be
    reconstructed (missing triage/eval/judge)."""
    article_id = r.get("article_id")
    fw = r.get("framework_version")
    models = r.get("models") or {}
    triage = models.get("triage")
    eval_m = models.get("eval") or r.get("model")
    judge = models.get("judge")
    mode = r.get("mode") or "deep"
    if not (article_id and fw and triage and eval_m and judge):
        return None
    sig = f"{model_abbrev(triage)}_{model_abbrev(eval_m)}_{model_abbrev(judge)}"
    return f"{article_id}_{fw}_{sig}_{mode}.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="Actually rename/delete (default: dry run)")
    args = ap.parse_args()

    renamed = deleted = compliant = collisions = 0

    for p in sorted(PROCESSED_DIR.glob("*.json")):
        if p.name in ARTIFACTS:
            continue
        try:
            r = json.loads(p.read_text())
        except Exception as e:
            print(f"[skip ] {p.name}: unreadable JSON ({e})")
            continue

        target_name = _compliant_name(r)

        if target_name is None:
            print(f"[DELETE] {p.name} — triage/judge unrecoverable, pending re-run")
            deleted += 1
            if args.apply:
                p.unlink()
            continue

        if target_name == p.name:
            compliant += 1
            continue

        target = PROCESSED_DIR / target_name
        if target.exists() and target != p:
            # A compliant file already exists for this exact run — keep the newer,
            # drop the older. Avoids two names for one (article, models, mode).
            keep_new = p.stat().st_mtime > target.stat().st_mtime
            loser = target if keep_new else p
            winner = p if keep_new else target
            print(f"[COLLIDE] {p.name} ↔ {target_name}: keeping newer {winner.name}, dropping {loser.name}")
            collisions += 1
            if args.apply:
                loser.unlink()
                if keep_new:
                    p.rename(target)
            continue

        print(f"[RENAME] {p.name} → {target_name}")
        renamed += 1
        if args.apply:
            p.rename(target)

    verb = "applied" if args.apply else "dry-run"
    print(
        f"\n{verb}: {renamed} to rename, {deleted} to delete, {collisions} collisions, "
        f"{compliant} already compliant."
    )
    if not args.apply:
        print("Re-run with --apply to make changes, then run scripts/build_index.py.")


if __name__ == "__main__":
    main()
