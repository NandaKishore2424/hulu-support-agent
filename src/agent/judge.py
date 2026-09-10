"""LLM-as-judge for reply quality, plus the guards that make it worth trusting.

Four things are done deliberately here.

Different vendor. The agent writes on Groq with gpt-oss; the judge scores on
Google's Gemini. A judge from the same family as the generator tends to prefer
its own phrasing, and that bias would inflate every reply score in this report.

Blind to the system. The judge never learns whether a reply came from the agent,
a baseline or a human. Candidates are presented alone, with no label.

Blind to the brand's actual reply for this case. The judge sees the same
retrieved exemplars the agent saw, not the true historical answer. Showing it
the real reply would make it score similarity to one particular answer rather
than quality, and would punish a correct alternative. Similarity to the real
reply is computed separately as its own weak metric.

Anchored scales. Each dimension states what a 1, a 3 and a 5 look like. Bare
1-to-5 scales without anchors drift toward 4 for everything.

The judge is only worth its output if it agrees with a person, so
scripts/07_judge_agreement.py measures that against human ratings and the
report quotes the agreement, not just the scores.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import config as C
from .llm import complete, parse_json
from .retrieve import Exemplar, format_exemplars

RUBRIC = """grounded (1-5): does the advice match how this brand has actually handled this
  problem, judged against the past cases shown?
  1 = invents a step, policy, price or date that contradicts or is absent from the past cases
  3 = broadly plausible and brand-consistent but not clearly supported by any past case
  5 = the step or question is one the brand demonstrably uses for this problem

actionable (1-5): does it move the case forward?
  1 = pure acknowledgement, nothing for the customer to do or answer
  3 = a step or question that is relevant but vague, or several at once
  5 = exactly one concrete step, or the one diagnostic question that unblocks the next step

safe (1-5): does it avoid commitments the brand cannot keep on a public channel?
  1 = promises a refund, a release date, an outage fix, or claims to have looked at the account
  3 = hedged but still implies something it cannot guarantee
  5 = makes no promise it cannot keep and claims no account access

voice (1-5): does it read like this brand's support account?
  1 = generic corporate support boilerplate, or the wrong register entirely
  3 = polite and inoffensive but could be any company
  5 = the brand's own warmth and rhythm, brief, at most one emoji

usable (0 or 1): would you post this unedited?
  0 = too long for a tweet, contains a placeholder like <URL>, addresses the wrong
      person by name, is empty, or is otherwise not postable as written
  1 = postable exactly as written"""

SYSTEM = """You grade draft customer-support replies against a rubric.
You are strict. Most replies are not a 5. Reserve 5 for replies that clearly meet
the anchor. You answer only in JSON."""

TEMPLATE = """Grade the candidate reply.

CUSTOMER MESSAGE
{message}

HOW THIS BRAND HANDLED SIMILAR MESSAGES BEFORE
{exemplars}

CANDIDATE REPLY
{reply}

RUBRIC
{rubric}

Return JSON with exactly these keys:
  "grounded": integer 1-5
  "actionable": integer 1-5
  "safe": integer 1-5
  "voice": integer 1-5
  "usable": 0 or 1
  "worst_problem": one short sentence naming the single biggest flaw, or "none"
"""

DIMENSIONS = ("grounded", "actionable", "safe", "voice")


@dataclass
class Verdict:
    case_id: str
    grounded: int
    actionable: int
    safe: int
    voice: int
    usable: int
    worst_problem: str

    @property
    def mean_quality(self) -> float:
        return sum(getattr(self, d) for d in DIMENSIONS) / len(DIMENSIONS)

    def to_dict(self) -> dict:
        return {**asdict(self), "mean_quality": round(self.mean_quality, 3)}


def _clamp(value, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def judge_reply(case_id: str, message: str, reply: str,
                exemplars: list[Exemplar], *, live: bool | None = None) -> Verdict:
    if not reply.strip():
        return Verdict(case_id, 1, 1, 1, 1, 0, "empty reply")
    prompt = TEMPLATE.format(
        message=message,
        exemplars=format_exemplars(exemplars) if exemplars else "(none available)",
        reply=reply, rubric=RUBRIC)
    raw = parse_json(complete(SYSTEM, prompt, provider="gemini", json_mode=True,
                              temperature=0.0, max_tokens=C.JUDGE_MAX_TOKENS,
                              live=live))
    return Verdict(
        case_id=case_id,
        grounded=_clamp(raw.get("grounded"), 1, 5, 3),
        actionable=_clamp(raw.get("actionable"), 1, 5, 3),
        safe=_clamp(raw.get("safe"), 1, 5, 3),
        voice=_clamp(raw.get("voice"), 1, 5, 3),
        usable=_clamp(raw.get("usable"), 0, 1, 0),
        worst_problem=str(raw.get("worst_problem", "")).strip()[:200],
    )
