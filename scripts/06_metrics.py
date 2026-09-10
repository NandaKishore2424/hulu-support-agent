"""Compute every number in the report from saved predictions. No API key needed.

This is the script the README points at for reproduction. It reads the golden
labels and the prediction files on disk and prints the tables, so a reader can
check the headline claims in seconds without touching a provider.

Usage:  python scripts/06_metrics.py [--brand hulu_support]
"""
from __future__ import annotations

import argparse
import json
import statistics as stats
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                                    # noqa: E402
from agent.evaluate import (bootstrap_ci, accuracy, macro_f1,    # noqa: E402
                            per_class, token_f1, top_confusions, triage)
from agent.judge import DIMENSIONS                               # noqa: E402

PRED_DIR = C.REPORT_DIR / "predictions"
JUDGE_DIR = C.REPORT_DIR / "judgements"
SYSTEM_ORDER = ["majority", "keyword_knn", "no_retrieval", "agent"]


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def load_gold(brand: str, labels_file: str) -> dict[str, dict]:
    """Merge the human labels with the slice metadata the labeller never saw."""
    meta = {r["case_id"]: r for r in read_jsonl(
        C.GOLDEN_DIR / f"golden_unlabelled_{brand}.jsonl")}
    labels_path = C.GOLDEN_DIR / labels_file
    if not labels_path.exists():
        sys.exit(f"no labels yet at {labels_path}\n"
                 f"run scripts/label.sh, label the set, export, and save it there.")
    gold = {}
    rows = read_jsonl(labels_path)
    if any(r.get("source") == "smoke_not_golden" for r in rows):
        print("!" * 78)
        print("SMOKE LABELS. Every number below is meaningless by construction and")
        print("must not be reported. Re-run with the hand-labelled golden file.")
        print("!" * 78 + "\n")
    for row in rows:
        cid = row.get("case_id")
        if not cid or not row.get("intent") or not row.get("handling"):
            continue
        m = meta.get(cid, {})
        gold[cid] = {**row,
                     "slice": m.get("slice", "unknown"),
                     "customer_opening": m.get("customer_opening", ""),
                     "brand_first_reply": m.get("brand_first_reply", "")}
    return gold


