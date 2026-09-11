"""Label the golden set with a model, because the human pass was not completed.

READ THIS BEFORE TRUSTING ANY NUMBER COMPUTED FROM THESE LABELS.

The evaluation set was meant to be hand-labelled. It was not. These labels come
from a language model, and that changes what every downstream number means.

  Intent "accuracy" is no longer accuracy. It is agreement between two models,
  the agent under test and the model that produced the reference. Two models can
  agree confidently and both be wrong, and nothing here would detect it.

  The escalation numbers have the same problem, with an extra twist: the policy
  rules the agent applies and the policy description this labeller was shown are
  the same text, so a shared misreading cannot show up as disagreement.

Three choices limit the damage as far as they can.

  A different model family. The agent writes on gpt-oss via Groq; the reference
  labels come from Google's gemini-3.6-flash, which is also deliberately not the
  model used as the reply judge. Using the agent's own model would have produced
  near-perfect agreement that measured nothing at all.

  The same instructions a person would have seen. The labeller is given the
  taxonomy, the boundary rules and the escalation definitions verbatim from
  taxonomy.py, which is the text the labelling page displays. Nothing is
  simplified for the model.

  An explicit "ambiguous" option and no forced confidence. The model may flag an
  item rather than guess, exactly as a human labeller could, so genuine
  ambiguity is recorded instead of resolved by coin flip.

Every row is stamped source="machine" and carries the model that produced it.
scripts/14_make_spotcheck.py builds a short human validation pass over a random
subset; if that is completed, the report can state how far these labels agree
with a person, which is the only thing that would make them worth anything.

Usage:  python scripts/13_machine_labels.py --live
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                                   # noqa: E402
from agent.llm import USAGE, QuotaExhausted, complete, parse_json  # noqa: E402
from agent.taxonomy import (ESCALATION_REASONS, INTENT_NAMES,   # noqa: E402
                            escalation_prompt_block, taxonomy_prompt_block)

# Not the agent's model and not the judge's model, on purpose.
#
# gemini-3.6-flash was the first choice and ran out of its free-tier daily
# allowance after a dozen calls. Those labels were discarded rather than mixed
# in: a reference set assembled from two different models is not a consistent
# standard, and the same rule was applied to the reply judge earlier for the same
# reason.
LABELLER_MODEL = "gemini-3.1-flash-lite"

SYSTEM = """You are annotating a customer-support evaluation set. You are not
answering the customer and not writing a reply. You decide what the message is
about and who should handle it, following the given definitions exactly.

Where a boundary rule is stated, it overrides your own intuition. Where a message
genuinely fits two intents equally, say so rather than picking one. You answer
only in JSON."""

TEMPLATE = """Annotate this customer message.

INTENT LABELS
{taxonomy}

ESCALATION REASONS
{escalations}

HANDLING
  "auto"     a correct public reply exists that needs no access to the customer's
             account and commits the brand to nothing it cannot keep
  "escalate" a person is required: the answer needs account or payment records,
             the customer is threatening to leave or to take legal action, there
             is abuse or serious distress, an accessibility fault, a broad
             outage whose messaging must be centrally controlled, or there is
             nothing actionable in the message at all

CUSTOMER MESSAGE
{message}

Return JSON with exactly these keys:
  "intent": one of {intent_list}
  "handling": "auto" or "escalate"
  "reason": one of {reason_list} when handling is "escalate", otherwise null
  "ambiguous": true if this message fits two intents equally well, else false
  "note": at most 12 words on why, or "" if obvious
"""


def build(message: str) -> str:
    return TEMPLATE.format(
        taxonomy=taxonomy_prompt_block(), escalations=escalation_prompt_block(),
        message=message, intent_list=", ".join(INTENT_NAMES),
        reason_list=", ".join(ESCALATION_REASONS))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    src = C.GOLDEN_DIR / f"golden_unlabelled_{args.brand}.jsonl"
    items = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    out = C.GOLDEN_DIR / "golden_labels.jsonl"

    done: dict[str, dict] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("intent"):
                    done[r["case_id"]] = r

    todo = [c for c in items if c["case_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(items)} golden items, {len(done)} already labelled, {len(todo)} to go")
    print(f"labeller: {LABELLER_MODEL} (agent is {C.AGENT_MODEL}, judge is {C.JUDGE_MODEL})")

    t0 = time.time()
    for n, case in enumerate(todo, 1):
        try:
            raw = parse_json(complete(SYSTEM, build(case["customer_opening"]),
                                      provider="gemini", model=LABELLER_MODEL,
                                      json_mode=True, temperature=0.0,
                                      max_tokens=C.JUDGE_MAX_TOKENS,
                                      live=args.live, allow_failover=False))
        except QuotaExhausted as exc:
            print(f"  STOP after {n - 1}: {exc}")
            break
        except Exception as exc:                                # noqa: BLE001
            print(f"  error on {case['case_id']}: {str(exc)[:140]}")
            continue

        intent = raw.get("intent") if raw.get("intent") in INTENT_NAMES else "other"
        handling = raw.get("handling") if raw.get("handling") in ("auto", "escalate") else "escalate"
        reason = raw.get("reason") if raw.get("reason") in ESCALATION_REASONS else None
        done[case["case_id"]] = {
            "case_id": case["case_id"], "intent": intent, "handling": handling,
            "reason": reason if handling == "escalate" else None,
            "ambiguous": bool(raw.get("ambiguous")),
            "note": str(raw.get("note", ""))[:120],
            "source": "machine",                 # never silently mistaken for human
            "labeller_model": LABELLER_MODEL,
        }
        # Written every item so an interrupted run loses nothing.
        out.write_text("\n".join(json.dumps(done[c["case_id"]], ensure_ascii=False)
                                 for c in items if c["case_id"] in done) + "\n",
                       encoding="utf-8")
        if n % 10 == 0 or n == len(todo):
            print(f"  {n}/{len(todo)}  {n/max(time.time()-t0,1e-9)*60:.1f}/min")

    print(f"\n{len(done)}/{len(items)} labelled")
    print("usage:", json.dumps(USAGE.summary(), indent=2))


if __name__ == "__main__":
    main()
