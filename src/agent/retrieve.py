"""Find how this brand has handled similar problems before.

Two retrievers are fused rather than one, because the two kinds of signal in
these messages fail in opposite ways.

BM25 over words catches the tokens that decide the answer: device names, error
codes, channel names. "Roku" and "PS4" need different troubleshooting steps and
a dense average would blur them.

TF-IDF over character 3-5 grams survives the spelling in real tweets, where
"buffring", "chromcast" and "cant loggin" are common and would be out-of-
vocabulary for word matching.

Scores from two different scales cannot be added, so they are fused by
reciprocal rank fusion, which only uses rank position.

The pool is filtered to replies that actually resolve something. Roughly one
Hulu reply in fourteen is a handoff to phone or chat, and showing those to the
agent as examples would teach it to deflect, which is the behaviour the brand
was chosen for not doing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

HANDOFF_RE = re.compile(
    r"(?:\bdm\b|\bdms\b|direct message|private message|inbox us|"
    r"share (?:your |the )?details (?:here|with us)|"
    r"(?:reach out to|reach out|reach|contact|get in touch with) "
    r"(?:us|our team|the team|here)|"
    r"fill (?:out |in )?(?:this|the) form|call (?:us|the number)|"
    r"chat (?:with )?us|give us a call|send us your details|"
    r"via (?:phone|chat|phone/chat)|phone/(?:live )?chat)", re.I)

TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def is_handoff(reply: str) -> bool:
    return bool(HANDOFF_RE.search(reply))


@dataclass
class Exemplar:
    case_id: str
    customer: str
    reply: str
    score: float


class ExemplarIndex:
    """Rank historical cases by similarity of the customer's opening message."""

    def __init__(self, cases: list[dict], *, drop_handoffs: bool = True,
                 min_reply_chars: int = 40):
        pool = cases
        if drop_handoffs:
            pool = [c for c in pool if not is_handoff(c["brand_first_reply"])]
        # Very short replies are acknowledgements, not resolutions.
        pool = [c for c in pool if len(c["brand_first_reply"]) >= min_reply_chars]
        self.cases = pool
        self.docs = [c["customer_opening"] for c in pool]

        self.bm25 = BM25Okapi([tokenize(d) for d in self.docs])
        self.tfidf = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                     min_df=2, max_features=200_000, sublinear_tf=True)
        self.matrix = self.tfidf.fit_transform(self.docs)

    def __len__(self) -> int:
        return len(self.cases)

    def search(self, query: str, k: int = 4, pool_size: int = 50) -> list[Exemplar]:
        bm = self.bm25.get_scores(tokenize(query))
        bm_top = np.argsort(-bm)[:pool_size]

        qv = self.tfidf.transform([query])
        cos = (self.matrix @ qv.T).toarray().ravel()
        cos_top = np.argsort(-cos)[:pool_size]

        # Reciprocal rank fusion. 60 is the constant from the original paper; it
        # damps the influence of a single retriever's top hit.
        fused: dict[int, float] = {}
        for rank, idx in enumerate(bm_top):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (60 + rank)
        for rank, idx in enumerate(cos_top):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (60 + rank)

        best = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [Exemplar(case_id=self.cases[i]["case_id"],
                         customer=self.cases[i]["customer_opening"],
                         reply=self.cases[i]["brand_first_reply"],
                         score=s) for i, s in best]


def format_exemplars(exemplars: list[Exemplar]) -> str:
    return "\n\n".join(
        f"[past case {n}]\ncustomer: {e.customer}\nHulu replied: {e.reply}"
        for n, e in enumerate(exemplars, 1))
