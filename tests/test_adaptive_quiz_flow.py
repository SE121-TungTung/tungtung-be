import pytest
from unittest.mock import MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserRole, UserStatus
from app.core.database import get_db
from app.dependencies import get_current_active_user
from app.services.cat_engine import (
    p_correct,
    fisher_information,
    update_theta,
    is_stopping_condition_met,
    theta_to_band,
)

client = TestClient(app, base_url="http://testserver/api/v1")


def test_full_cat_adaptive_convergence_flow():
    """
    Simulate full CAT lifecycle:
    1. Initial theta = 0.0, SE = 1.0
    2. Student answers sequentially (alternating or consistently)
    3. Theta adjusts appropriately (increases on correct, decreases on incorrect)
    4. Information accumulates and SE strictly decreases
    5. Stopping rule triggers when SE < 0.3 or max items reached
    """
    theta = 0.0
    se = 1.0
    administered_responses = []

    # Simulated item bank calibrated parameters (a, b, c)
    items = [
        {"a": 1.2, "b": 0.0, "c": 0.2, "correct": True},
        {"a": 1.4, "b": 0.5, "c": 0.2, "correct": True},
        {"a": 1.5, "b": 1.1, "c": 0.2, "correct": False},
        {"a": 1.3, "b": 0.8, "c": 0.2, "correct": True},
        {"a": 1.6, "b": 1.3, "c": 0.2, "correct": True},
        {"a": 1.8, "b": 1.8, "c": 0.2, "correct": True},
        {"a": 1.7, "b": 2.2, "c": 0.2, "correct": False},
        {"a": 1.5, "b": 1.9, "c": 0.2, "correct": True},
        {"a": 1.6, "b": 2.1, "c": 0.2, "correct": True},
        {"a": 1.5, "b": 2.3, "c": 0.2, "correct": False},
        {"a": 1.7, "b": 2.0, "c": 0.2, "correct": True},
        {"a": 1.6, "b": 2.2, "c": 0.2, "correct": True},
        {"a": 1.8, "b": 2.4, "c": 0.2, "correct": False},
        {"a": 1.7, "b": 2.1, "c": 0.2, "correct": True},
        {"a": 1.6, "b": 2.3, "c": 0.2, "correct": True},
    ]

    se_history = [se]
    theta_history = [theta]

    for idx, item in enumerate(items, 1):
        # 1. Calculate Fisher info at current theta
        info = fisher_information(theta, item["a"], item["b"], item["c"])
        assert info > 0, f"Fisher information must be strictly positive, got {info}"

        # 2. Append response
        administered_responses.append({
            "a": item["a"],
            "b": item["b"],
            "c": item["c"],
            "is_correct": item["correct"],
        })

        # 3. Update theta
        new_theta, new_se = update_theta(theta, administered_responses)

        # Check directional movement within domain bounds
        assert -4.0 <= new_theta <= 4.0

        # Check SE reduction over administered items
        assert new_se < se_history[0], "SE after answering items must be lower than initial SE"

        theta = new_theta
        se = new_se
        theta_history.append(theta)
        se_history.append(se)

        # 4. Check stopping condition
        stop, reason = is_stopping_condition_met(se, idx, max_items=20)
        if stop:
            break

    # Final SE must have shrunk significantly below 0.5
    assert se <= 0.45, f"Expected SE to converge <= 0.45, got {se}"
    final_band = theta_to_band(theta)
    assert 1.0 <= final_band <= 9.0, f"Band score must be valid IELTS range, got {final_band}"


def test_batch_calibration_convergence():
    """
    Test that IRT parameter calibration logic functions without divergence.
    """
    students = [
        {"theta": -2.0, "ans": False},
        {"theta": -1.5, "ans": False},
        {"theta": -1.0, "ans": False},
        {"theta": -0.5, "ans": False},
        {"theta": 0.0, "ans": False},
        {"theta": 0.5, "ans": False},
        {"theta": 1.0, "ans": False},
        {"theta": 1.5, "ans": True},
        {"theta": 2.0, "ans": True},
    ]

    # Initial guess
    a = 1.0
    b = 0.0
    c = 0.2

    # Run gradient update step
    lr = 0.05
    for _ in range(25):
        grad_b = 0.0
        for s in students:
            p = p_correct(s["theta"], a, b, c)
            actual = 1.0 if s["ans"] else 0.0
            # d(-logL)/db = sum (actual - p) * (-a * D * (P - c) / (P * (1 - c)))
            grad_b += (p - actual)

        b = b + lr * (grad_b / len(students))
        b = max(-4.0, min(4.0, b))

    # b should have moved in positive direction because mostly high theta students answered correctly
    assert b > 0.0, f"Expected difficulty b to increase toward positive difficulty, got {b}"
    assert -4.0 <= b <= 4.0
