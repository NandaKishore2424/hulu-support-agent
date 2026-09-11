"""Turn the raw twcs.csv dump into per-brand support cases.

The raw file is one row per tweet with a pointer to the tweet it replied to.
Nothing in it is a conversation yet, so this module does three jobs:

1. Rebuild threads by following in_response_to_tweet_id.
2. Collapse consecutive tweets from the same speaker, because customers commonly
   split one complaint across three tweets and each is a separate row.
3. Reduce each thread to a "case": the customer's opening message, the brand's
   first substantive reply, and the rest of the thread as context.

Normalisation keeps the original text alongside the cleaned text. Anything we
throw away, we can still show in the failure analysis.
"""
from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from . import config as C

URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@[A-Za-z0-9_]+")
# Support agents sign off with their initials, e.g. "...let us know. ^JB" or "*TM".
SIGNOFF_RE = re.compile(r"\s*[\^\*][A-Za-z]{2,3}\s*$")
WS_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Light cleaning only. Aggressive cleaning would hide real input noise."""
    t = str(text)
    t = URL_RE.sub("<URL>", t)
    t = MENTION_RE.sub("@user", t)
    t = SIGNOFF_RE.sub("", t)
    return WS_RE.sub(" ", t).strip()


@dataclass
class Turn:
    role: str            # "customer" or "brand"
    author: str
    created_at: str
    text: str
    text_raw: str
    tweet_ids: list[int]


@dataclass
class Case:
    case_id: str
    brand: str
    customer_opening: str          # normalised, what the agent sees
    customer_opening_raw: str
    brand_first_reply: str         # normalised, the historical response
    brand_first_reply_raw: str
    n_turns: int
    n_customer_turns: int
    created_at: str
    thread: list[dict]             # full collapsed thread, for context and audit


def load_raw(path: Path | None = None, nrows: int | None = None) -> pd.DataFrame:
    path = path or C.TWCS_CSV
    df = pd.read_csv(path, nrows=nrows, dtype={"tweet_id": "int64", "author_id": "string",
                                               "text": "string", "response_tweet_id": "string"})
    df["in_response_to_tweet_id"] = pd.to_numeric(df["in_response_to_tweet_id"],
                                                  errors="coerce")
    return df


def build_threads(df: pd.DataFrame) -> list[list[dict]]:
    """Walk reply pointers into ordered threads.

    Roots are tweets with no parent. When a tweet has several replies the thread
    follows the earliest one; branch counts are reported by thread_stats so the
    report can say how much conversation this discards.
    """
    by_id: dict[int, dict] = {}
    children: dict[int, list[int]] = defaultdict(list)

    for row in df.itertuples(index=False):
        by_id[row.tweet_id] = {
            "tweet_id": row.tweet_id,
            "author_id": str(row.author_id),
            "inbound": bool(row.inbound),
            "created_at": str(row.created_at),
            "text": str(row.text),
        }
        parent = row.in_response_to_tweet_id
        if pd.notna(parent):
            children[int(parent)].append(row.tweet_id)

    has_parent = set()
    for kids in children.values():
        has_parent.update(kids)
    roots = [tid for tid in by_id if tid not in has_parent]

    threads: list[list[dict]] = []
    for root in roots:
        chain, node = [], root
        seen = set()
        while node is not None and node in by_id and node not in seen:
            seen.add(node)
            chain.append(by_id[node])
            kids = [k for k in children.get(node, []) if k in by_id]
            kids.sort(key=lambda k: by_id[k]["tweet_id"])
            node = kids[0] if kids else None
        if len(chain) >= 2:
            threads.append(chain)
    return threads


def collapse_turns(thread: list[dict]) -> list[Turn]:
    """Merge runs of consecutive tweets by the same speaker into one turn."""
    turns: list[Turn] = []
    for tw in thread:
        role = "customer" if tw["inbound"] else "brand"
        if turns and turns[-1].role == role and turns[-1].author == tw["author_id"]:
            prev = turns[-1]
            prev.text_raw = f"{prev.text_raw} {tw['text']}"
            prev.text = normalize_text(prev.text_raw)
            prev.tweet_ids.append(tw["tweet_id"])
        else:
            turns.append(Turn(role=role, author=tw["author_id"],
                              created_at=tw["created_at"],
                              text=normalize_text(tw["text"]),
                              text_raw=tw["text"], tweet_ids=[tw["tweet_id"]]))
    return turns


def thread_brand(turns: list[Turn]) -> str | None:
    for t in turns:
        if t.role == "brand":
            return t.author
    return None


def to_cases(threads: list[list[dict]], brand: str | None = None) -> list[Case]:
    """One Case per thread that starts with a customer and gets a brand reply."""
    cases: list[Case] = []
    for chain in threads:
        turns = collapse_turns(chain)
        if not turns or turns[0].role != "customer":
            continue
        b = thread_brand(turns)
        if b is None or (brand and b != brand):
            continue
        first_brand = next(t for t in turns if t.role == "brand")
        cases.append(Case(
            case_id=f"{b}-{turns[0].tweet_ids[0]}",
            brand=b,
            customer_opening=turns[0].text,
            customer_opening_raw=turns[0].text_raw,
            brand_first_reply=first_brand.text,
            brand_first_reply_raw=first_brand.text_raw,
            n_turns=len(turns),
            n_customer_turns=sum(1 for t in turns if t.role == "customer"),
            created_at=turns[0].created_at,
            thread=[asdict(t) for t in turns],
        ))
    return cases


def save_cases(cases: list[Case], path: Path) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


def load_cases(path: Path) -> list[dict]:
    """Read a case file, transparently preferring a gzipped copy.

    The Hulu history split is 19 MB of JSON lines and compresses to 2.5 MB, so
    the repository ships the gzipped form. That keeps a clone small while still
    letting someone reproduce the results without a Kaggle account, which they
    would otherwise need just to rebuild an intermediate file.
    """
    if not path.exists() and path.with_suffix(path.suffix + ".gz").exists():
        path = path.with_suffix(path.suffix + ".gz")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ------------------------------------------------------------------ scoping
def add_root_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Label every tweet with the id of the first tweet in its thread.

    Done once over the whole file with memoisation so that scoping to a single
    brand afterwards is a cheap filter rather than a graph walk per brand.
    """
    parent: dict[int, int] = {}
    for tid, pid in zip(df["tweet_id"].to_numpy(),
                        df["in_response_to_tweet_id"].to_numpy(), strict=True):
        if pd.notna(pid):
            parent[int(tid)] = int(pid)

    root_of: dict[int, int] = {}

    def find_root(start: int) -> int:
        path = []
        node = start
        while node in parent and node not in root_of:
            path.append(node)
            node = parent[node]
        root = root_of.get(node, node)
        for n in path:
            root_of[n] = root
        root_of[start] = root
        return root

    df = df.copy()
    df["root_id"] = [find_root(int(t)) for t in df["tweet_id"].to_numpy()]
    return df


def scope_to_brand(df: pd.DataFrame, brand: str) -> pd.DataFrame:
    """Every tweet belonging to a thread this brand participated in."""
    if "root_id" not in df.columns:
        df = add_root_ids(df)
    roots = set(df.loc[df["author_id"] == brand, "root_id"].unique())
    return df[df["root_id"].isin(roots)]
