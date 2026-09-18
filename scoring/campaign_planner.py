"""
scoring/campaign_planner.py
===========================
Turn a prospect's tier + reachability into a concrete marketing action:
    - primary channel   (the cheapest channel they're actually reachable on)
    - budget band        (High / Medium / Low / None) + a TND range
    - touch cadence
    - a short human-readable rationale

This is what answers "where do we spend most and least money" at the row level.
"""

from scoring.config import CAMPAIGN_PLAN, BUDGET_BAND_TND
from scoring.models import _has_value, _get, _truthy


def _channel_available(row, channel: str) -> bool:
    """Is a given channel usable for this prospect, given its contact signals?"""
    has_phone   = _has_value(_get(row, "maps_phone")) or _truthy(_get(row, "callable_prospect", False))
    has_website = _has_value(_get(row, "maps_website"))
    has_email   = _has_value(_get(row, "maps_email")) or _has_value(_get(row, "email"))
    has_geo     = _has_value(_get(row, "maps_lat")) or _has_value(_get(row, "city")) \
                  or _has_value(_get(row, "governorate"))

    return {
        "field_sales": has_geo,       # need a location to visit
        "tele_sales":  has_phone,     # need a phone
        "email":       has_email or has_website,  # website → contact form / discoverable email
        "sms":         has_phone,
        "social":      True,          # broad targeting works without direct contact
        "none":        True,
    }.get(channel, False)


def plan_campaign(row, tier_key: str) -> dict:
    """
    Build the campaign plan for one prospect.

    Returns a dict:
        {
          "channel":       "tele_sales",
          "budget_band":   "High",
          "budget_tnd":    "150–400",
          "cadence":       "Weekly, personalized",
          "rationale":     "...",
        }
    """
    plan = CAMPAIGN_PLAN.get(tier_key, CAMPAIGN_PLAN["D"])

    # Pick the first preferred channel the prospect is actually reachable on.
    chosen = "none"
    for channel in plan["channel_options"]:
        if _channel_available(row, channel):
            chosen = channel
            break

    band = plan["budget_band"]
    # A high-value prospect we cannot reach on any direct channel gets nudged toward
    # social/awareness at a lower band — you can't pour field-sales money at a company
    # with no contact path.
    if chosen in ("none", "social") and band == "High":
        band = "Medium"

    return {
        "channel":     chosen,
        "budget_band": band,
        "budget_tnd":  BUDGET_BAND_TND.get(band, "0"),
        "cadence":     plan["cadence"],
        "rationale":   plan["note"],
    }
