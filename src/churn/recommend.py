"""Personalised retention recommendation engine.

The engine combines model evidence (risk level + SHAP drivers) with a curated
retention playbook.  It is deliberately rule based: every suggestion is
auditable, which matters for customer-facing retention decisions.  Priority
scores order the playbook for a given customer, they are *not* calibrated
uplift estimates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .risk import priority_label


@dataclass(frozen=True)
class Recommendation:
    id: str
    category: str
    title: str
    description: str
    action: str
    offer: str
    priority: str
    priority_score: int
    expected_impact: str
    channels: list[str] = field(default_factory=list)
    triggered_by: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "action": self.action,
            "offer": self.offer,
            "priority": self.priority,
            "priority_score": self.priority_score,
            "expected_impact": self.expected_impact,
            "channels": list(self.channels),
            "triggered_by": list(self.triggered_by),
        }


def _get(profile: Mapping[str, Any], key: str, default: Any = None) -> Any:
    value = profile.get(key, default)
    return default if value is None else value


def _is(profile: Mapping[str, Any], key: str, value: str) -> bool:
    return str(_get(profile, key, "")).strip().lower() == value.lower()


def _num(profile: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(_get(profile, key, default))
    except (TypeError, ValueError):
        return default


def _risk_boost(risk_level: str) -> int:
    if risk_level == "high":
        return 20
    if risk_level == "medium":
        return 10
    return 0


def _driver_boost(source: str, top_sources: list[str], all_sources: set[str]) -> int:
    if source in top_sources[:3]:
        return 25
    if source in all_sources:
        return 10
    return 0


def recommend(
    profile: Mapping[str, Any],
    probability: float,
    risk_level: str,
    top_drivers: list[dict[str, Any]] | None = None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return up to ``limit`` ranked retention actions for one customer."""
    top_drivers = top_drivers or []
    all_sources = {str(d.get("source", "")) for d in top_drivers}
    ordered_sources = [str(d.get("source", "")) for d in top_drivers]
    limit = max(1, min(int(limit), 8))

    tenure = _num(profile, "tenure")
    monthly = _num(profile, "MonthlyCharges")
    internet = str(_get(profile, "InternetService", "No"))
    has_internet = internet in {"DSL", "Fiber optic"}
    high_risk = risk_level == "high"
    medium_or_higher = risk_level in {"medium", "high"}
    contract = str(_get(profile, "Contract", "Month-to-month"))
    payment = str(_get(profile, "PaymentMethod", ""))
    senior = _num(profile, "SeniorCitizen") >= 1
    paperless = _is(profile, "PaperlessBilling", "Yes")
    tech_support = str(_get(profile, "TechSupport", "No"))
    online_security = str(_get(profile, "OnlineSecurity", "No"))
    device_protection = str(_get(profile, "DeviceProtection", "No"))
    streaming_count = sum(_is(profile, c, "Yes") for c in ("StreamingTV", "StreamingMovies"))
    base = 50 + _risk_boost(risk_level)
    candidates: list[Recommendation] = []

    def add(
        *,
        rec_id: str,
        category: str,
        title: str,
        description: str,
        action: str,
        offer: str,
        impact: str,
        channels: list[str],
        trigger: str,
        source: str | None = None,
        bonus: int = 0,
        triggered_by: list[str] | None = None,
    ) -> None:
        score = base + (bonus or 0)
        if source:
            score += _driver_boost(source, ordered_sources, all_sources)
        score = max(0, min(int(score), 99))
        candidates.append(
            Recommendation(
                id=rec_id,
                category=category,
                title=title,
                description=description,
                action=action,
                offer=offer,
                priority=priority_label(score),
                priority_score=score,
                expected_impact=impact,
                channels=channels,
                triggered_by=triggered_by or [trigger],
            )
        )

    # 1. Proactive outreach — always relevant for a scored customer.
    add(
        rec_id="RET-01",
        category="engagement",
        title="Proactive retention outreach",
        description=(
            "A retention specialist contacts the customer to understand pain points "
            "and reinforce the value they receive before the renewal window closes."
        ),
        action="Schedule a 15-minute retention call within 48 hours.",
        offer="Dedicated retention specialist + service review.",
        impact="High - early contact recovers at-risk customers before they shop around.",
        channels=["phone", "email"],
        trigger="Model risk score",
        bonus=6 if high_risk else 0,
    )

    # 2. Contract conversion.
    if contract.lower() == "month-to-month":
        add(
            rec_id="RET-02",
            category="contract",
            title="Convert to an annual contract",
            description=(
                "Month-to-month customers can leave at any time. A 12- or 24-month "
                "plan with a loyalty rate lowers price anxiety and locks in revenue."
            ),
            action="Offer a 12-month plan with a 15% loyalty discount (24-month: 20%).",
            offer="15-20% off for 12-24 months with a commitment plan.",
            impact="High - contract conversion is the strongest retention lever in telco.",
            channels=["phone", "email"],
            trigger=f"Contract = {contract}",
            source="Contract",
            bonus=10 if high_risk else 4,
        )

    # 3. Fiber pricing review.
    if internet == "Fiber optic" and monthly >= 70:
        add(
            rec_id="RET-03",
            category="pricing",
            title="Personalised fiber plan review",
            description=(
                "High monthly charges for fiber are a recurring churn driver. "
                "Re-price the plan or right-size the speed tier to match usage."
            ),
            action="Audit the plan against usage and offer a loyalty credit.",
            offer="$10-20/month loyalty credit or a lower-cost speed tier.",
            impact="High - addresses the most common price-related churn driver.",
            channels=["phone"],
            trigger=f"Fiber optic with ${monthly:.0f}/month charges",
            source="MonthlyCharges",
            bonus=8 if high_risk else 0,
            triggered_by=["InternetService", "MonthlyCharges"],
        )

    # 4. Payment friction.
    if payment.lower() == "electronic check":
        add(
            rec_id="RET-04",
            category="payment",
            title="Migrate to autopay",
            description=(
                "Electronic-check customers churn more often, partly due to billing "
                "friction. Autopay reduces missed payments and increases stickiness."
            ),
            action="Switch to credit card or bank autopay with assisted setup.",
            offer="5% bill credit for 6 months after the first autopay payment.",
            impact="Medium-High - improves payment reliability and reduces churn.",
            channels=["email", "sms"],
            trigger="Payment method = Electronic check",
            source="PaymentMethod",
            bonus=4,
        )

    # 5. Tech support.
    if has_internet and tech_support.lower() == "no":
        add(
            rec_id="RET-05",
            category="service",
            title="Complimentary tech support",
            description=(
                "Customers without tech support resolve issues on their own and "
                "associate recurring problems with the service. A support trial "
                "raises perceived value and creates a support habit."
            ),
            action="Enable TechSupport and book a setup call.",
            offer="3 months of TechSupport free.",
            impact="Medium - reduces problem-driven churn for internet customers.",
            channels=["phone", "email"],
            trigger="TechSupport = No",
            source="TechSupport",
            bonus=2,
        )

    # 6. Security bundle.
    if has_internet and online_security.lower() == "no":
        add(
            rec_id="RET-06",
            category="service",
            title="Security add-on trial",
            description=(
                "Online security increases service depth and protects the customer. "
                "Bundling it also raises switching costs."
            ),
            action="Add OnlineSecurity and walk the customer through activation.",
            offer="Free OnlineSecurity for 3 months, then bundled rate.",
            impact="Medium - increases product adoption and reduces churn.",
            channels=["email"],
            trigger="OnlineSecurity = No",
            source="OnlineSecurity",
            bonus=0,
        )

    # 7. Early-life onboarding.
    if tenure <= 6:
        add(
            rec_id="RET-07",
            category="engagement",
            title="New-customer onboarding programme",
            description=(
                "The first six months carry the highest churn risk. Structured "
                "onboarding fixes setup problems before they become reasons to leave."
            ),
            action="Welcome call at day 7 and a service check-in at day 30.",
            offer="Onboarding concierge + first-bill walkthrough.",
            impact="High - early engagement measurably improves first-year retention.",
            channels=["phone", "email"],
            trigger=f"Tenure = {int(tenure)} months",
            source="tenure",
            bonus=6,
        )

    # 8. Loyalty recognition.
    if tenure >= 24:
        add(
            rec_id="RET-08",
            category="loyalty",
            title="Loyalty recognition",
            description=(
                "Long-tenured customers who are now at risk often feel undervalued. "
                "Recognise their history and review their price against new-customer offers."
            ),
            action="Apply loyalty pricing and assign a named account contact.",
            offer="Loyalty price review + dedicated account manager.",
            impact="Medium-High - protects high-CLV customers from competitor offers.",
            channels=["phone"],
            trigger=f"Tenure = {int(tenure)} months",
            source="tenure",
            bonus=3,
        )

    # 9. Senior customer support.
    if senior:
        add(
            rec_id="RET-09",
            category="service",
            title="Priority human support",
            description=(
                "Senior customers value simple, human-assisted service. "
                "Removing support friction lowers frustration-driven churn."
            ),
            action="Register the customer for the priority support line.",
            offer="Priority support line and simplified billing.",
            impact="Medium - improves experience and reduces support-related churn.",
            channels=["phone"],
            trigger="SeniorCitizen = 1",
            source="SeniorCitizen",
            bonus=2,
        )

    # 10. Billing clarity.
    if paperless and monthly >= 75:
        add(
            rec_id="RET-10",
            category="billing",
            title="Bill clarity review",
            description=(
                "High paperless bills with add-ons can feel opaque. "
                "An itemised review removes bill-shock and surfaces savings."
            ),
            action="Send an itemised bill breakdown and offer a paper bill option.",
            offer="Bill audit + one-time $10 credit.",
            impact="Medium - reduces bill-shock churn.",
            channels=["email"],
            trigger="Paperless billing with high monthly charges",
            source="PaperlessBilling",
            bonus=0,
        )

    # 11. Streaming bundle.
    if streaming_count == 2 and monthly >= 80:
        add(
            rec_id="RET-11",
            category="pricing",
            title="Entertainment bundle optimisation",
            description=(
                "Two streaming add-ons on a high bill invite comparisons with "
                "streaming-first competitors. A bundled rate protects the spend."
            ),
            action="Bundle StreamingTV and StreamingMovies at a packaged rate.",
            offer="Bundle discount on both streaming add-ons.",
            impact="Medium - improves value perception while protecting ARPU.",
            channels=["email"],
            trigger="StreamingTV + StreamingMovies on a high bill",
            source="StreamingServices",
            bonus=0,
            triggered_by=["StreamingTV", "StreamingMovies", "MonthlyCharges"],
        )

    # 12. Device protection.
    if has_internet and device_protection.lower() == "no" and tenure > 6:
        add(
            rec_id="RET-12",
            category="service",
            title="Device protection trial",
            description=(
                "Device protection adds everyday value and another reason to stay. "
                "A trial gives the customer a reason to re-evaluate the bundle."
            ),
            action="Offer a DeviceProtection trial with a simple claims walkthrough.",
            offer="6 months of DeviceProtection free.",
            impact="Low-Medium - lifts service depth without a large discount.",
            channels=["email"],
            trigger="DeviceProtection = No",
            source="DeviceProtection",
            bonus=0,
        )

    # 13. Save offer for the highest-risk customers.
    if probability >= 0.65:
        add(
            rec_id="RET-13",
            category="pricing",
            title="Targeted save offer",
            description=(
                "For customers with a high churn probability, a short, time-bound "
                "discount creates a reason to stay while the retention team works on "
                "the underlying driver."
            ),
            action="Send a personalised save offer valid for 7 days.",
            offer="20% off for 3 months, conditional on speaking with retention.",
            impact="High - immediate save lever, use only for high-risk customers.",
            channels=["phone", "email"],
            trigger=f"Churn probability = {probability:.0%}",
            bonus=12,
        )

    if not medium_or_higher:
        # Keep low-risk customers in a nurture track rather than discounting them.
        candidates = [rec for rec in candidates if rec.category != "pricing"]
        add(
            rec_id="RET-14",
            category="engagement",
            title="Loyalty nurture track",
            description=(
                "The customer is currently low risk. Maintain engagement with "
                "value-led communication instead of discounts."
            ),
            action="Add to the quarterly loyalty newsletter and satisfaction survey.",
            offer="Loyalty rewards programme invitation.",
            impact="Low - cost-efficient relationship maintenance.",
            channels=["email"],
            trigger=f"Low churn probability ({probability:.0%})",
            bonus=0,
        )

    # Rank: priority score, then category specificity, then id for determinism.
    seen: set[str] = set()
    ranked: list[Recommendation] = []
    for rec in sorted(candidates, key=lambda r: (-r.priority_score, r.id)):
        if rec.id in seen:
            continue
        seen.add(rec.id)
        ranked.append(rec)
        if len(ranked) >= limit:
            break
    return [rec.as_dict() for rec in ranked]


def recommendation_summary(recs: list[dict[str, Any]], risk_level: str) -> str:
    """One-line summary suitable for a dashboard card."""
    if not recs:
        return "No retention action required at this time."
    top = recs[0]["title"]
    return (
        f"{risk_level.capitalize()} churn risk. Start with: {top} ({len(recs)} actions suggested)."
    )
