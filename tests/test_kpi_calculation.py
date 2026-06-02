"""
Unit tests for the Lotus KPI Calculation Engine.

Tests the scoring formula against the sample data from the spec:
- Total expected score: 0.872
- Total expected bonus: 13,080,000 VND
"""

import pytest
from decimal import Decimal
from app.services.kpi.calculation_service import KPICalculationService
from app.models.kpi import MetricUnit


calc = KPICalculationService()


class TestMetricScoreCalculation:
    """Test individual metric scoring formula."""

    # ----- PERCENT / SCORE unit tests -----

    def test_a1_below_minimum(self):
        """A1: actual=0.31, min=0.4, max=1.0, weight=0.12 → 0 (below min)"""
        score = calc.calculate_metric_score(
            actual=Decimal("0.31"),
            target_min=Decimal("0.4"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.12"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0"), f"Expected 0, got {score}"

    def test_a2_linear_interpolation(self):
        """A2: actual=0.06, min=0, max=0.1, weight=0.02 → 0.012"""
        score = calc.calculate_metric_score(
            actual=Decimal("0.06"),
            target_min=Decimal("0"),
            target_max=Decimal("0.1"),
            weight=Decimal("0.02"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.0120"), f"Expected 0.0120, got {score}"

    def test_a3_full_score(self):
        """A3: actual=1.0, min=0.9, max=1.0, weight=0.08 → 0.08 (full)"""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0.9"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.08"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.08"), f"Expected 0.08, got {score}"

    def test_a4_full_score(self):
        """A4: actual=1.0, min=0.8, max=1.0, weight=0.08 → 0.08"""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0.8"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.08"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.08"), f"Expected 0.08, got {score}"

    def test_a5_full_score(self):
        """A5: actual=1.0, min=0.9, max=1.0, weight=0.08 → 0.08"""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0.9"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.08"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.08"), f"Expected 0.08, got {score}"

    def test_b1_full_score(self):
        """B1: actual=1.0, min=0.5, max=1.0, weight=0.15 → 0.15"""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0.5"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.15"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.15"), f"Expected 0.15, got {score}"

    def test_b2_full_score(self):
        """B2: actual=1.0, min=0.5, max=1.0, weight=0.15 → 0.15"""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0.5"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.15"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.15"), f"Expected 0.15, got {score}"

    def test_c1_full_score(self):
        """C1: actual=1.0, min=0.7, max=1.0, weight=0.20 → 0.20"""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0.7"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.20"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.20"), f"Expected 0.20, got {score}"

    def test_d2_full_score(self):
        """D2: actual=1.0, min=0.7, max=1.0, weight=0.05 → 0.05"""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0.7"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.05"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0.05"), f"Expected 0.05, got {score}"

    # ----- COUNT / STUDENT unit tests -----

    def test_a6_full_score_student(self):
        """A6: actual=2, min=0, max=2, weight=0.02 → 0.02 (student unit)"""
        score = calc.calculate_metric_score(
            actual=Decimal("2"),
            target_min=Decimal("0"),
            target_max=Decimal("2"),
            weight=Decimal("0.02"),
            unit=MetricUnit.STUDENT,
        )
        assert score == Decimal("0.02"), f"Expected 0.02, got {score}"

    def test_d1_full_score_count(self):
        """D1: actual=2, min=0, max=2, weight=0.025 → 0.025 (count unit)"""
        score = calc.calculate_metric_score(
            actual=Decimal("2"),
            target_min=Decimal("0"),
            target_max=Decimal("2"),
            weight=Decimal("0.025"),
            unit=MetricUnit.COUNT,
        )
        assert score == Decimal("0.025"), f"Expected 0.025, got {score}"

    def test_d3_full_score_count(self):
        """D3: actual=5, min=0, max=5, weight=0.025 → 0.025 (count unit)"""
        score = calc.calculate_metric_score(
            actual=Decimal("5"),
            target_min=Decimal("0"),
            target_max=Decimal("5"),
            weight=Decimal("0.025"),
            unit=MetricUnit.COUNT,
        )
        assert score == Decimal("0.025"), f"Expected 0.025, got {score}"

    def test_count_partial(self):
        """Count partial: actual=1, max=2, weight=0.025 → 0.0125"""
        score = calc.calculate_metric_score(
            actual=Decimal("1"),
            target_min=Decimal("0"),
            target_max=Decimal("2"),
            weight=Decimal("0.025"),
            unit=MetricUnit.COUNT,
        )
        assert score == Decimal("0.0125"), f"Expected 0.0125, got {score}"

    def test_count_zero(self):
        """Count zero: actual=0, max=5, weight=0.025 → 0"""
        score = calc.calculate_metric_score(
            actual=Decimal("0"),
            target_min=Decimal("0"),
            target_max=Decimal("5"),
            weight=Decimal("0.025"),
            unit=MetricUnit.COUNT,
        )
        assert score == Decimal("0"), f"Expected 0, got {score}"

    def test_count_over_max(self):
        """Count over max: actual=10, max=5, weight=0.025 → 0.025 (capped)"""
        score = calc.calculate_metric_score(
            actual=Decimal("10"),
            target_min=Decimal("0"),
            target_max=Decimal("5"),
            weight=Decimal("0.025"),
            unit=MetricUnit.COUNT,
        )
        assert score == Decimal("0.025"), f"Expected 0.025, got {score}"

    # ----- Edge cases -----

    def test_percent_at_exact_min(self):
        """At exact min: actual=0.4, min=0.4, max=1.0, weight=0.12 → 0 (not >= max, but = min)."""
        score = calc.calculate_metric_score(
            actual=Decimal("0.4"),
            target_min=Decimal("0.4"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.12"),
            unit=MetricUnit.PERCENT,
        )
        # At min → interpolation = weight × (0.4-0.4)/(1.0-0.4) = 0
        assert score == Decimal("0"), f"Expected 0, got {score}"

    def test_percent_just_above_min(self):
        """Just above min: actual=0.41, min=0.4, max=1.0, weight=0.12."""
        score = calc.calculate_metric_score(
            actual=Decimal("0.41"),
            target_min=Decimal("0.4"),
            target_max=Decimal("1.0"),
            weight=Decimal("0.12"),
            unit=MetricUnit.PERCENT,
        )
        # weight × (0.41-0.4)/(1.0-0.4) = 0.12 × 0.01/0.6 = 0.002
        assert score == Decimal("0.0020"), f"Expected 0.0020, got {score}"

    def test_zero_weight(self):
        """Weight = 0 → always 0."""
        score = calc.calculate_metric_score(
            actual=Decimal("1.0"),
            target_min=Decimal("0"),
            target_max=Decimal("1"),
            weight=Decimal("0"),
            unit=MetricUnit.PERCENT,
        )
        assert score == Decimal("0"), f"Expected 0, got {score}"


class TestTotalScoreCalculation:
    """
    Test total score calculation against the spec example.

    Sample data from the spec:
    A1: 0.31 (0), A2: 0.06 (0.012), A3: 1.0 (0.08), A4: 1.0 (0.08),
    A5: 1.0 (0.08), A6: 2 (0.02), B1: 1.0 (0.15), B2: 1.0 (0.15),
    C1: 1.0 (0.20), D1: 2 (0.025), D2: 1.0 (0.05), D3: 5 (0.025)
    
    Total = 0.872
    Bonus = 15,000,000 × 0.872 = 13,080,000
    
    NOTE: The weights in the template use pre-computed values where
    metric_weight = weight_in_group × group_weight. E.g. A1: 0.3 × 0.4 = 0.12
    """

    METRICS = [
        # (actual, min, max, weight, unit)
        (Decimal("0.31"), Decimal("0.4"), Decimal("1.0"), Decimal("0.12"), MetricUnit.PERCENT),    # A1
        (Decimal("0.06"), Decimal("0.0"), Decimal("0.1"), Decimal("0.02"), MetricUnit.PERCENT),    # A2
        (Decimal("1.0"),  Decimal("0.9"), Decimal("1.0"), Decimal("0.08"), MetricUnit.PERCENT),    # A3
        (Decimal("1.0"),  Decimal("0.8"), Decimal("1.0"), Decimal("0.08"), MetricUnit.PERCENT),    # A4
        (Decimal("1.0"),  Decimal("0.9"), Decimal("1.0"), Decimal("0.08"), MetricUnit.PERCENT),    # A5
        (Decimal("2"),    Decimal("0"),   Decimal("2"),   Decimal("0.02"), MetricUnit.STUDENT),    # A6
        (Decimal("1.0"),  Decimal("0.5"), Decimal("1.0"), Decimal("0.15"), MetricUnit.PERCENT),    # B1
        (Decimal("1.0"),  Decimal("0.5"), Decimal("1.0"), Decimal("0.15"), MetricUnit.PERCENT),    # B2
        (Decimal("1.0"),  Decimal("0.7"), Decimal("1.0"), Decimal("0.20"), MetricUnit.PERCENT),    # C1
        (Decimal("2"),    Decimal("0"),   Decimal("2"),   Decimal("0.025"), MetricUnit.COUNT),     # D1
        (Decimal("1.0"),  Decimal("0.7"), Decimal("1.0"), Decimal("0.05"), MetricUnit.PERCENT),    # D2
        (Decimal("5"),    Decimal("0"),   Decimal("5"),   Decimal("0.025"), MetricUnit.COUNT),     # D3
    ]

    def test_total_score(self):
        """Verify total score matches spec: 0.872"""
        total = Decimal("0")
        for actual, min_val, max_val, weight, unit in self.METRICS:
            score = calc.calculate_metric_score(actual, min_val, max_val, weight, unit)
            total += score

        # Allow small rounding variance
        assert abs(total - Decimal("0.872")) < Decimal("0.001"), \
            f"Expected ~0.872, got {total}"

    def test_bonus_calculation(self):
        """Verify bonus: 15,000,000 × 0.872 = 13,080,000"""
        total = Decimal("0")
        for actual, min_val, max_val, weight, unit in self.METRICS:
            score = calc.calculate_metric_score(actual, min_val, max_val, weight, unit)
            total += score

        max_bonus = Decimal("15000000")
        bonus = max_bonus * total
        expected_bonus = Decimal("13080000")

        assert abs(bonus - expected_bonus) < Decimal("10000"), \
            f"Expected ~13,080,000, got {bonus}"

    def test_weight_sum_equals_one(self):
        """Verify all weights sum to 1.0."""
        total_weight = sum(w for _, _, _, w, _ in self.METRICS)
        assert total_weight == Decimal("1.000"), f"Expected 1.0, got {total_weight}"


class TestSupportCalcFormula:
    """Test the support calculator A1/A2 formula."""

    def test_basic_calculation(self):
        """Test with spec example: 32 students, 10 above avg, 2 above high."""
        from app.services.kpi.support_calc_service import SupportCalcService
        from app.schemas.kpi import SupportCalcRequest

        svc = SupportCalcService()
        payload = SupportCalcRequest(
            class_size=32,
            max_score=9,
            avg_threshold=4.5,
            above_avg_count=10,
            high_threshold=7.0,
            above_high_count=2,
        )

        result = svc.calculate_rates(payload)
        assert result["rate_above_avg"] == 0.375   # (10+2)/32
        assert result["rate_above_high"] == 0.0625  # 2/32
        assert result["breakdown"]["total_students"] == 32
        assert result["breakdown"]["above_avg_only"] == 10
        assert result["breakdown"]["above_high"] == 2
        assert result["breakdown"]["below_avg"] == 20

    def test_all_above_avg(self):
        """All students above average."""
        from app.services.kpi.support_calc_service import SupportCalcService
        from app.schemas.kpi import SupportCalcRequest

        svc = SupportCalcService()
        payload = SupportCalcRequest(
            class_size=20,
            max_score=10,
            avg_threshold=5.0,
            above_avg_count=15,
            high_threshold=8.0,
            above_high_count=5,
        )

        result = svc.calculate_rates(payload)
        assert result["rate_above_avg"] == 1.0      # (15+5)/20
        assert result["rate_above_high"] == 0.25     # 5/20
