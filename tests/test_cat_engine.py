import pytest
from app.services.cat_engine import (
    p_correct,
    fisher_information,
    estimate_theta_eap,
    estimate_theta_mle,
    update_theta,
    select_next_question,
    theta_to_band,
    is_stopping_condition_met
)


def test_p_correct_basic():
    # Model 3PL: theta=0, a=1, b=0, c=0.25 -> 0.625
    prob = p_correct(theta=0.0, a=1.0, b=0.0, c=0.25)
    assert abs(prob - 0.625) < 1e-6


def test_p_correct_limits():
    # As theta -> -infinity, P -> c
    low_prob = p_correct(theta=-100.0, a=1.5, b=0.0, c=0.20)
    assert abs(low_prob - 0.20) < 1e-4

    # As theta -> +infinity, P -> 1.0
    high_prob = p_correct(theta=100.0, a=1.5, b=0.0, c=0.20)
    assert abs(high_prob - 1.0) < 1e-4


def test_fisher_information():
    # Information should be non-negative
    info = fisher_information(theta=0.0, a=1.5, b=0.0, c=0.20)
    assert info > 0.0

    # Information peaks near difficulty b
    info_near_b = fisher_information(theta=1.0, a=1.5, b=1.0, c=0.20)
    info_far_b = fisher_information(theta=4.0, a=1.5, b=1.0, c=0.20)
    assert info_near_b > info_far_b


def test_eap_all_correct():
    # Student answers 5 questions correctly
    responses = [
        {"a": 1.0, "b": 0.0, "c": 0.25, "is_correct": True}
        for _ in range(5)
    ]
    theta, se = estimate_theta_eap(responses)
    assert theta > 0.0
    assert -4.0 <= theta <= 4.0
    assert 0.0 < se < 2.0


def test_eap_all_wrong():
    # Student answers 5 questions wrongly
    responses = [
        {"a": 1.0, "b": 0.0, "c": 0.25, "is_correct": False}
        for _ in range(5)
    ]
    theta, se = estimate_theta_eap(responses)
    assert theta < 0.0
    assert -4.0 <= theta <= 4.0
    assert 0.0 < se < 2.0


def test_update_theta_hybrid():
    # First 3 items use EAP
    responses = [
        {"a": 1.2, "b": -0.5, "c": 0.25, "is_correct": True},
        {"a": 1.0, "b": 0.2, "c": 0.25, "is_correct": True},
        {"a": 1.5, "b": 0.8, "c": 0.25, "is_correct": False},
    ]
    theta_3, se_3 = update_theta(0.0, responses)
    assert -4.0 <= theta_3 <= 4.0
    assert se_3 > 0.0

    # After 7 mixed items, uses MLE
    more_responses = responses + [
        {"a": 1.1, "b": 0.3, "c": 0.25, "is_correct": True},
        {"a": 1.3, "b": 0.5, "c": 0.25, "is_correct": False},
        {"a": 1.0, "b": 0.0, "c": 0.25, "is_correct": True},
        {"a": 1.4, "b": 0.4, "c": 0.25, "is_correct": False},
    ]
    theta_7, se_7 = update_theta(theta_3, more_responses)
    assert -4.0 <= theta_7 <= 4.0
    assert se_7 > 0.0

    # With 14 items under MLE, total Fisher information increases so SE strictly decreases
    even_more = more_responses * 2
    theta_14, se_14 = update_theta(theta_7, even_more)
    assert -4.0 <= theta_14 <= 4.0
    assert se_14 < se_7


def test_select_next_question():
    candidates = [
        {"id": "q1", "a": 1.2, "b": -1.5, "c": 0.25},
        {"id": "q2", "a": 1.5, "b": 0.1, "c": 0.25},
        {"id": "q3", "a": 1.0, "b": 2.0, "c": 0.25},
    ]
    # For a student with theta = 0.0, q2 has b=0.1 which is closest and high 'a'
    best_item, info = select_next_question(current_theta=0.0, candidates=candidates, used_question_ids=[])
    assert best_item["id"] == "q2"
    assert info > 0.0

    # If q2 was already used, it should pick the next best
    best_next, _ = select_next_question(current_theta=0.0, candidates=candidates, used_question_ids=["q2"])
    assert best_next["id"] in ["q1", "q3"]


def test_theta_to_band():
    assert theta_to_band(-3.0) == 3.5
    assert theta_to_band(-2.0) == 4.5
    assert theta_to_band(-1.0) == 5.5
    assert theta_to_band(0.0) == 6.5
    assert theta_to_band(1.0) == 7.5
    assert theta_to_band(2.0) == 8.5
    assert theta_to_band(3.0) == 9.0


def test_stopping_condition():
    # Not enough items
    stop, reason = is_stopping_condition_met(se_current=0.25, items_administered=4, max_items=20, min_items=5)
    assert not stop
    assert reason is None

    # SE threshold reached after min items
    stop, reason = is_stopping_condition_met(se_current=0.28, items_administered=12, max_items=20, min_items=5, se_threshold=0.30)
    assert stop
    assert reason == "se_threshold"

    # Max items reached
    stop, reason = is_stopping_condition_met(se_current=0.35, items_administered=20, max_items=20)
    assert stop
    assert reason == "max_items"
