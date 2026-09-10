"""The support agent: classify, draft a grounded reply, decide who handles it.

One model call does all three. They are not independent problems: the reply
depends on the intent, and the escalation reason has to be consistent with both.
Three separate calls would let them contradict each other, and would triple the
cost against a free-tier quota.

The escalation decision is deliberately split in two.

  The model proposes. It sees the message, the taxonomy and the escalation
  reasons, and says what it thinks should happen.

  Policy code disposes. Hard rules then run in Python and can override the
  model. Billing always goes to a human, so does an outage, so does anything the
  model was unsure about. This matters because an escalation policy that lives
  only inside a prompt cannot be audited, cannot be unit tested, and changes
  silently whenever the model is swapped.

Every override is recorded, so the report can say how often policy disagreed
with the model rather than assuming they agree.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from . import config as C
from .llm import complete, parse_json
from .retrieve import Exemplar, ExemplarIndex, format_exemplars
from .taxonomy import (ALWAYS_ESCALATE_INTENTS, ESCALATION_REASONS, INTENT_NAMES,
                       escalation_prompt_block, taxonomy_prompt_block)

CONFIDENCE_FLOOR = 0.55

SYSTEM = """You are a customer support agent for Hulu, replying in public on Twitter.

House style, learned from how Hulu actually replies:
- Open with a short, warm acknowledgement. Hulu uses "Oh no!", "Uh oh!", "Sorry to hear that".
- Then do exactly one useful thing: give one concrete troubleshooting step, or ask
  the one diagnostic question that unblocks the next step. Never both at length.
- Under 280 characters. These are tweets.
- Warm but not gushing. At most one emoji.
- Never invent a release date, a price, a refund, a policy or an outage status.
- You have no access to any customer account, so never claim to have looked one up.

You answer only in JSON matching the requested schema."""

TEMPLATE = """Classify this customer message, draft a reply, and decide who should handle it.

INTENT LABELS
{taxonomy}

ESCALATION REASONS
{escalations}

HOW HULU HANDLED SIMILAR MESSAGES BEFORE
Ground your reply in these. Reuse the steps and the tone. If none of them fit
the customer's problem, say so in grounded_in rather than inventing a step.

{exemplars}

CUSTOMER MESSAGE
{message}

Return JSON with exactly these keys:
  "intent": one of {intent_list}
  "confidence": number between 0 and 1, how sure you are of the intent
  "reply": the tweet you would send, under 280 characters
  "grounded_in": list of the past case numbers you actually used, e.g. [1, 3];
                 empty list if none of them fit
  "handling": "auto" or "escalate"
  "escalation_reason": one of {reason_list}, or null when handling is "auto"
  "rationale": one sentence, why this handling"""


@dataclass
class AgentOutput:
    case_id: str
    message: str
    intent: str
    confidence: float
    reply: str
    grounded_in: list[int]
    handling: str                    # final decision, after policy
    escalation_reason: str | None
    rationale: str
    model_handling: str              # what the model proposed, before policy
    policy_overrode: bool
    exemplar_ids: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def build_prompt(message: str, exemplars: list[Exemplar]) -> str:
    return TEMPLATE.format(
        taxonomy=taxonomy_prompt_block(),
        escalations=escalation_prompt_block(),
        exemplars=format_exemplars(exemplars) if exemplars else "(no similar past cases found)",
        message=message,
        intent_list=", ".join(INTENT_NAMES),
        reason_list=", ".join(ESCALATION_REASONS),
    )


def apply_policy(intent: str, confidence: float, model_handling: str,
                 model_reason: str | None) -> tuple[str, str | None, bool]:
    """Hard escalation rules that outrank whatever the model proposed.

    Returns (handling, reason, overrode).
    """
    if intent in ALWAYS_ESCALATE_INTENTS:
        reason = {
            "plans_billing": "account_or_payment_specific",
            "service_outage": "confirmed_broad_outage",
            "unactionable_or_churn": "no_actionable_detail",
        }[intent]
        return "escalate", reason, model_handling != "escalate"

    if confidence < CONFIDENCE_FLOOR:
        return "escalate", "low_confidence_or_multi_intent", model_handling != "escalate"

    if model_handling == "escalate":
        reason = model_reason if model_reason in ESCALATION_REASONS else "low_confidence_or_multi_intent"
        return "escalate", reason, False

    return "auto", None, False


def run(case: dict, index: ExemplarIndex, *, k: int = C.RETRIEVAL_K,
        live: bool | None = None) -> AgentOutput:
    message = case["customer_opening"]
    exemplars = index.search(message, k=k)
    raw_text = complete(SYSTEM, build_prompt(message, exemplars),
                        provider="groq", json_mode=True, temperature=0.0, live=live)
    raw = parse_json(raw_text)

    intent = raw.get("intent", "other")
    if intent not in INTENT_NAMES:
        intent = "other"
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    model_handling = raw.get("handling", "escalate")
    if model_handling not in ("auto", "escalate"):
        model_handling = "escalate"

    handling, reason, overrode = apply_policy(
        intent, confidence, model_handling, raw.get("escalation_reason"))

    grounded = [g for g in (raw.get("grounded_in") or []) if isinstance(g, int)]
    return AgentOutput(
        case_id=case["case_id"], message=message, intent=intent, confidence=confidence,
        reply=str(raw.get("reply", "")).strip(), grounded_in=grounded,
        handling=handling, escalation_reason=reason,
        rationale=str(raw.get("rationale", "")).strip(),
        model_handling=model_handling, policy_overrode=overrode,
        exemplar_ids=[e.case_id for e in exemplars], raw=raw,
    )
