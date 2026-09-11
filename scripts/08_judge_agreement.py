"""Does the LLM judge agree with a person?

Reports agreement at two levels, because they answer different questions and a
judge can pass one and fail the other.

Per item. Do the judge and the human give the same reply the same score? Reported
as exact agreement, agreement within one point, and quadratic weighted kappa,
which penalises a 5-versus-1 disagreement far more than a 4-versus-5. Mean
difference is reported too, since a judge that is uniformly one point generous is
still perfectly usable for comparing systems.

Per system. Do the judge and the human rank the systems in the same order? This
is the question the report actually rests on, because every claim in it is a
comparison between systems rather than a statement about one absolute score. A
judge with only moderate per-item agreement can still rank systems correctly, and
saying so honestly is better than quoting a kappa and hoping.

Usage:  python scripts/08_judge_agreement.py
"""
from __future__ import annotations

import json
import statistics as stats
import sys
from collections import defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from agent import config as C                                       # noqa: E402
from agent.evaluate import (cohen_kappa, exact_and_adjacent,        # noqa: E402
                            quadratic_weighted_kappa)
from agent.judge import DIMENSIONS                                  # noqa: E402

JUDGE_DIR = C.REPORT_DIR / "judgements"


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    plan = {r["rating_id"]: r for r in read_jsonl(C.GOLDEN_DIR / "rating_plan.jsonl")}
    human_rows = read_jsonl(C.GOLDEN_DIR / "reply_ratings.jsonl")
    if not plan:
        sys.exit("no rating plan; run scripts/07_make_rater.py first")
    if not human_rows:
        sys.exit(f"no human ratings at {C.GOLDEN_DIR / 'reply_ratings.jsonl'}\n"
                 "serve data/golden/rate.html, rate the replies, export, save it there.")

    judge_by: dict[tuple[str, str], dict] = {}
    seen_models: set[str] = set()
    for path in JUDGE_DIR.glob("*.jsonl"):
        for v in read_jsonl(path):
            judge_by[(v["case_id"], path.stem)] = v
            seen_models.add(v.get("judge_model", "unknown"))

    pairs: list[tuple[dict, dict, str]] = []
    for row in human_rows:
        rid = row.get("rating_id")
        if not rid or rid not in plan:
            continue
        if not all(d in row for d in DIMENSIONS + ("usable",)):
            continue
        system = plan[rid]["system"]
        verdict = judge_by.get((plan[rid]["case_id"], system))
        if verdict:
            pairs.append((row, verdict, system))

    if len(seen_models) > 1:
        sys.exit(f"verdicts come from more than one judge {sorted(seen_models)}; "
                 "agreement across mixed judges is not interpretable.")
    if not pairs:
        sys.exit("no overlap between human ratings and judge verdicts. "
                 "run scripts/05_run_systems.py --stage judge first.")

    print(f"matched {len(pairs)} human ratings to judge verdicts "
          f"across {len({s for _, _, s in pairs})} systems\n")

    print("--- per item agreement ---")
    print(f"{'dimension':12s} {'exact':>7s} {'within1':>8s} {'QWK':>7s} "
          f"{'human':>7s} {'judge':>7s} {'judge-human':>12s}")
    result: dict[str, dict] = {}
    for d in DIMENSIONS:
        h = [int(p[0][d]) for p in pairs]
        j = [int(p[1][d]) for p in pairs]
        ex, adj = exact_and_adjacent(h, j)
        qwk = quadratic_weighted_kappa(h, j)
        print(f"{d:12s} {ex:7.2f} {adj:8.2f} {qwk:7.3f} "
              f"{stats.mean(h):7.2f} {stats.mean(j):7.2f} {stats.mean(j)-stats.mean(h):12.2f}")
        result[d] = {"exact": ex, "within_one": adj, "qwk": qwk,
                     "human_mean": stats.mean(h), "judge_mean": stats.mean(j)}

    hu = [int(p[0]["usable"]) for p in pairs]
    ju = [int(p[1]["usable"]) for p in pairs]
    agree = sum(1 for a, b in zip(hu, ju, strict=True) if a == b) / len(hu)
    kap = cohen_kappa(hu, ju)
    print(f"{'usable':12s} {agree:7.2f} {'-':>8s} {kap:7.3f} "
          f"{stats.mean(hu):7.2f} {stats.mean(ju):7.2f} {stats.mean(ju)-stats.mean(hu):12.2f}")
    result["usable"] = {"exact": agree, "cohen_kappa": kap,
                        "human_mean": stats.mean(hu), "judge_mean": stats.mean(ju)}

    print("\n--- per system ranking, the comparison the report relies on ---")
    by_system_h: dict[str, list[float]] = defaultdict(list)
    by_system_j: dict[str, list[float]] = defaultdict(list)
    for hrow, jrow, system in pairs:
        by_system_h[system].append(stats.mean([int(hrow[d]) for d in DIMENSIONS]))
        by_system_j[system].append(stats.mean([int(jrow[d]) for d in DIMENSIONS]))
    print(f"{'system':14s} {'n':>4s} {'human mean':>11s} {'judge mean':>11s}")
    rows = []
    for system in sorted(by_system_h, key=lambda s: -stats.mean(by_system_h[s])):
        hm, jm = stats.mean(by_system_h[system]), stats.mean(by_system_j[system])
        print(f"{system:14s} {len(by_system_h[system]):4d} {hm:11.2f} {jm:11.2f}")
        rows.append((system, hm, jm))
    h_order = [s for s, _, _ in sorted(rows, key=lambda r: -r[1])]
    j_order = [s for s, _, _ in sorted(rows, key=lambda r: -r[2])]
    print(f"\nhuman ranking: {' > '.join(h_order)}")
    print(f"judge ranking: {' > '.join(j_order)}")
    print("rankings agree" if h_order == j_order else "RANKINGS DISAGREE")
    result["system_ranking"] = {"human": h_order, "judge": j_order,
                                "agree": h_order == j_order,
                                "means": {s: {"human": h, "judge": j} for s, h, j in rows}}

    out = C.REPORT_DIR / "judge_agreement.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
