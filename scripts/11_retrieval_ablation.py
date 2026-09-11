"""Measure what retrieval actually contributes, both arms on one model.

The main agent runs on gpt-oss-120b, whose free-tier daily token allowance was
spent before the ablation could run. Rather than leave the question unanswered,
both arms run here on gpt-oss-20b, which has its own separate allowance.

That trade is deliberate and it costs something specific. The comparison stays
internally valid, because the two arms differ in exactly one thing: whether the
prompt carries retrieved exemplars. Same model, same items, same template, same
temperature. What it cannot claim is a number for gpt-oss-120b. It answers "does
grounding in this brand's history change the replies this model writes", not
"by how much does it change the replies the deployed agent writes".

Running the with-retrieval arm again here rather than reusing the 120b
predictions is the whole point. Comparing 120b-with-retrieval against
20b-without would confound retrieval with model size and produce a number that
looks like an ablation and is not one.

Usage:
  python scripts/11_retrieval_ablation.py --n 35 --live
  python scripts/11_retrieval_ablation.py --n 35 --live --stage judge
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from agent import config as C                                        # noqa: E402
from agent.agent import SYSTEM, apply_policy, build_prompt           # noqa: E402
from agent.data import load_cases                                    # noqa: E402
from agent.judge import judge_reply                                  # noqa: E402
from agent.llm import USAGE, CacheMiss, QuotaExhausted, complete, parse_json  # noqa: E402
from agent.retrieve import ExemplarIndex                             # noqa: E402
from agent.taxonomy import INTENT_NAMES                              # noqa: E402

PRED_DIR = C.REPORT_DIR / "predictions"
JUDGE_DIR = C.REPORT_DIR / "judgements"
ARMS = {"ablation_with_retrieval": True, "ablation_no_retrieval": False}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_one(case: dict, index: ExemplarIndex, use_retrieval: bool,
            model: str, live: bool) -> dict:
    message = case["customer_opening"]
    exemplars = index.search(message, k=C.RETRIEVAL_K) if use_retrieval else []
    raw = parse_json(complete(SYSTEM, build_prompt(message, exemplars),
                              provider="groq", model=model, json_mode=True,
                              temperature=0.0, live=live, allow_failover=False))
    intent = raw.get("intent") if raw.get("intent") in INTENT_NAMES else "other"
    try:
        conf = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        conf = 0.0
    proposed = raw.get("handling") if raw.get("handling") in ("auto", "escalate") else "escalate"
    handling, reason, overrode = apply_policy(intent, conf, proposed,
                                              raw.get("escalation_reason"))
    return {
        "case_id": case["case_id"], "message": message, "intent": intent,
        "confidence": conf, "reply": str(raw.get("reply", "")).strip(),
        "grounded_in": [g for g in (raw.get("grounded_in") or []) if isinstance(g, int)],
        "handling": handling, "escalation_reason": reason,
        "rationale": str(raw.get("rationale", "")).strip(),
        "model_handling": proposed, "policy_overrode": overrode,
        "exemplar_ids": [e.case_id for e in exemplars],
        "slice": case["slice"], "arm_model": model,
        "retrieval": use_retrieval,
    }


def stage_predict(items: list[dict], index: ExemplarIndex, model: str, live: bool) -> None:
    for name, use_retrieval in ARMS.items():
        out = PRED_DIR / f"{name}.jsonl"
        done = {r["case_id"] for r in read_jsonl(out)}
        todo = [c for c in items if c["case_id"] not in done]
        print(f"\n[{name}] {len(items)} items, {len(done)} saved, {len(todo)} to run")
        t0 = time.time()
        with out.open("a", encoding="utf-8") as fh:
            for n, case in enumerate(todo, 1):
                try:
                    rec = run_one(case, index, use_retrieval, model, live)
                except QuotaExhausted as exc:
                    print(f"  STOP after {n - 1}: {exc}")
                    return
                except CacheMiss:
                    print("  stop: not cached and --live not set")
                    return
                except Exception as exc:                       # noqa: BLE001
                    print(f"  error on {case['case_id']}: {str(exc)[:140]}")
                    continue
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                if n % 5 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)}  {n/max(time.time()-t0,1e-9)*60:.1f}/min")


def stage_judge(items: list[dict], index: ExemplarIndex, live: bool) -> None:
    lookup = {c["case_id"]: c for c in items}
    for name in ARMS:
        preds = read_jsonl(PRED_DIR / f"{name}.jsonl")
        out = JUDGE_DIR / f"{name}.jsonl"
        done = {r["case_id"] for r in read_jsonl(out)}
        todo = [p for p in preds if p["case_id"] not in done]
        print(f"\n[{name}] {len(preds)} predictions, {len(done)} judged, {len(todo)} to go")
        with out.open("a", encoding="utf-8") as fh:
            for n, p in enumerate(todo, 1):
                msg = lookup[p["case_id"]]["customer_opening"]
                try:
                    # Both arms are judged against the same retrieved history, so
                    # the no-retrieval arm is held to the same standard rather
                    # than graded on a softer one.
                    v = judge_reply(p["case_id"], msg, p["reply"],
                                    index.search(msg, k=C.RETRIEVAL_K), live=live)
                except QuotaExhausted as exc:
                    print(f"  STOP after {n - 1}: {exc}")
                    return
                except Exception as exc:                       # noqa: BLE001
                    print(f"  error on {p['case_id']}: {str(exc)[:140]}")
                    continue
                fh.write(json.dumps(v.to_dict(), ensure_ascii=False) + "\n")
                fh.flush()
                if n % 10 == 0 or n == len(todo):
                    print(f"  {n}/{len(todo)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--n", type=int, default=35)
    ap.add_argument("--model", default="openai/gpt-oss-20b")
    ap.add_argument("--stage", choices=["predict", "judge"], default="predict")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    golden = [json.loads(line) for line in
              (C.GOLDEN_DIR / f"golden_unlabelled_{args.brand}.jsonl").read_text().splitlines()]
    items = [g for g in golden if g["slice"] == "random"][:args.n]
    index = ExemplarIndex(load_cases(C.PROC_DIR / f"history_{args.brand}.jsonl"))
    print(f"ablation on {args.model}: {len(items)} random-slice items, both arms")

    if args.stage == "predict":
        stage_predict(items, index, args.model, args.live)
    else:
        stage_judge(items, index, args.live)
    print("\nusage:", json.dumps(USAGE.summary(), indent=2))


if __name__ == "__main__":
    main()
