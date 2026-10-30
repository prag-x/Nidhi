"""Measure institution-matching accuracy on synthetic noisy references.

    python scripts/evaluate_matcher.py --n 3000

The same evaluation runs when the demo data is loaded, and its result is shown on the Proof page.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.matching.evaluate import evaluate  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=3000)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    with SessionLocal() as db:
        r = evaluate(db, args.n, args.seed)
    if not r["evaluated"]:
        raise SystemExit("No institutions in the database; seed it first.")
    n = r["evaluated"]
    print(f"References evaluated:            {n}")
    print(f"Linked automatically:            {r['auto']} ({100 * r['auto_rate']:.1f}%)")
    print(f"  precision of automatic links:  {100 * r['auto_precision']:.2f}%")
    print(f"Suggested for confirmation:      {r['suggested']} ({100 * r['suggested'] / n:.1f}%), right institution on top "
          f"{100 * r['suggested_top_correct']:.1f}%")
    print(f"Left unmatched:                  {r['unmatched']} ({100 * r['unmatched'] / n:.1f}%)")
    print(f"Right institution ranked first:  {100 * r['top1']:.1f}%")
    print("\nBy kind of noise (auto-correct / auto-wrong / suggested / unmatched):")
    for kind, c in r["by_kind"].items():
        total = sum(c.values())
        sugg = c.get("suggested_correct", 0) + c.get("suggested_wrong", 0)
        print(f"  {kind:<28} n={total:<5} {c.get('auto_correct', 0):>4} / {c.get('auto_wrong', 0):>3} / "
              f"{sugg:>4} / {c.get('unmatched', 0):>3}")


if __name__ == "__main__":
    main()
