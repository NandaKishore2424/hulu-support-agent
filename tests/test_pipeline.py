"""Tests for the parts where a silent bug would corrupt every reported number."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.baselines import keyword_intent
from agent.data import add_root_ids, build_threads, collapse_turns, normalize_text, to_cases
from agent.evaluate import (accuracy, bootstrap_ci, cohen_kappa, macro_f1,
                            quadratic_weighted_kappa, token_f1, triage)
from agent.retrieve import is_handoff
from agent.taxonomy import ALWAYS_ESCALATE_INTENTS, INTENT_NAMES
from agent.agent import apply_policy


def _frame(rows):
    df = pd.DataFrame(rows)
    df["in_response_to_tweet_id"] = pd.to_numeric(df["in_response_to_tweet_id"], errors="coerce")
    return df


THREAD = [
    dict(tweet_id=1, author_id="123", inbound=True, created_at="a", text="app broken", in_response_to_tweet_id=None),
    dict(tweet_id=2, author_id="123", inbound=True, created_at="b", text="on roku", in_response_to_tweet_id=1),
    dict(tweet_id=3, author_id="hulu_support", inbound=False, created_at="c", text="try rebooting ^JB", in_response_to_tweet_id=2),
]


def test_normalize_strips_urls_mentions_and_agent_initials():
    out = normalize_text("@Someone try https://t.co/abc now ^JB")
    assert out == "@user try <URL> now"


def test_threads_are_rebuilt_in_order():
    threads = build_threads(_frame(THREAD))
    assert len(threads) == 1
    assert [t["tweet_id"] for t in threads[0]] == [1, 2, 3]


def test_consecutive_customer_tweets_collapse_into_one_turn():
    turns = collapse_turns(build_threads(_frame(THREAD))[0])
    assert [t.role for t in turns] == ["customer", "brand"]
    assert turns[0].text == "app broken on roku"
    assert turns[0].tweet_ids == [1, 2]


def test_case_captures_opening_and_first_brand_reply():
    cases = to_cases(build_threads(_frame(THREAD)), brand="hulu_support")
    assert len(cases) == 1
    assert cases[0].customer_opening == "app broken on roku"
    assert cases[0].brand_first_reply == "try rebooting"


def test_root_ids_group_a_thread_together():
    df = add_root_ids(_frame(THREAD))
    assert df["root_id"].nunique() == 1


def test_handoff_detector_covers_both_idioms():
    assert is_handoff("Please DM us and we'll help")
    assert is_handoff("Kindly share your details here: <URL>")
    assert is_handoff("reach out here: <URL>")
    assert not is_handoff("Try rebooting your modem and router: <URL>")


@pytest.mark.parametrize("message,expected", [
    ("charged twice this month", "plans_billing"),
    ("cant log in on roku", "login_access"),
    ("is hulu down for everyone", "service_outage"),
    ("when is season 4 coming", "content_availability"),
])
def test_keyword_baseline_rules_fire_in_priority_order(message, expected):
    assert keyword_intent(message) == expected


def test_policy_overrides_the_model_on_always_escalate_intents():
    for intent in ALWAYS_ESCALATE_INTENTS:
        handling, reason, overrode = apply_policy(intent, 0.99, "auto", None)
        assert handling == "escalate"
        assert reason is not None
        assert overrode is True


def test_policy_escalates_when_the_model_is_unsure():
    handling, reason, _ = apply_policy("playback_error", 0.10, "auto", None)
    assert handling == "escalate"
    assert reason == "low_confidence_or_multi_intent"


def test_policy_leaves_a_confident_auto_case_alone():
    handling, reason, overrode = apply_policy("playback_error", 0.95, "auto", None)
    assert (handling, reason, overrode) == ("auto", None, False)


def test_macro_f1_ignores_labels_absent_from_gold():
    y_true = ["a", "a", "b", "b"]
    perfect = macro_f1(y_true, y_true)
    assert perfect == pytest.approx(1.0)
    assert macro_f1(y_true, ["a", "a", "b", "other"]) < perfect


def test_triage_separates_the_two_error_kinds():
    t = triage(["escalate", "auto", "escalate"], ["auto", "escalate", "escalate"])
    assert t.missed_escalations == 1
    assert t.over_escalations == 1


def test_bootstrap_interval_brackets_the_mean():
    lo, hi = bootstrap_ci([1.0] * 75 + [0.0] * 25)
    assert lo < 0.75 < hi


def test_weighted_kappa_punishes_far_disagreement_more():
    close = quadratic_weighted_kappa([5, 4, 3, 2, 1], [4, 4, 3, 2, 2])
    far = quadratic_weighted_kappa([5, 4, 3, 2, 1], [1, 2, 3, 4, 5])
    assert close > far


def test_kappa_is_zero_when_agreement_is_only_chance():
    assert cohen_kappa(["a"] * 10, ["a"] * 10) == pytest.approx(1.0)


def test_token_f1_rewards_overlap_not_identity():
    assert token_f1("reboot your router", "reboot your router") == pytest.approx(1.0)
    assert 0 < token_f1("reboot your router", "please reboot the router") < 1
    assert token_f1("reboot your router", "season four arrives later") == 0.0


def test_taxonomy_and_accuracy_are_consistent():
    assert len(INTENT_NAMES) == len(set(INTENT_NAMES))
    assert accuracy(["a", "b"], ["a", "b"]) == 1.0
