"""Collapse duplicate predictions, and report what the duplicates revealed.

Two prediction runs briefly overlapped, so 31 golden cases were generated twice.
Each process computed its "already done" set before the other had written, so
both called the API and both appended. The cache did not merge them because both
missed it at the same moment.

The accident is useful. Those 31 cases are independent repeat samples of the same
prompt at temperature zero, which is the only run-to-run variance estimate in the
project. `scripts/12_dedupe_predictions.py --report` prints it before collapsing.

Deduplication keeps the first occurrence in file order, which is deterministic and
independent of which result looks better.

Usage:
  python scripts/12_dedupe_predictions.py --report      # inspect only
  python scripts/12_dedupe_predictions.py --apply       # rewrite the files
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                       # noqa: E402

PRED_DIR = C.REPORT_DIR / "predictions"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def variance_report(rows: list[dict]) -> dict | None:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["case_id"]].append(r)
    repeats = [rs for rs in by.values() if len(rs) >= 2]
    if not repeats:
        return None
    n = len(repeats)
    def stable(field: str) -> float:
        return sum(1 for rs in repeats if len({json.dumps(r[field]) for r in rs}) == 1) / n
    return {"n_repeated": n, "intent": stable("intent"), "handling": stable("handling"),
            "confidence": stable("confidence"), "reply": stable("reply")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="rewrite files without duplicates")
    ap.add_argument("--report", action="store_true", help="print the variance estimate")
    args = ap.parse_args()

    for path in sorted(PRED_DIR.glob("*.jsonl")):
        rows = read_jsonl(path)
        seen, kept = set(), []
        for r in rows:
            if r["case_id"] in seen:
                continue
            seen.add(r["case_id"])
            kept.append(r)
        dupes = len(rows) - len(kept)
        print(f"{path.name:32s} rows={len(rows):4d} unique={len(kept):4d} dropped={dupes:3d}")
        if args.report and dupes:
            v = variance_report(rows)
            if v:
                print(f"    repeat samples at temperature 0, n={v['n_repeated']}")
                for k in ("intent", "handling", "confidence", "reply"):
                    print(f"      identical {k:11s} {v[k]:.0%}")
        if args.apply and dupes:
            path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in kept) + "\n",
                            encoding="utf-8")
            print(f"    rewrote {path.name} with {len(kept)} rows")


if __name__ == "__main__":
    main()
