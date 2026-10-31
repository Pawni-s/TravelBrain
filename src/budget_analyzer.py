"""Explainable profile-weighted budget analysis for TravelBrain.

Amounts are estimates in INR. This module deliberately does not claim to fetch live prices
or train a machine-learning model; it uses deterministic, inspectable optimization rules.
"""
from math import isfinite

COST_FIELDS = {
    "travel": "Travel",
    "accommodation": "Accommodation",
    "food": "Food",
    "local_transport": "Local transport",
    "activities": "Activities & sightseeing",
    "miscellaneous": "Miscellaneous",
}

# Relative priorities, not claims about what a trip will actually cost. Normalized at runtime.
PROFILE_WEIGHTS = {
    "balanced": {"travel": 0.20, "accommodation": 0.25, "food": 0.15, "local_transport": 0.10, "activities": 0.20, "miscellaneous": 0.10},
    "luxury": {"travel": 0.15, "accommodation": 0.35, "food": 0.20, "local_transport": 0.05, "activities": 0.15, "miscellaneous": 0.10},
    "adventure": {"travel": 0.20, "accommodation": 0.12, "food": 0.12, "local_transport": 0.10, "activities": 0.36, "miscellaneous": 0.10},
    "culture": {"travel": 0.18, "accommodation": 0.20, "food": 0.14, "local_transport": 0.10, "activities": 0.28, "miscellaneous": 0.10},
    "food": {"travel": 0.15, "accommodation": 0.18, "food": 0.35, "local_transport": 0.08, "activities": 0.14, "miscellaneous": 0.10},
    "family": {"travel": 0.20, "accommodation": 0.28, "food": 0.18, "local_transport": 0.10, "activities": 0.14, "miscellaneous": 0.10},
}
DEFAULT_RESERVE_RATE = 0.10
CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "د.إ ", "JPY": "¥"}
SUPPORTED_CURRENCIES = tuple(CURRENCY_SYMBOLS)
CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "AED": "د.إ ", "JPY": "¥"}
SUPPORTED_CURRENCIES = tuple(CURRENCY_SYMBOLS)


def _number(value, label, *, allow_zero=True):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number.")
    if not isfinite(number) or number < 0 or (not allow_zero and number == 0):
        qualifier = "greater than zero" if not allow_zero else "a finite, non-negative number"
        raise ValueError(f"{label} must be {qualifier}.")
    return number


def analyze_budget(budget, costs, profile="balanced", reserve_rate=DEFAULT_RESERVE_RATE, currency="INR", trip_context=None, duration_days=None):
    """Analyze entered estimates and provide profile-specific targets and trade-offs.

    ``budget`` is treated as a soft limit: the analyzer identifies the overrun and suggests
    reductions, but does not silently delete or alter user-entered costs.
    """
    budget = _number(budget, "Budget", allow_zero=False)
    currency = str(currency or "INR").upper()
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(f"Unsupported currency {currency}. Choose one of: {', '.join(SUPPORTED_CURRENCIES)}.")
    symbol = CURRENCY_SYMBOLS[currency]
    profile = str(profile or "balanced").strip().lower()
    if profile not in PROFILE_WEIGHTS:
        raise ValueError(f"Unknown travel profile '{profile}'. Choose one of: {', '.join(PROFILE_WEIGHTS)}.")
    reserve_rate = _number(reserve_rate, "Reserve rate")
    if reserve_rate >= 1:
        raise ValueError("Reserve rate must be less than 1.")
    if not isinstance(costs, dict):
        raise ValueError("Costs must be an object of category amounts.")

    normalized = {}
    for key, label in COST_FIELDS.items():
        normalized[key] = round(_number(costs.get(key, 0), f"{label} cost"), 2)

    total = round(sum(normalized.values()), 2)
    remaining = round(budget - total, 2)
    over_budget = total > budget
    planned_budget = round(budget * (1 - reserve_rate), 2)
    reserve_amount = round(budget * reserve_rate, 2)
    weights = PROFILE_WEIGHTS[profile]
    allocation = []
    for key, label in COST_FIELDS.items():
        target = round(planned_budget * weights[key], 2)
        allocation.append({
            "key": key,
            "label": label,
            "weight": weights[key],
            "target": target,
            "entered": normalized[key],
            "difference": round(normalized[key] - target, 2),
        })

    recommendations = []
    if over_budget:
        overrun = round(total - budget, 2)
        # Recommend reviewing lower-priority categories first, while retaining user control.
        candidates = sorted(
            (item for item in allocation if normalized[item["key"]] > 0),
            key=lambda item: (weights[item["key"]], -normalized[item["key"]]),
        )
        if candidates:
            first = candidates[0]
            recommendations.append(
                f"Your estimates exceed the budget by {symbol}{overrun:,.2f}. For the {profile} profile, "
                f"review {first['label'].lower()} first: its entered estimate is "
                f"{symbol}{first['entered']:,.2f} versus a profile target of {symbol}{first['target']:,.2f}. "
                "Compare alternatives before reducing a category that matters to you."
            )
        else:
            recommendations.append(f"Your estimates exceed the budget by {symbol}{overrun:,.2f}; review one or more categories.")
    else:
        recommendations.append(
            f"Your estimates are {symbol}{remaining:,.2f} below the total budget. The {profile} profile "
            f"targets {symbol}{planned_budget:,.2f} for planned expenses and reserves {symbol}{reserve_amount:,.2f} "
            "for unexpected costs. Treat targets as guidance, not mandatory spending."
        )

    largest_deviation = max(allocation, key=lambda item: abs(item["difference"]))
    if abs(largest_deviation["difference"]) >= 1:
        direction = "above" if largest_deviation["difference"] > 0 else "below"
        recommendations.append(
            f"Largest difference from the profile target: {largest_deviation['label']} is "
            f"{symbol}{abs(largest_deviation['difference']):,.2f} {direction} its suggested allocation."
        )

    return {
        "currency": currency,
        "currency_symbol": symbol,
        "trip_context": str(trip_context or "").strip()[:1200],
        "duration_days": duration_days,
        "budget": round(budget, 2),
        "total": total,
        "remaining": remaining,
        "over_budget": over_budget,
        "profile": profile,
        "reserve_rate": reserve_rate,
        "reserve_amount": reserve_amount,
        "planned_budget": planned_budget,
        "breakdown": [{"key": key, "label": label, "amount": normalized[key]} for key, label in COST_FIELDS.items()],
        "allocation": allocation,
        "recommendations": recommendations,
        "method": "Deterministic profile-weighted allocation with soft-budget constraint checks",
        "disclaimer": f"All amounts are shown in {currency}. Estimates are not live quotes and are not automatically converted from another currency. Profile targets are adjustable planning guidance, not predictions or booking prices.",
    }
