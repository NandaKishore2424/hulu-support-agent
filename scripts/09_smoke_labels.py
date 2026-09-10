"""Generate throwaway labels so the metrics harness can be tested before the real
golden labels exist.

This is NOT an evaluation set and must never appear in the report. Its only job is
to prove that `06_metrics.py` runs, joins, and renders every table, so that the
moment the hand-labelled file lands the last mile is already de-risked.

Labels are copied from the keyword baseline's own predictions, deliberately. That
makes them free, deterministic, and obviously circular: the keyword baseline will
score 100% against them. Any number produced from this file is meaningless by
construction, which is safer than plausible-looking fake labels that someone
might mistake for real ones. The file records its own status in every row.

Usage:  python scripts/09_smoke_labels.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C                      # noqa: E402

OUT = C.GOLDEN_DIR / "golden_labels_SMOKE.jsonl"


def main() -> None:
    src = C.REPORT_DIR / "predictions" / "keyword_knn.jsonl"
    if not src.exists():
        sys.exit("run scripts/05_run_systems.py --stage predict first")
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    with OUT.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({
                "case_id": r["case_id"],
                "intent": r["intent"],
                "handling": r["handling"],
                "reason": r.get("escalation_reason"),
                "source": "smoke_not_golden",
            }, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} throwaway labels to {OUT}")
    print("these exist only to exercise the harness; the keyword baseline will")
    print("score 100% against them because they were copied from it.")


if __name__ == "__main__":
    main()
