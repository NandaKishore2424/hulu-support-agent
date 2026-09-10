"""Baselines the agent has to beat, from trivial to genuinely hard.

A single headline accuracy means nothing without a floor and a cheap
alternative. Three systems are compared.

majority
    Predicts the most frequent intent every time, replies with the most common
    Hulu template, and hands everything the same way. This is the floor. If the
    agent cannot beat it by a wide margin on a skewed label distribution, the
    headline number is an artefact of the skew.

keyword_knn
    No LLM at all. Intent by hand-written keyword rules in priority order, reply
    copied verbatim from the nearest historical case, handling by a lookup on the
    intent. This is the honest competitor: it is free, instant, and copies a real
    human reply, so any credit the agent claims for "sounding like Hulu" has to
    be measured against a system that literally is Hulu.

no_retrieval
    The same LLM and prompt with the exemplars removed. Not a baseline exactly,
    an ablation: it isolates what retrieval contributes rather than what the
    model contributes.
"""
from __future__ import annotations

import re
from collections import Counter

from .agent import AgentOutput, SYSTEM, apply_policy, build_prompt
from .llm import complete, parse_json
from .retrieve import ExemplarIndex
from .taxonomy import ALWAYS_ESCALATE_INTENTS, INTENT_NAMES

# Priority order matters: a message about being charged for a service that also
# will not play is a billing case first. Rules are tried top to bottom.
KEYWORD_RULES: tuple[tuple[str, str], ...] = (
    ("plans_billing",
     r"charg|bill|refund|invoice|price|pricing|\$\d|subscription|cancel|trial|"
     r"add-?on|promo|student|payment|credit card"),
    ("login_access",
     r"log ?in|log ?on|sign ?in|sign ?on|password|credential|locked out|log ?out|"
     r"sign ?out|wrong account"),
    ("service_outage",
     r"\b(?:is|are) (?:hulu|you|it) down\b|outage|down (?:right now|again)|"
     r"not working on any|everything else works|servers?\b"),
    ("ads_experience",
     r"\bads?\b|advert|commercial|ad-?free|no ads|adblock"),
    ("playback_error",
     r"buffer|freez|frozen|error|won'?t (?:play|load|stream)|wont (?:play|load)|"
     r"playback|stream(?:ing)? (?:issue|problem)|lag|stutter|subtitle|caption|"
     r"black screen|keeps (?:stopping|restarting)"),
    ("app_device_problem",
     r"\bapp\b|roku|xbox|playstation|ps4|ps3|fire ?tv|apple ?tv|chromecast|"
     r"switch|crash|navigat|interface|layout|voiceover|accessib"),
    ("content_availability",
     r"season|episode|when (?:is|will|are)|available|add (?:the )?show|"
     r"remove|took .* off|rights|catalog|library|movie"),
    ("product_feedback",
     r"suggestion|feature|please add|i wish|would be (?:nice|great)|bring back"),
    ("unactionable_or_churn",
     r"sucks|worst|garbage|terrible|done with|had enough|never again|lawyer|court"),
)
COMPILED = tuple((name, re.compile(pat, re.I)) for name, pat in KEYWORD_RULES)

# The reply the majority baseline sends, in Hulu's most common shape.
MAJORITY_REPLY = ("Oh no! Sorry for the trouble. What device are you using? "
                  "Let us know and we'll take a look.")


def keyword_intent(message: str) -> str:
    for name, rx in COMPILED:
        if rx.search(message):
            return name
    return "other"


class MajorityBaseline:
    """Constant prediction. The floor."""

    def __init__(self, intent: str = "playback_error", handling: str = "auto"):
        self.intent, self.handling = intent, handling

    @staticmethod
    def fit_intent(labels: list[str]) -> str:
        return Counter(labels).most_common(1)[0][0]

    def run(self, case: dict) -> AgentOutput:
        reason = None if self.handling == "auto" else "no_actionable_detail"
        return AgentOutput(
            case_id=case["case_id"], message=case["customer_opening"],
            intent=self.intent, confidence=1.0, reply=MAJORITY_REPLY,
            grounded_in=[], handling=self.handling, escalation_reason=reason,
            rationale="constant prediction", model_handling=self.handling,
            policy_overrode=False, exemplar_ids=[], raw={"baseline": "majority"})


class KeywordKnnBaseline:
    """Keyword rules for intent, nearest historical reply copied verbatim."""

    def __init__(self, index: ExemplarIndex):
        self.index = index

    def run(self, case: dict) -> AgentOutput:
        message = case["customer_opening"]
        intent = keyword_intent(message)
        hits = self.index.search(message, k=1)
        reply = hits[0].reply if hits else MAJORITY_REPLY
        handling = "escalate" if intent in ALWAYS_ESCALATE_INTENTS else "auto"
        reason = {"plans_billing": "account_or_payment_specific",
                  "service_outage": "confirmed_broad_outage",
                  "unactionable_or_churn": "no_actionable_detail"}.get(intent)
        return AgentOutput(
            case_id=case["case_id"], message=message, intent=intent, confidence=1.0,
            reply=reply, grounded_in=[1] if hits else [], handling=handling,
            escalation_reason=reason, rationale="keyword rule plus nearest neighbour",
            model_handling=handling, policy_overrode=False,
            exemplar_ids=[h.case_id for h in hits], raw={"baseline": "keyword_knn"})


class NoRetrievalAblation:
    """The full prompt with the exemplar block emptied out."""

    def run(self, case: dict, *, live: bool | None = None) -> AgentOutput:
        message = case["customer_opening"]
        raw = parse_json(complete(SYSTEM, build_prompt(message, []),
                                  provider="groq", json_mode=True,
                                  temperature=0.0, live=live))
        intent = raw.get("intent") if raw.get("intent") in INTENT_NAMES else "other"
        try:
            conf = float(raw.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        model_handling = raw.get("handling") if raw.get("handling") in ("auto", "escalate") else "escalate"
        handling, reason, overrode = apply_policy(intent, conf, model_handling,
                                                  raw.get("escalation_reason"))
        return AgentOutput(
            case_id=case["case_id"], message=message, intent=intent, confidence=conf,
            reply=str(raw.get("reply", "")).strip(), grounded_in=[], handling=handling,
            escalation_reason=reason, rationale=str(raw.get("rationale", "")).strip(),
            model_handling=model_handling, policy_overrode=overrode, exemplar_ids=[],
            raw={"baseline": "no_retrieval", **raw})
