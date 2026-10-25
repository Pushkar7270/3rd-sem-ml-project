"""Risk banding and business value calculations."""

from __future__ import annotations

from typing import Any

from . import config

RiskBand = tuple[str, float, float]


def risk_bands_for_threshold(
    threshold: float,
    *,
    high_floor: float = 0.60,
    high_gap: float = 0.15,
) -> tuple[RiskBand, ...]:
    """Build risk bands whose low/medium boundary equals the decision threshold.

    Keeping the low band strictly below the deployed threshold prevents the
    contradictory case where a customer is both "low risk" and "predicted to
    churn".  The high band stays at 60% unless the threshold is unusually high,
    in which case it moves up with the threshold.
    """
    low_cut = round(min(max(float(threshold), 0.01), 0.95), 4)
    high_cut = round(min(0.99, max(high_floor, low_cut + high_gap)), 4)
    if high_cut <= low_cut:
        high_cut = round(min(0.999, low_cut + 0.05), 4)
    return (
        ("low", 0.0, low_cut),
        ("medium", low_cut, high_cut),
        ("high", high_cut, 1.0001),
    )


def probability_to_risk(probability: float, bands: tuple[RiskBand, ...] | None = None) -> str:
    """Map a churn probability to ``low`` / ``medium`` / ``high``.

    Bands are inclusive on the lower bound and exclusive on the upper bound.
    Callers can pass the model-specific bands stored in the artifact; otherwise
    the project defaults in :mod:`churn.config` are used.
    """
    if not 0.0 <= probability <= 1.0:
        raise ValueError(f"probability must be in [0, 1], got {probability}")
    bands = bands or config.RISK_BANDS
    for name, lower, upper in bands:
        if lower <= probability < upper:
            return name
    return bands[-1][0]


def risk_band_details(bands: tuple[RiskBand, ...] | None = None) -> list[dict[str, Any]]:
    """JSON-friendly band descriptors for the API and model card."""
    bands = bands or config.RISK_BANDS
    return [
        {
            "level": name,
            "min_probability": lower,
            "max_probability": min(upper, 1.0),
            "color": config.RISK_COLORS.get(name, "#757575"),
        }
        for name, lower, upper in bands
    ]


def bands_from_details(details: list[dict[str, Any]]) -> tuple[RiskBand, ...]:
    """Reconstruct the tuple form from artifact metadata.

    The displayed maximum of the last band is 1.0, but the comparison upper
    bound is exclusive, so it is extended slightly to include probability 1.0.
    """
    bands: list[RiskBand] = []
    for index, item in enumerate(details):
        lower = float(item["min_probability"])
        upper = 1.0001 if index == len(details) - 1 else float(item["max_probability"])
        bands.append((str(item["level"]), lower, upper))
    return tuple(bands)


def financial_impact(monthly_charges: float, probability: float) -> dict[str, float]:
    """Estimate revenue exposure and a simple customer lifetime value.

    ``annual_revenue_at_risk`` = monthly charges x 12 x churn probability.

    ``expected_remaining_months`` treats churn as a geometric process, so the
    expected remaining tenure is ``1 / p`` (capped at 72 months).  The CLV
    figure is therefore an upper-bound revenue estimate, excluding margin and
    discounting; it is meant for prioritisation, not accounting.
    """
    monthly = max(float(monthly_charges or 0.0), 0.0)
    probability = min(max(float(probability), 0.0), 1.0)
    if probability <= 0.0:
        remaining = float(config.MAX_EXPECTED_REMAINING_MONTHS)
    else:
        remaining = min(1.0 / probability, float(config.MAX_EXPECTED_REMAINING_MONTHS))
    return {
        "monthly_charges": round(monthly, 2),
        "annual_revenue_at_risk": round(monthly * config.MONTHS_PER_YEAR * probability, 2),
        "expected_remaining_months": round(remaining, 1),
        "estimated_clv": round(monthly * remaining, 2),
    }


def priority_label(score: float) -> str:
    if score >= 85:
        return "critical"
    if score >= 70:
        return "high"
    return "medium"
