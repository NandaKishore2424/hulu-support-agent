"""Choose the 200 cases that become the hand-labelled golden set.

The set is built in two parts and they are kept separately labelled, because
they answer different questions.

random slice (n=120)
    Uniform random from the holdout split. It preserves the real traffic mix, so
    accuracy measured here is an unbiased estimate of production performance.

boost slice (n=80)
    Rare intents appear a handful of times in 120 messages, which is too few to
    say anything about per-class recall. The boost oversamples them using keyword
    heuristics written by hand. Crucially it does NOT use the agent's own
    classifier to select examples: choosing the test set with the model under
    test would make per-class numbers circular.

Headline metrics are reported on the random slice only. The union is used for
per-class breakdowns, and the report states which is which.

Usage:  python scripts/03_sample_golden.py --brand hulu_support
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                      # noqa: E402
from agent.data import load_cases                  # noqa: E402

# Hand-written probes for the intents that random sampling starves. Each probe is
# a guess about surface form, not a label: whatever it pulls out still gets
# labelled by a human, and probes are allowed to be wrong.
PROBES: dict[str, str] = {
    "ads_experience": r"\bads?\b|advert|commercial|ad-?free|no ads|adblock",
    "plans_billing": r"charg|bill|refund|price|pricing|cost|subscription|cancel|trial|"
                     r"add-?on|plan\b|\$\d|promo|student",
    "unactionable_or_churn": r"cancel(l)?ing|unsubscrib|done with|had enough|worst|"
                             r"sucks|garbage|lawyer|court|refund me|never again|"
                             r"lost a customer",
    "service_outage": r"\b(is|are) (hulu|you|it) down\b|outage|down right now|"
                      r"not working on any|everything else works|server",
    "login_access": r"log ?in|log ?on|sign ?in|password|credential|locked out|log ?out",
    "product_feedback": r"suggestion|feature|please add|wish|would be (nice|great)|"
                        r"bring back|new (interface|layout|design|app)",
    "other": r"^(?=.*\b(thanks|thank you|love|awesome|best)\b)(?!.*\b(but|however|"
             r"issue|problem|error|cant|can't)\b)",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--n-random", type=int, default=120)
    ap.add_argument("--n-boost", type=int, default=80)
    ap.add_argument("--min-chars", type=int, default=25,
                    help="drop stubs that no human could label, e.g. 'same question <URL>'")
    args = ap.parse_args()

    holdout = load_cases(C.PROC_DIR / f"holdout_{args.brand}.jsonl")
    eligible = [c for c in holdout if len(c["customer_opening"]) >= args.min_chars]
    print(f"holdout={len(holdout):,}  eligible={len(eligible):,} "
          f"(dropped {len(holdout) - len(eligible)} short stubs)")

    rng = random.Random(C.RANDOM_SEED)
    pool = eligible[:]
    rng.shuffle(pool)

    random_slice = pool[:args.n_random]
    chosen_ids = {c["case_id"] for c in random_slice}
    remaining = [c for c in pool[args.n_random:] if c["case_id"] not in chosen_ids]

    # Round-robin across probes so no single rare intent dominates the boost.
    per_probe = max(1, args.n_boost // len(PROBES))
    boost: list[dict] = []
    for intent, pattern in PROBES.items():
        rx = re.compile(pattern, re.I)
        hits = [c for c in remaining
                if rx.search(c["customer_opening"]) and c["case_id"] not in chosen_ids]
        take = hits[:per_probe]
        for c in take:
            chosen_ids.add(c["case_id"])
            boost.append({**c, "probe": intent})
        print(f"  probe {intent:24s} matched {len(hits):4d}  took {len(take)}")

    while len(boost) < args.n_boost and remaining:
        c = remaining.pop()
        if c["case_id"] not in chosen_ids:
            chosen_ids.add(c["case_id"])
            boost.append({**c, "probe": "filler"})

    items = ([{**c, "slice": "random", "probe": None} for c in random_slice] +
             [{**c, "slice": "boost"} for c in boost])
    rng.shuffle(items)                       # so the labeller cannot infer the slice

    out = C.GOLDEN_DIR / f"golden_unlabelled_{args.brand}.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for i, c in enumerate(items):
            fh.write(json.dumps({
                "idx": i,
                "case_id": c["case_id"],
                "slice": c["slice"],
                "probe": c.get("probe"),
                "customer_opening": c["customer_opening"],
                "brand_first_reply": c["brand_first_reply"],
                "n_turns": c["n_turns"],
                "created_at": c["created_at"],
            }, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(items)} items to {out}")
    print(f"  random slice: {sum(1 for c in items if c['slice'] == 'random')}")
    print(f"  boost slice:  {sum(1 for c in items if c['slice'] == 'boost')}")


if __name__ == "__main__":
    main()
