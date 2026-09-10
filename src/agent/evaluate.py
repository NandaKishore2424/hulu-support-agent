"""Metrics. Pure computation over saved predictions, so it needs no API key.

Choices worth defending:

Macro F1 alongside accuracy. The intent distribution is skewed, so accuracy is
mostly a report on how well the biggest class is doing. Macro F1 weights a rare
intent as heavily as a common one.

Headline numbers on the random slice only. The boost slice was built by keyword
probes to give rare intents enough support for per-class recall, so it does not
reflect real traffic. Mixing the two would quietly change what accuracy means.

Escalation errors are reported as two separate quantities, never as one score.
Auto-handling something that needed a person is a customer-visible failure.
Escalating something the agent could have handled just costs a human a minute.
They are not interchangeable and averaging them hides the one that matters.

Bootstrap intervals on every headline number. With 120 items, the difference
between 71% and 76% is usually noise, and a report that states a bare point
estimate invites the reader to believe otherwise.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

TOKEN_SPLIT = str.maketrans("", "", ".,!?;:\"'()[]")


# ------------------------------------------------------------------ intervals
def bootstrap_ci(values: list[float], *, n_boot: int = 2000, alpha: float = 0.05,
                 seed: int = 12345) -> tuple[float, float]:
    """Percentile bootstrap interval for the mean of per-item scores."""
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        means.append(sum(values[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[int((1 - alpha / 2) * n_boot) - 1]
    return (lo, hi)


# ------------------------------------------------------------ classification
@dataclass
class ClassMetrics:
    label: str
    support: int
    precision: float
    recall: float
    f1: float


def per_class(y_true: list[str], y_pred: list[str]) -> list[ClassMetrics]:
    labels = sorted(set(y_true) | set(y_pred))
    out = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out.append(ClassMetrics(lab, tp + fn, prec, rec, f1))
    return out


def accuracy(y_true: list[str], y_pred: list[str]) -> float:
    if not y_true:
        return 0.0
    return sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    """Averaged over labels that actually occur in the gold data.

    Labels the model hallucinated but that never appear in gold would otherwise
    drag the average down through a zero it can never fix, which flatters or
    punishes arbitrarily depending on the label set size.
    """
    gold_labels = set(y_true)
    rows = [c for c in per_class(y_true, y_pred) if c.label in gold_labels]
    return sum(c.f1 for c in rows) / len(rows) if rows else 0.0


def confusion(y_true: list[str], y_pred: list[str]) -> dict[tuple[str, str], int]:
    return dict(Counter(zip(y_true, y_pred)))


def top_confusions(y_true: list[str], y_pred: list[str], k: int = 8) -> list[tuple[str, str, int]]:
    pairs = [(t, p, n) for (t, p), n in confusion(y_true, y_pred).items() if t != p]
    return sorted(pairs, key=lambda x: -x[2])[:k]


# ---------------------------------------------------------------- escalation
@dataclass
class TriageMetrics:
    n: int
    precision: float          # of those escalated, how many needed a human
    recall: float             # of those needing a human, how many were caught
    f1: float
    missed_escalations: int   # auto-handled but a human was required
    over_escalations: int     # sent to a human but safely automatable
    missed_rate: float
    over_rate: float
    automation_rate: float    # share the agent handled without a human


def triage(y_true: list[str], y_pred: list[str]) -> TriageMetrics:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == "escalate" and p == "escalate")
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == "auto" and p == "escalate")
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == "escalate" and p == "auto")
    n = len(y_true)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    need_human = tp + fn
    safe_auto = sum(1 for t in y_true if t == "auto")
    return TriageMetrics(
        n=n, precision=prec, recall=rec, f1=f1,
        missed_escalations=fn, over_escalations=fp,
        missed_rate=fn / need_human if need_human else 0.0,
        over_rate=fp / safe_auto if safe_auto else 0.0,
        automation_rate=sum(1 for p in y_pred if p == "auto") / n if n else 0.0,
    )


# ------------------------------------------------------------------- overlap
def token_f1(candidate: str, reference: str) -> float:
    """Unigram overlap with the brand's real reply.

    Reported but not trusted. A different, equally good answer scores near zero,
    and Hulu's own reply is frequently a handoff, so a high score here can mean
    the agent learned to deflect. See the report section on misleading numbers.
    """
    c = Counter(candidate.lower().translate(TOKEN_SPLIT).split())
    r = Counter(reference.lower().translate(TOKEN_SPLIT).split())
    overlap = sum((c & r).values())
    if not overlap:
        return 0.0
    prec = overlap / sum(c.values())
    rec = overlap / sum(r.values())
    return 2 * prec * rec / (prec + rec)


# ----------------------------------------------------------------- agreement
def cohen_kappa(a: list, b: list) -> float:
    """Chance-corrected agreement between two raters over categorical labels."""
    if not a:
        return 0.0
    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum((ca[k] / n) * (cb[k] / n) for k in set(a) | set(b))
    if expected >= 1.0:
        return 1.0
    return (observed - expected) / (1 - expected)


def quadratic_weighted_kappa(a: list[int], b: list[int], lo: int = 1, hi: int = 5) -> float:
    """Kappa for ordered scores, penalising a 5-vs-1 gap far more than 4-vs-5.

    The right statistic for a 1-5 rubric: plain kappa would treat "off by one"
    and "completely opposite" as the same disagreement.
    """
    if not a:
        return 0.0
    labels = list(range(lo, hi + 1))
    idx = {v: i for i, v in enumerate(labels)}
    k = len(labels)
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    n = len(a)
    ha = [sum(row) for row in obs]
    hb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            num += w * obs[i][j]
            den += w * ha[i] * hb[j] / n
    return 1 - num / den if den else 0.0


def exact_and_adjacent(a: list[int], b: list[int]) -> tuple[float, float]:
    """Share of items where two raters agree exactly, and within one point."""
    if not a:
        return (0.0, 0.0)
    exact = sum(1 for x, y in zip(a, b) if x == y) / len(a)
    adj = sum(1 for x, y in zip(a, b) if abs(x - y) <= 1) / len(a)
    return exact, adj
