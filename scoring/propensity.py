"""
scoring/propensity.py
=====================
Turn the trained PU-model probability into a 0–100 Conversion Propensity Score
(CPS) suitable for tiering and ranking.

The calibrated probabilities are heavily skewed by the low customer base rate, so
raw values crush everyone against 0. For prioritization we use the *percentile
rank* of the PU probability (balanced, rankable), while keeping the raw modeled
probability for honest display.
"""

import pandas as pd

from scoring.config import PU_PRIMARY_COLUMN, PU_DISPLAY_COLUMN, PROPENSITY_AS_PERCENTILE


def compute_propensity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add two columns to a copy of df:
        propensity_score  : 0–100 conversion axis used for tiering (percentile rank
                            of the PU probability, or the scaled probability)
        propensity_prob   : the raw modeled probability (for display, as a fraction)
    Requires PU_PRIMARY_COLUMN to be present.
    """
    df = df.copy()
    if PU_PRIMARY_COLUMN not in df.columns:
        raise KeyError(f"PU column '{PU_PRIMARY_COLUMN}' not found in Maps data")

    prob = pd.to_numeric(df[PU_PRIMARY_COLUMN], errors="coerce").fillna(0.0)
    df["propensity_prob"] = pd.to_numeric(
        df.get(PU_DISPLAY_COLUMN, prob), errors="coerce").fillna(0.0).round(4)

    if PROPENSITY_AS_PERCENTILE:
        # percentile rank in [0,100]; ties share the average rank
        df["propensity_score"] = (prob.rank(pct=True) * 100).round(1)
    else:
        df["propensity_score"] = (prob.clip(0, 1) * 100).round(1)

    return df
