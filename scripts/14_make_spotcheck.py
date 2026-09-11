"""Build a 30-item human validation pass over the machine-labelled set.

The reference labels came from a model. That makes every classification number in
the report agreement between two models rather than accuracy, and nothing in the
project currently measures how far those machine labels track a person.

Thirty items is enough to detect a badly wrong reference and takes about ten
minutes. It does not turn the set into a hand-labelled one, and it is not
presented as doing so. What it buys is a single defensible sentence: the machine
labels agree with a human on N of 30 items, so read the headline accordingly.

The items are a random sample of the random slice, seeded, and the page never
shows what the machine decided, so the human is not anchored to it.

Usage:
  python scripts/14_make_spotcheck.py
  python scripts/label_server.py          # then open /spotcheck.html
  python scripts/15_spotcheck_agreement.py
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--brand", default="hulu_support")
    ap.add_argument("--n", type=int, default=30)
    args = ap.parse_args()

    label_page = C.GOLDEN_DIR / "label.html"
    if not label_page.exists():
        sys.exit("run scripts/04_make_labeller.py first")
    html = label_page.read_text(encoding="utf-8")

    items = json.loads(re.search(r"const ITEMS = (\[.*?\]), TAX", html, re.S).group(1))
    golden = {json.loads(l)["case_id"]: json.loads(l) for l in
              (C.GOLDEN_DIR / f"golden_unlabelled_{args.brand}.jsonl")
              .read_text(encoding="utf-8").splitlines()}

    pool = [it for it in items if golden[it["case_id"]]["slice"] == "random"]
    rng = random.Random(C.RANDOM_SEED + 7)
    subset = rng.sample(pool, min(args.n, len(pool)))

    out = html.replace(json.dumps(items, ensure_ascii=False),
                       json.dumps(subset, ensure_ascii=False), 1)
    # Save to its own file so a spot-check can never overwrite the reference set.
    out = out.replace("'golden_labels.jsonl'", "'spotcheck_labels.jsonl'")
    out = out.replace("<title>Golden set labelling</title>",
                      "<title>Spot check</title>")
    # The milestone hints belong to the 200-item pass and would be wrong here.
    out = re.sub(r"if\(nDone < 120\).*?goal\.textContent = \"complete\";",
                 'goal.textContent = `${ITEMS.length-nDone} left`;', out, flags=re.S)

    path = C.GOLDEN_DIR / "spotcheck.html"
    path.write_text(out, encoding="utf-8")
    print(f"wrote {path} ({len(subset)} items, ~10 minutes)")
    print("labels save to data/golden/spotcheck_labels.jsonl")
    print("the machine's own label is never shown, so the rater is not anchored")


if __name__ == "__main__":
    main()
