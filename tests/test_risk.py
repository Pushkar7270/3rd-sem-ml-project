"""Tests for risk banding and financial estimates."""

from __future__ import annotations

import pytest

from churn import config
from churn.risk import (
    bands_from_details,
    financial_impact,
    priority_label,
    probability_to_risk,
    risk_band_details,
    risk_bands_for_threshold,
)


@pytest.mark.parametrize(
    ("probability", "expected"),
    [
        (0.0, "low"),
        (0.20, "low"),
        (0.3499, "low"),
        (0.35, "medium"),
        (0.45, "medium"),
        (0.5999, "medium"),
        (0.60, "high"),
        (0.918, "high"),
        (1.0, "high"),
    ],
)
def test_probability_to_risk_boundaries(probability, expected):
    assert probability_to_risk(probability) == expected


def test_dynamic_bands_align_with_threshold():
    bands = risk_bands_for_threshold(0.33)
    assert bands[0] == ("low", 0.0, 0.33)
    assert bands[1][0] == "medium" and bands[1][1] == 0.33
    assert probability_to_risk(0.33, bands) == "medium"
    assert probability_to_risk(0.3299, bands) == "low"
    assert probability_to_risk(0.60, bands) == "high"
    details = risk_band_details(bands)
    assert details[0]["max_probability"] == 0.33
    assert bands_from_details(details) == bands


def test_bands_from_details_includes_probability_one():
    details = risk_band_details(risk_bands_for_threshold(0.4))
    bands = bands_from_details(details)
    assert probability_to_risk(1.0, bands) == "high"
    assert bands[-1][2] > 1.0


@pytest.mark.parametrize("probability", [-0.01, 1.01, 2.0])
def test_probability_to_risk_rejects_invalid_values(probability):
    with pytest.raises(ValueError):
        probability_to_risk(probability)


def test_risk_band_details_cover_full_range():
    bands = risk_band_details()
    assert [band["level"] for band in bands] == ["low", "medium", "high"]
    assert bands[0]["min_probability"] == 0.0
    assert bands[-1]["max_probability"] == 1.0
    assert bands[0]["color"] == config.RISK_COLORS["low"]


def test_financial_impact_at_half_probability():
    impact = financial_impact(100.0, 0.5)
    assert impact["monthly_charges"] == 100.0
    assert impact["annual_revenue_at_risk"] == 600.0  # 100 * 12 * 0.5
    assert impact["expected_remaining_months"] == 2.0
    assert impact["estimated_clv"] == 200.0


def test_financial_impact_zero_probability_caps_tenure():
    impact = financial_impact(100.0, 0.0)
    assert impact["annual_revenue_at_risk"] == 0.0
    assert impact["expected_remaining_months"] == config.MAX_EXPECTED_REMAINING_MONTHS
    assert impact["estimated_clv"] == 100.0 * config.MAX_EXPECTED_REMAINING_MONTHS


def test_financial_impact_certain_churn():
    impact = financial_impact(80.0, 1.0)
    assert impact["annual_revenue_at_risk"] == 960.0
    assert impact["expected_remaining_months"] == 1.0
    assert impact["estimated_clv"] == 80.0


def test_financial_impact_clamps_negative_monthly_charges():
    impact = financial_impact(-50.0, 0.5)
    assert impact["monthly_charges"] == 0.0
    assert impact["annual_revenue_at_risk"] == 0.0


@pytest.mark.parametrize(
    ("score", "label"),
    [(99, "critical"), (85, "critical"), (84, "high"), (70, "high"), (69, "medium"), (0, "medium")],
)
def test_priority_labels(score, label):
    assert priority_label(score) == label
