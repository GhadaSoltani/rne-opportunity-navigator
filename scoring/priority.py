"""
scoring/priority.py
===================
Blend value + conversion into a priority score, then place each prospect on the
value × propensity grid to get its action tier.

    A — Strategic          high value, high propensity → invest most
    B — High-value nurture high value, low  propensity → warm up
    C — Efficient          low  value, high propensity → cheap automation
    D — Monitor            low  value, low  propensity → minimal spend
"""

from scoring.config import (
    PRIORITY_VALUE_WEIGHT, TIER_VALUE_THRESHOLD, TIER_PROPENSITY_THRESHOLD, TIER_LABELS,
)


def priority_score(value: float, conversion: float) -> float:
    w = PRIORITY_VALUE_WEIGHT
    return round(w * value + (1 - w) * conversion, 2)


def assign_tier(value: float, conversion: float) -> tuple[str, str]:
    high_value = value >= TIER_VALUE_THRESHOLD
    high_conv  = conversion >= TIER_PROPENSITY_THRESHOLD
    key = "A" if (high_value and high_conv) else \
          "B" if (high_value and not high_conv) else \
          "C" if (not high_value and high_conv) else "D"
    return key, TIER_LABELS[key]
