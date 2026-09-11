"""How far do the machine reference labels agree with a person?

Reports agreement on intent and on the handling decision, with chance-corrected
kappa alongside raw agreement because the label distribution is skewed and raw
agreement flatters a skewed set.

If this prints a high number the machine reference is defensible as a stand-in. If
it prints a low one, the report's headline figures should be read as noise, and
saying so is the point of running it.

Usage:  python scripts/15_spotcheck_agreement.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                      # noqa: E402
from agent.evaluate import cohen_kappa             # noqa: E402


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> None:
    human = {r["case_id"]: r for r in read(C.GOLDEN_DIR / "spotcheck_labels.jsonl")
             if r.get("intent") and r.get("handling")}
    machine = {r["case_id"]: r for r in read(C.GOLDEN_DIR / "golden_labels.jsonl")
               if r.get("source") == "machine"}
    shared = sorted(set(human) & set(machine))
    if not shared:
        sys.exit("no completed spot-check labels yet; "
                 "run scripts/14_make_spotcheck.py, serve it, and rate the items")

    hi = [human[c]["intent"] for c in shared]
    mi = [machine[c]["intent"] for c in shared]
    hh = [human[c]["handling"] for c in shared]
    mh = [machine[c]["handling"] for c in shared]
    agree_i = sum(1 for a, b in zip(hi, mi) if a == b) / len(shared)
    agree_h = sum(1 for a, b in zip(hh, mh) if a == b) / len(shared)

    print(f"spot check on {len(shared)} items\n")
    print(f"  intent   agreement {agree_i:.0%}   kappa {cohen_kappa(hi, mi):+.3f}")
    print(f"  handling agreement {agree_h:.0%}   kappa {cohen_kappa(hh, mh):+.3f}")
    print("\ndisagreements:")
    for c in shared:
        if human[c]["intent"] != machine[c]["intent"]:
            print(f"  human={human[c]['intent']:22s} machine={machine[c]['intent']:22s}")
    out = {"n": len(shared), "intent_agreement": agree_i, "intent_kappa": cohen_kappa(hi, mi),
           "handling_agreement": agree_h, "handling_kappa": cohen_kappa(hh, mh)}
    (C.REPORT_DIR / "spotcheck_agreement.json").write_text(json.dumps(out, indent=2))
    print(f"\nwrote {C.REPORT_DIR / 'spotcheck_agreement.json'}")


if __name__ == "__main__":
    main()
