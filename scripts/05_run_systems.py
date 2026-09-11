"""Run every system over the golden set and save predictions, then judge replies.

Split into two stages because they hit different providers with different limits,
and because the judging stage should be re-runnable without regenerating replies.

Everything routes through the disk cache, so an interrupted run resumes where it
stopped and a finished run costs nothing to repeat. That is what lets the README
promise a reproduction in minutes rather than hours.

Usage:
  python scripts/05_run_systems.py --stage predict --live
  python scripts/05_run_systems.py --stage judge --live --judge-n 100
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import agent as A                                          # noqa: E402
from agent import config as C                                         # noqa: E402
from agent.baselines import (KeywordKnnBaseline, MajorityBaseline,    # noqa: E402
                             NoRetrievalAblation)
from agent.data import load_cases                                     # noqa: E402
from agent.judge import judge_reply                                   # noqa: E402
from agent.llm import USAGE, CacheMiss, QuotaExhausted               # noqa: E402
from agent.retrieve import ExemplarIndex                              # noqa: E402

PRED_DIR = C.REPORT_DIR / "predictions"
JUDGE_DIR = C.REPORT_DIR / "judgements"
PRED_DIR.mkdir(parents=True, exist_ok=True)
JUDGE_DIR.mkdir(parents=True, exist_ok=True)


def load_golden(brand: str) -> list[dict]:
    path = C.GOLDEN_DIR / f"golden_unlabelled_{brand}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def predict(brand: str, live: bool, only: list[str] | None,
            limit: int | None = None, ablation_n: int = 40) -> None:
    items = load_golden(brand)
    hist = load_cases(C.PROC_DIR / f"history_{brand}.jsonl")
    index = ExemplarIndex(hist)
    print(f"golden={len(items)}  exemplar pool={len(index):,}")

    majority = MajorityBaseline()
    knn = KeywordKnnBaseline(index)
    ablation = NoRetrievalAblation()

    # The ablation only needs the random slice: it exists to isolate retrieval's
    # contribution, not to produce a headline number, and Groq's daily quota is
    # better spent on the agent itself.
    plans = {
        "majority":     (items, lambda c: majority.run(c)),
        "keyword_knn":  (items, lambda c: knn.run(c)),
        "agent":        (items, lambda c: A.run(c, index, live=live)),
        "no_retrieval": ([i for i in items if i["slice"] == "random"][:ablation_n],
                         lambda c: ablation.run(c, live=live)),
    }
    for name, (subset, fn) in plans.items():
        if only and name not in only:
            continue
        out_path = PRED_DIR / f"{name}.jsonl"
        done = set()
        if out_path.exists():
            done = {json.loads(line)["case_id"] for line in out_path.read_text().splitlines()}
        todo = [c for c in subset if c["case_id"] not in done]
        if limit:
            todo = todo[:limit]
        print(f"\n[{name}] {len(subset)} items, {len(done)} already saved, {len(todo)} to run")
        t0 = time.time()
        with out_path.open("a", encoding="utf-8") as fh:
            for n, case in enumerate(todo, 1):
                try:
                    out = fn(case)
                except CacheMiss:
                    print(f"  stop: cache miss at item {n} and --live not set")
                    break
                except QuotaExhausted as exc:
                    print(f"\n  STOP after {n - 1} items: {exc}")
                    return
                except Exception as exc:                       # noqa: BLE001
                    print(f"  error on {case['case_id']}: {str(exc)[:160]}")
                    continue
                rec = out.to_dict()
                rec["slice"] = case["slice"]
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                if n % 10 == 0 or n == len(todo):
                    rate = n / max(time.time() - t0, 1e-9) * 60
                    print(f"  {n}/{len(todo)}  {rate:.1f}/min  usage={USAGE.summary()}")


def judge(brand: str, live: bool, judge_n: int, only: list[str] | None,
          limit: int | None = None) -> None:
    hist = load_cases(C.PROC_DIR / f"history_{brand}.jsonl")
    index = ExemplarIndex(hist)
    items = {c["case_id"]: c for c in load_golden(brand)}

    # One judging subset shared by every system, so the comparison is like for
    # like. Taken from the random slice in file order, which the sampler already
    # shuffled with a fixed seed.
    subset = [c["case_id"] for c in load_golden(brand) if c["slice"] == "random"][:judge_n]
    subset_set = set(subset)
    print(f"judging {len(subset)} cases per system with {C.JUDGE_MODEL}")

    for pred_path in sorted(PRED_DIR.glob("*.jsonl")):
        name = pred_path.stem
        if only and name not in only:
            continue
        preds = {}
        for line in pred_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["case_id"] in subset_set:
                preds[r["case_id"]] = r
        out_path = JUDGE_DIR / f"{name}.jsonl"
        done = set()
        if out_path.exists():
            done = {json.loads(line)["case_id"] for line in out_path.read_text().splitlines()}
        todo = [cid for cid in subset if cid in preds and cid not in done]
        if limit:
            todo = todo[:limit]
        print(f"\n[{name}] {len(preds)} in subset, {len(done)} judged, {len(todo)} to go")
        t0 = time.time()
        with out_path.open("a", encoding="utf-8") as fh:
            for n, cid in enumerate(todo, 1):
                rec = preds[cid]
                msg = items[cid]["customer_opening"]
                try:
                    verdict = judge_reply(cid, msg, rec["reply"],
                                          index.search(msg, k=C.RETRIEVAL_K), live=live)
                except CacheMiss:
                    print(f"  stop: cache miss at item {n} and --live not set")
                    break
                except QuotaExhausted as exc:
                    print(f"\n  STOP after {n - 1} items: {exc}")
                    return
                except Exception as exc:                        # noqa: BLE001
                    print(f"  error on {cid}: {str(exc)[:160]}")
                    continue
                fh.write(json.dumps(verdict.to_dict(), ensure_ascii=False) + "\n")
                fh.flush()
                if n % 10 == 0 or n == len(todo):
                    rate = n / max(time.time() - t0, 1e-9) * 60
                    print(f"  {n}/{len(todo)}  {rate:.1f}/min")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--stage", choices=["predict", "judge"], required=True)
    ap.add_argument("--live", action="store_true",
                    help="allow real API calls; without it only cached prompts resolve")
    ap.add_argument("--judge-n", type=int, default=100)
    ap.add_argument("--ablation-n", type=int, default=40,
                    help="random-slice items for the no-retrieval ablation; it only "
                         "has to show whether retrieval helps, and it is the first "
                         "thing to shrink when a daily token budget binds")
    ap.add_argument("--limit", type=int, default=None,
                    help="process at most this many pending items per system, then "
                         "exit cleanly; lets a long run proceed in bounded chunks")
    ap.add_argument("--only", nargs="*", default=None,
                    help="restrict to named systems, e.g. --only agent")
    args = ap.parse_args()

    if args.stage == "predict":
        predict(args.brand, args.live, args.only, args.limit, args.ablation_n)
    else:
        judge(args.brand, args.live, args.judge_n, args.only, args.limit)
    print("\nfinal usage:", json.dumps(USAGE.summary(), indent=2))


if __name__ == "__main__":
    main()
