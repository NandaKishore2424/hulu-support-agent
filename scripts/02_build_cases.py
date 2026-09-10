"""Reconstruct threads for one brand and split them chronologically.

The split is by time, not at random. A random split lets the agent retrieve a
near-duplicate of the very conversation being scored, because the same complaint
recurs daily, and that inflates every reply-quality number. Retrieval may only
see conversations that happened before the evaluation window.

Usage:  python scripts/02_build_cases.py --brand hulu_support
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                                    # noqa: E402
from agent.data import (build_threads, load_raw, save_cases,      # noqa: E402
                        scope_to_brand, to_cases)

TW_FMT = "%a %b %d %H:%M:%S %z %Y"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--holdout-frac", type=float, default=0.25,
                    help="most recent share of cases reserved for evaluation")
    args = ap.parse_args()

    print("loading raw tweets ...")
    df = load_raw()
    print(f"  {len(df):,} tweets")

    print(f"scoping to threads involving {args.brand} ...")
    sub = scope_to_brand(df, args.brand)
    print(f"  {len(sub):,} tweets in {sub['root_id'].nunique():,} threads")

    print("rebuilding threads ...")
    threads = build_threads(sub)
    cases = to_cases(threads, brand=args.brand)
    print(f"  {len(cases):,} cases with a customer opening and a brand reply")

    ts = pd.to_datetime([c.created_at for c in cases], format=TW_FMT, utc=True)
    order = sorted(range(len(cases)), key=lambda i: ts[i])
    cases = [cases[i] for i in order]
    ts = ts[order]
    cut = int(len(cases) * (1 - args.holdout_frac))

    history, holdout = cases[:cut], cases[cut:]
    save_cases(history, C.PROC_DIR / f"history_{args.brand}.jsonl")
    save_cases(holdout, C.PROC_DIR / f"holdout_{args.brand}.jsonl")

    meta = {
        "brand": args.brand,
        "n_cases": len(cases),
        "n_history": len(history),
        "n_holdout": len(holdout),
        "date_min": str(ts.min()), "date_max": str(ts.max()),
        "split_boundary": str(ts[cut]),
        "median_turns": float(pd.Series([c.n_turns for c in cases]).median()),
        "multi_turn_share": float(pd.Series([c.n_turns > 2 for c in cases]).mean()),
    }
    (C.PROC_DIR / f"split_meta_{args.brand}.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
