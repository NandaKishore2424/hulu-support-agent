"""Intent taxonomy and escalation policy for hulu_support.

Induced by reading 120 randomly sampled customer openings from the HISTORY
split only. The holdout split was not read while designing this, so the label
set is not fitted to the examples it is later scored on.

This file is the single source of truth. The labelling guide, the classifier
prompt and the report all render from it, so the definition a human labelled
against and the definition the model was given cannot drift apart.

Boundary rules are written down because the ambiguous pairs are predictable:
playback_error vs service_outage, and content_availability vs plans_billing.
Without a stated rule, disagreement on those pairs is noise rather than signal.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Intent:
    name: str
    definition: str
    boundary: str
    examples: tuple[str, ...]


INTENTS: tuple[Intent, ...] = (
    Intent(
        name="playback_error",
        definition=("Something the customer is watching is broken: it will not start, "
                    "buffers, freezes, throws an error code, resets to the beginning, "
                    "loses its resume position, or arrives with wrong subtitles or a "
                    "truncated ending. Scoped to the customer's own viewing."),
        boundary=("Use this when the customer describes their own failure, even angrily. "
                  "Use service_outage only when they claim Hulu itself is broadly down. "
                  "If the app never opens at all, that is app_device_problem."),
        examples=(
            "I am constantly getting an Error code 3(-971) during commercials",
            "Each commercial break it jumps back to the beginning. Missing parts of it.",
            "Rizzoli & Isles S3E2 subtitles say words are bleeped but audio is fine",
        ),
    ),
    Intent(
        name="login_access",
        definition=("Cannot sign in, password will not work or reset, session drops and "
                    "demands credentials again, signed into the wrong profile or account, "
                    "or cannot sign out."),
        boundary=("The blocking symptom must be authentication. A login prompt appearing "
                  "after a crash is login_access; a crash with no login prompt is "
                  "app_device_problem."),
        examples=(
"why am I suddenly unable to log onto Hulu on my Roku? Email and password no longer saved",
            "I'm logged in the wrong account on PS4 and there is no log out button",
        ),
    ),
    Intent(
        name="app_device_problem",
        definition=("The application or a device integration is at fault rather than one "
                    "video: app will not load or crashes, navigation or layout is unusable, "
                    "casting is not detected, or an accessibility feature is broken."),
        boundary=("A defect report about how the app behaves. If the customer merely "
                  "dislikes a working design, that is product_feedback. Accessibility "
                  "regressions belong here, not in product_feedback, because they are faults."),
        examples=(
            "The app has been redone and is no longer accessible with voiceover for iPhone",
            "the chrome cast tool on your iPhone app takes 2-3 minutes to recognize a chrome cast",
            "the hulu app on my roku wont work even though ive done all the troubleshooting",
        ),
    ),
    Intent(
        name="content_availability",
        definition=("A question or complaint about what exists in the catalogue: when a "
                    "season or episode will arrive, why only some seasons are carried, why "
                    "a title was removed, a request to add a show, or availability in a "
                    "country."),
        boundary=("About whether Hulu carries the content at all. If the customer is asking "
                  "which plan or add-on includes it, use plans_billing."),
        examples=(
            "when is season 4 of steven universe gonna be on your service",
            "WHY TF DID YOU TAKE PAWN STARS OFF??",
            "OK WHY IS THE Hulu APP NOT AVAILABLE IN THE PHILIPPINES?!?",
        ),
    ),
    Intent(
        name="plans_billing",
        definition=("Money and packaging: charges, unexpected or duplicate billing, refunds, "
                    "plan and add-on contents, pricing, trials, promotional or student "
                    "offers, and how to cancel."),
        boundary=("Includes pre-sale questions from people who are not yet customers, such "
                  "as which add-on carries a channel. A charge dispute always lands here "
                  "even when the customer is also threatening to leave."),
        examples=(
            "i canceled my subscription in july so why am i still being charged",
            "Can you please tell me if FoxNews is live streaming yet on HuluLive?",
            "I've been charged by Hulu for years and I don't even have a Hulu account",
        ),
    ),
    Intent(
        name="ads_experience",
        definition=("Advertising specifically: ads appearing on an ad-free plan, the same "
                    "advert repeating, ad load or frequency, or ad-blocker interaction."),
        boundary=("Only when advertising is the subject. An ad break that breaks playback "
                  "is playback_error."),
        examples=(
            "I recently upgraded to Hulu with no ads, but I'm still seeing ads on PS3",
            "can we spice up these ads? I've seen the same CoD advert every break for days",
        ),
    ),
    Intent(
        name="product_feedback",
        definition=("An opinion or feature request about a product that is working as "
                    "designed: dislike of a redesign, a request for picture-in-picture, a "
                    "wish for higher resolution, or a suggestion about autoplay."),
        boundary=("Nothing is broken, so there is nothing to troubleshoot. If a specific "
                  "function fails, it is app_device_problem instead."),
        examples=(
            "so whats the odds of a rollback to the last version? The new interface is awful",
            "So Hulu needs to get on board with picture in picture mode for iPad",
        ),
    ),
    Intent(
        name="service_outage",
        definition=("The customer reports or asks about a broad current failure rather than "
                    "a personal one: Hulu is down, nothing works on any device, or a live "
                    "event failed for everyone."),
        boundary=("Requires a claim of breadth, such as 'is Hulu down', 'not working on any "
                  "device', or a named live event. A single device failing is playback_error."),
        examples=(
            "is Hulu down? Not working on any device. Everything else works fine",
            "30 minutes into the #CubsvsDodgers and still nothing. Absolutely Unacceptable.",
        ),
    ),
    Intent(
        name="unactionable_or_churn",
        definition=("Dissatisfaction with no diagnosable detail, or a stated intention to "
                    "cancel or a threat of escalation, where the message gives nothing to "
                    "troubleshoot."),
        boundary=("Use only when no more specific intent is recoverable. 'Buffering is "
                  "horrid, I'm cancelling' has a diagnosable symptom, so it is "
                  "playback_error. 'Hulu really sucks, I give up' does not."),
        examples=(
            "Hulu really sucks. Tried several times and so many issues, I give up.",
            "I AM LIVID! how DARE you. This is grounds for termination. See you in court!",
        ),
    ),
    Intent(
        name="other",
        definition=("Not a support request: praise with no question, a mention that merely "
                    "tags the brand, promotional or unrelated chatter."),
        boundary="Escape hatch. If a support need is recoverable at all, do not use this.",
        examples=(
            "Wow Hulu coming in clutch with that free account",
            "Before we celebrate Thanksgiving with the Hecks, here's a trip back #TheMiddle",
        ),
    ),
)

INTENT_NAMES: tuple[str, ...] = tuple(i.name for i in INTENTS)
BY_NAME: dict[str, Intent] = {i.name: i for i in INTENTS}

# ---------------------------------------------------------------- escalation
# Auto-handling is only safe when a correct public reply exists that needs no
# account access and carries no commercial or reputational risk. Everything else
# goes to a person. The policy is deliberately conservative: on this channel the
# cost of a wrong public answer is higher than the cost of a human reading a
# tweet.
ESCALATION_RULES: tuple[tuple[str, str], ...] = (
    ("account_or_payment_specific",
     "Resolving it needs the customer's account or payment records, so no public "
     "reply can be correct. Covers charge disputes, refunds and cancellations."),
    ("churn_or_legal_risk",
     "The customer states they are leaving, or threatens legal or regulatory action. "
     "Retention and legal exposure are human decisions."),
    ("abuse_or_severe_distress",
     "Sustained abuse or distress where a templated reply would inflame the thread."),
    ("accessibility_complaint",
     "Accessibility regressions carry legal and reputational weight and deserve a "
     "written human response."),
    ("confirmed_broad_outage",
     "Outage messaging must be centrally consistent, so the agent must not "
     "improvise status claims."),
    ("no_actionable_detail",
     "Nothing in the message can be acted on, so the next move is human judgement "
     "about how to re-engage."),
    ("low_confidence_or_multi_intent",
     "The classifier is unsure, or two intents with different handling are equally "
     "present. Ambiguity is routed to a person rather than guessed."),
)
ESCALATION_REASONS: tuple[str, ...] = tuple(r for r, _ in ESCALATION_RULES)

# Intents whose standard reply is a public, account-free troubleshooting step or
# a policy statement. These are candidates for auto-handling, subject to the
# rules above still firing on the individual message.
AUTO_CANDIDATE_INTENTS: frozenset[str] = frozenset({
    "playback_error", "login_access", "app_device_problem",
    "content_availability", "ads_experience", "product_feedback",
})
ALWAYS_ESCALATE_INTENTS: frozenset[str] = frozenset({
    "plans_billing", "service_outage", "unactionable_or_churn",
})


def taxonomy_prompt_block() -> str:
    """Render the taxonomy for a model prompt, definitions and boundaries included."""
    lines = []
    for i in INTENTS:
        lines.append(f"- {i.name}: {i.definition} BOUNDARY: {i.boundary}")
    return "\n".join(lines)


def escalation_prompt_block() -> str:
    return "\n".join(f"- {name}: {why}" for name, why in ESCALATION_RULES)
