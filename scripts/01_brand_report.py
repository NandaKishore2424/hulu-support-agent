"""Pick a brand with evidence rather than by reputation.

Brand choice decides the whole assignment, so it is made on measured properties
of the data. The property that matters is whether the brand resolves issues in
public. If its standard move is to move the customer to DM or to a web form,
then the visible reply is a handoff, the real resolution happened off-platform,
and there is nothing to ground a drafted reply in. Measuring reply quality
against handoffs would be measuring nothing.

Two handoff idioms exist and both must be counted. AppleSupport and SpotifyCares
say "DM us". AmazonHelp says "share your details here" with a form link. A
DM-only regex ranks Amazon as the most substantive brand in the dataset, which
is wrong, so channel-switch phrasing is detected as well.

Usage:  python scripts/01_brand_report.py [--nrows N] [--top 25]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agent import config as C          # noqa: E402
from agent.data import load_raw        # noqa: E402

# Moving the customer to another channel. The resolution leaves the dataset here.
HANDOFF_RE = re.compile(
    r"(?:\bdm\b|\bdms\b|direct message|private message|inbox us|"
    r"share (?:your |the )?details (?:here|with us)|"
    r"(?:reach out to|reach|contact|get in touch with) (?:us|our team|the team)"
    r"(?: here| at| on)?|fill (?:out |in )?(?:this|the) form|"
    r"call (?:us|/chat us)|chat (?:with )?us|give us a call|"
    r"send us your details|let us know in dm)", re.I)

# A pointer to a help article is grounded content, not a handoff.
LINK_RE = re.compile(r"https?://\S+")
# Concrete self-service instructions: the thing we most want to learn to imitate.
INSTRUCT_RE = re.compile(
    r"\b(?:try|restart|reboot|reset|update|reinstall|uninstall|clear|check|"
    r"toggle|tap|click|go to|head to|open|log ?out|sign ?out|swipe|hold|"
    r"unplug|power cycle|settings)\b", re.I)
# Asking for the information needed to diagnose.
DIAGNOSTIC_RE = re.compile(
    r"(?:\?|\bwhat (?:device|version|happens)|which (?:device|version|browser)|"
    r"are you (?:seeing|getting|able)|have you tried|can you (?:confirm|tell|share))", re.I)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nrows", type=int, default=None)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--min-tweets", type=int, default=5000)
    args = ap.parse_args()

    df = load_raw(nrows=args.nrows)
    print(f"rows={len(df):,}  inbound={int(df['inbound'].sum()):,}")

    out = df[~df["inbound"]].copy()
    out["text"] = out["text"].astype(str)
    out["handoff"] = out["text"].str.contains(HANDOFF_RE)
    out["instructs"] = out["text"].str.contains(INSTRUCT_RE) & ~out["handoff"]
    out["diagnoses"] = out["text"].str.contains(DIAGNOSTIC_RE) & ~out["handoff"]
    out["links"] = out["text"].str.contains(LINK_RE)
    out["chars"] = out["text"].str.len()

    g = out.groupby("author_id")
    stats = pd.DataFrame({
        "brand_tweets": g.size(),
        "handoff": g["handoff"].mean(),
        "instructs": g["instructs"].mean(),
        "diagnoses": g["diagnoses"].mean(),
        "links": g["links"].mean(),
        "med_chars": g["chars"].median(),
    })
    stats = stats[stats["brand_tweets"] >= args.min_tweets]
    # Groundable = the brand either gives a concrete instruction or asks a real
    # diagnostic question, instead of pushing the conversation off Twitter.
    stats["groundable"] = (out.groupby("author_id")
                              .apply(lambda d: (d["instructs"] | d["diagnoses"]).mean(),
                                     include_groups=False)
                              .reindex(stats.index))
    stats = stats.sort_values("groundable", ascending=False)

    pd.set_option("display.width", 160)
    print(f"\n=== brands with >= {args.min_tweets:,} outbound tweets, ranked by groundable reply share ===")
    print(stats.head(args.top).round(3).to_string())
    print("\n=== highest-volume brands ===")
    print(stats.sort_values("brand_tweets", ascending=False).head(10).round(3).to_string())
    stats.round(4).to_csv(C.PROC_DIR / "brand_stats.csv")
    print(f"\nwrote {C.PROC_DIR / 'brand_stats.csv'}")


if __name__ == "__main__":
    main()