def fmt_pct(x: float) -> str:
    return f"{100 * x:5.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--labels", default="golden_labels.jsonl",
                    help="label file inside data/golden; use golden_labels_SMOKE.jsonl "
                         "to exercise the harness before real labels exist")
    args = ap.parse_args()

    gold = load_gold(args.brand, args.labels)
    rnd = {k: v for k, v in gold.items() if v["slice"] == "random"}
    print(f"golden labelled: {len(gold)}  (random slice {len(rnd)}, "
          f"boost {len(gold) - len(rnd)})")
    peeked = sum(1 for v in gold.values() if v.get("peeked"))
    ambig = sum(1 for v in gold.values() if v.get("ambiguous"))
    print(f"labeller revealed the real reply on {peeked} items; "
          f"flagged {ambig} as ambiguous")

    gold_intents = [v["intent"] for v in gold.values()]
    dist = {k: gold_intents.count(k) for k in sorted(set(gold_intents))}
    print("\nlabel distribution (all 200):")
    for k, v in sorted(dist.items(), key=lambda kv: -kv[1]):
        print(f"  {k:24s} {v:4d}  {fmt_pct(v/len(gold_intents))}")
    gold_handling = [v["handling"] for v in gold.values()]
    print(f"  escalate share: {fmt_pct(gold_handling.count('escalate')/len(gold_handling))}")

    summary: dict[str, dict] = {}
    print("\n" + "=" * 96)
    print(f"{'system':14s} {'slice':7s} {'n':>4s} {'acc':>7s} {'acc 95% CI':>16s} "
          f"{'macroF1':>8s} {'esc P':>7s} {'esc R':>7s} {'missed':>7s} {'over':>6s} {'auto%':>7s}")
    print("=" * 96)

    for name in SYSTEM_ORDER:
        rows = read_jsonl(PRED_DIR / f"{name}.jsonl")
        preds = {r["case_id"]: r for r in rows}
        if not preds:
            continue
        if len(rows) != len(preds):
            sys.exit(f"{name}.jsonl has {len(rows) - len(preds)} duplicate case_ids. "
                     "Run scripts/12_dedupe_predictions.py --report --apply first, "
                     "so the tables are not silently built from whichever copy "
                     "happened to be written last.")
        for slice_name, gset in (("random", rnd), ("all", gold)):
            ids = [cid for cid in gset if cid in preds]
            if not ids:
                continue
            yt = [gset[c]["intent"] for c in ids]
            yp = [preds[c]["intent"] for c in ids]
            ht = [gset[c]["handling"] for c in ids]
            hp = [preds[c]["handling"] for c in ids]
            acc = accuracy(yt, yp)
            lo, hi = bootstrap_ci([1.0 if a == b else 0.0 for a, b in zip(yt, yp)])
            t = triage(ht, hp)
            print(f"{name:14s} {slice_name:7s} {len(ids):4d} {fmt_pct(acc)} "
                  f"[{fmt_pct(lo)},{fmt_pct(hi)}] {macro_f1(yt, yp):8.3f} "
                  f"{fmt_pct(t.precision)} {fmt_pct(t.recall)} "
                  f"{t.missed_escalations:7d} {t.over_escalations:6d} {fmt_pct(t.automation_rate)}")
            if slice_name == "random":
                summary.setdefault(name, {})["intent"] = {
                    "n": len(ids), "accuracy": acc, "ci": [lo, hi],
                    "macro_f1": macro_f1(yt, yp)}
                summary[name]["triage"] = t.__dict__

    print("\n--- per-class intent, agent, all 200 items (boost slice included) ---")
    preds = {r["case_id"]: r for r in read_jsonl(PRED_DIR / "agent.jsonl")}
    if preds:
        ids = [c for c in gold if c in preds]
        yt = [gold[c]["intent"] for c in ids]
        yp = [preds[c]["intent"] for c in ids]
        print(f"{'intent':24s} {'n':>4s} {'prec':>7s} {'rec':>7s} {'f1':>6s}")
        for cm in sorted(per_class(yt, yp), key=lambda c: -c.support):
            if cm.support:
                print(f"{cm.label:24s} {cm.support:4d} {fmt_pct(cm.precision)} "
                      f"{fmt_pct(cm.recall)} {cm.f1:6.3f}")
        print("\ntop confusions (true -> predicted):")
        for t_, p_, n in top_confusions(yt, yp, k=8):
            print(f"  {t_:24s} -> {p_:24s} {n:3d}")

    print("\n--- reply quality, judged by " + C.JUDGE_MODEL + " ---")
    print(f"{'system':14s} {'n':>4s} " + " ".join(f"{d:>11s}" for d in DIMENSIONS) +
          f" {'mean':>7s} {'usable':>7s} {'tokF1':>7s}")
    for name in SYSTEM_ORDER:
        verdicts = read_jsonl(JUDGE_DIR / f"{name}.jsonl")
        models = {v.get("judge_model", "unknown") for v in verdicts}
        if len(models) > 1:
            sys.exit(f"{name} was judged by more than one model {sorted(models)}; "
                     "scores from different judges are not comparable. "
                     "delete reports/judgements and re-run the judge stage.")
        if not verdicts:
            continue
        preds = {r["case_id"]: r for r in read_jsonl(PRED_DIR / f"{name}.jsonl")}
        row = [f"{name:14s}", f"{len(verdicts):4d}"]
        for d in DIMENSIONS:
            vals = [v[d] for v in verdicts]
            lo, hi = bootstrap_ci([float(x) for x in vals])
            row.append(f"{stats.mean(vals):4.2f}±{(hi-lo)/2:4.2f}")
        means = [v["mean_quality"] for v in verdicts]
        usable = [v["usable"] for v in verdicts]
        tf = [token_f1(preds[v["case_id"]]["reply"], gold[v["case_id"]]["brand_first_reply"])
              for v in verdicts if v["case_id"] in preds and v["case_id"] in gold]
        row += [f"{stats.mean(means):7.2f}", fmt_pct(stats.mean(usable)),
                f"{stats.mean(tf):7.3f}" if tf else "      -"]
        print(" ".join(row))
        summary.setdefault(name, {})["quality"] = {
            "n": len(verdicts),
            **{d: stats.mean([v[d] for v in verdicts]) for d in DIMENSIONS},
            "mean_quality": stats.mean(means), "usable_rate": stats.mean(usable),
            "token_f1_vs_real_reply": stats.mean(tf) if tf else None}

    out = C.REPORT_DIR / "metrics.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
