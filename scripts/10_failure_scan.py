"""Scan generated replies for defects that need no gold labels to detect.

Some failures are properties of the reply text alone: a leaked placeholder, a
tweet over the character limit, someone else's name copied out of a retrieved
example, an empathy opener on a message with nothing to be sorry about. These are
countable now, they are the concrete evidence the failure analysis needs, and
several of them are unpostable regardless of how good the advice is.

Every check is deliberately mechanical and conservative. A pattern that would
need judgement to confirm is reported as a candidate for reading, not as a
confirmed count.

Usage:  python scripts/10_failure_scan.py [--system agent] [--examples 3]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from agent import config as C                        # noqa: E402
from agent.data import load_cases                    # noqa: E402

PRED_DIR = C.REPORT_DIR / "predictions"
TWEET_LIMIT = 280

# Intents where nothing bad has happened to the customer, so an apology opener is
# tonally wrong rather than merely warm.
NEUTRAL_INTENTS = {"content_availability", "product_feedback", "how_to_question"}
EMPATHY_OPENER = re.compile(
    r"^\s*(?:@user\s+)?(?:oh no|uh oh|sorry to hear|so sorry|we'?re sorry|"
    r"apologies|sorry (?:about|for))", re.I)
PLACEHOLDER = re.compile(r"<URL>|<url>|\[link\]|\{.*?\}|https?://example")
# A capitalised first name after a greeting or comma is how Hulu addresses people.
NAME_ADDRESS = re.compile(r"(?:hey|hi|hello|thanks|thank you|sorry|apologies)[ ,]+"
                          r"([A-Z][a-z]{2,12})\b")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="agent")
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args()

    preds = read_jsonl(PRED_DIR / f"{args.system}.jsonl")
    if not preds:
        sys.exit(f"no predictions for {args.system}")
    history = {c["case_id"]: c for c in load_cases(C.PROC_DIR / "history_hulu_support.jsonl")}

    checks: dict[str, list[dict]] = {k: [] for k in (
        "leaked_placeholder", "over_tweet_limit", "empty_reply",
        "empathy_opener_on_neutral_intent", "borrowed_name_from_exemplar",
        "no_exemplar_fit", "policy_overrode_model", "missing_at_user_prefix")}

    for p in preds:
        reply = p.get("reply", "") or ""
        if not reply.strip():
            checks["empty_reply"].append(p)
            continue
        if PLACEHOLDER.search(reply):
            checks["leaked_placeholder"].append(p)
        if len(reply) > TWEET_LIMIT:
            checks["over_tweet_limit"].append(p)
        if p.get("intent") in NEUTRAL_INTENTS and EMPATHY_OPENER.match(reply):
            checks["empathy_opener_on_neutral_intent"].append(p)
        if not reply.lstrip().startswith("@user"):
            checks["missing_at_user_prefix"].append(p)
        if not p.get("grounded_in"):
            checks["no_exemplar_fit"].append(p)
        if p.get("policy_overrode"):
            checks["policy_overrode_model"].append(p)

        # A name in the reply that appears in a retrieved exemplar but not in the
        # customer's own message is a name lifted from someone else's case.
        found = {m.group(1) for m in NAME_ADDRESS.finditer(reply)}
        if found:
            exemplar_text = " ".join(
                history.get(eid, {}).get("brand_first_reply", "")
                for eid in p.get("exemplar_ids", []))
            own = p.get("message", "")
            lifted = {n for n in found if n in exemplar_text and n not in own}
            if lifted:
                checks["borrowed_name_from_exemplar"].append({**p, "_names": sorted(lifted)})

    n = len(preds)
    print(f"scanned {n} replies from {args.system}\n")
    print(f"{'check':38s} {'count':>6s} {'rate':>7s}")
    print("-" * 54)
    for name, rows in sorted(checks.items(), key=lambda kv: -len(kv[1])):
        print(f"{name:38s} {len(rows):6d} {100*len(rows)/n:6.1f}%")

    unpostable = {p["case_id"] for k in ("leaked_placeholder", "over_tweet_limit",
                                         "empty_reply", "borrowed_name_from_exemplar")
                  for p in checks[k]}
    print(f"\nreplies unpostable as written, any mechanical reason: "
          f"{len(unpostable)} of {n} ({100*len(unpostable)/n:.1f}%)")

    print("\n" + "=" * 74)
    print("EXAMPLES")
    print("=" * 74)
    for name, rows in sorted(checks.items(), key=lambda kv: -len(kv[1])):
        if not rows:
            continue
        print(f"\n--- {name} ({len(rows)}) ---")
        for p in rows[:args.examples]:
            extra = f"  names={p['_names']}" if "_names" in p else ""
            print(f"  customer: {p['message'][:110]}")
            print(f"  intent={p['intent']} handling={p['handling']}{extra}")
            print(f"  reply:    {p['reply'][:160]}")
            print()

    intents = Counter(p["intent"] for p in preds)
    print("predicted intent mix:", dict(intents.most_common()))
    out = C.REPORT_DIR / f"failure_scan_{args.system}.json"
    out.write_text(json.dumps(
        {k: [p["case_id"] for p in v] for k, v in checks.items()} |
        {"n": n, "unpostable": sorted(unpostable)}, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
