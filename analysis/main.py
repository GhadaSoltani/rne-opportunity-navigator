"""
analysis/main.py
================
Entry point for the analysis layer (feature-engineering only).

The recommendation system (offer + score) is intentionally NOT part of this
module — it will be built separately. This file runs cleaning-compatible
feature engineering and writes the analytical CSVs the dashboard reads.

Run directly:
    python -m analysis.main

Or from pipeline/runner.py:
    from analysis.main import run_analysis
    run_analysis(input_csv="data/output/rne_companies_segmented.csv")

Produces in data/output/:
    1. company_features.csv         — every company with all engineered features (v1 + v2)
    2. sector_kpis.csv              — per-sector averages and signal coverage
    3. cohort_summary.csv           — counts per (sector × maturity × capital_tier)
    4. geography_summary.csv        — counts + signal coverage per city
    5. vague_activities_report.csv  — activities producing many "others" rows
    6. governorate_breakdown.csv    — v2: counts + signals per governorate (24 govs)
    7. opportunity_matrix.csv       — v2: size × connectivity_need × business_model
    8. timing_summary.csv           — v2: monthly registration counts (last 24 months)
"""

import logging
from pathlib import Path

import pandas as pd

from analysis.config import (
    ANALYSIS_INPUT_CSV,
    COHORT_SUMMARY_CSV,
    SECTOR_KPIS_CSV,
    VAGUE_ACTIVITIES_CSV,
)
from analysis.feature_engineering import build_all_features

logger = logging.getLogger(__name__)

# Derived output paths (kept here so config.py needs no edit)
FEATURES_CSV         = ANALYSIS_INPUT_CSV.parent / "company_features.csv"
GEOGRAPHY_CSV        = ANALYSIS_INPUT_CSV.parent / "geography_summary.csv"
GOVERNORATE_CSV      = ANALYSIS_INPUT_CSV.parent / "governorate_breakdown.csv"
OPPORTUNITY_CSV      = ANALYSIS_INPUT_CSV.parent / "opportunity_matrix.csv"
TIMING_CSV           = ANALYSIS_INPUT_CSV.parent / "timing_summary.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Aggregations
# ─────────────────────────────────────────────────────────────────────────────

def build_sector_kpis(df: pd.DataFrame) -> pd.DataFrame:
    """Per-sector KPIs: counts, capital, age, and signal coverage."""
    kpis = (
        df.groupby("category", dropna=False)
          .agg(
              companies=("identifiant_unique", "count"),
              avg_capital=("capital", "mean"),
              median_capital=("capital", "median"),
              avg_age_years=("age_years", "mean"),
              pct_digital_high=("digital_signal", lambda s: 100 * (s == "high").mean()),
              pct_mobility=("mobility_signal", lambda s: 100 * s.mean()),
              pct_multisite=("multisite_signal", lambda s: 100 * s.mean()),
              pct_callable=("callable_prospect", lambda s: 100 * s.mean()),
              avg_confidence=("confidence", "mean"),
          )
          .reset_index()
          .sort_values("companies", ascending=False)
    )
    for col in ["avg_capital", "median_capital", "avg_age_years",
                "pct_digital_high", "pct_mobility", "pct_multisite",
                "pct_callable", "avg_confidence"]:
        if col in kpis.columns:
            kpis[col] = kpis[col].round(2)
    return kpis


def build_cohort_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-tab of sector x maturity x capital_tier — where the pockets are."""
    cohort = (
        df.groupby(["category", "maturity", "capital_tier"], dropna=False)
          .agg(
              companies=("identifiant_unique", "count"),
              avg_capital=("capital", "mean"),
          )
          .reset_index()
          .sort_values("companies", ascending=False)
    )
    cohort["avg_capital"] = cohort["avg_capital"].round(0)
    return cohort


def build_geography_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-city counts and signal coverage — for the geography view."""
    if "city" not in df.columns:
        return pd.DataFrame()
    geo = (
        df.groupby("city", dropna=False)
          .agg(
              companies=("identifiant_unique", "count"),
              pct_digital_high=("digital_signal", lambda s: 100 * (s == "high").mean()),
              pct_mobility=("mobility_signal", lambda s: 100 * s.mean()),
              avg_capital=("capital", "mean"),
          )
          .reset_index()
          .sort_values("companies", ascending=False)
    )
    for col in ["pct_digital_high", "pct_mobility", "avg_capital"]:
        if col in geo.columns:
            geo[col] = geo[col].round(2)
    return geo


def build_vague_activities_report(df: pd.DataFrame, top_n: int = 30) -> pd.DataFrame:
    """Activities producing many low-confidence / 'others' classifications."""
    if "fr_activite_principale" not in df.columns:
        return pd.DataFrame()
    mask_vague = (df["category"] == "others") | (df.get("needs_review") == True)
    vague = df.loc[mask_vague, ["fr_activite_principale", "category", "method"]].copy()
    vague["fr_activite_principale"] = vague["fr_activite_principale"].fillna("(empty)")
    report = (
        vague.groupby("fr_activite_principale", dropna=False)
             .size()
             .reset_index(name="occurrences")
             .sort_values("occurrences", ascending=False)
             .head(top_n)
    )
    return report


# ─────────────────────────────────────────────────────────────────────────────
# v2 aggregations — surface the new features for the dashboard
# ─────────────────────────────────────────────────────────────────────────────

def build_governorate_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """
    Per-governorate breakdown — sales team is organized by region, so this is
    the natural unit for territory dashboards.
    """
    if "governorate" not in df.columns:
        return pd.DataFrame()
    out = (
        df.groupby("governorate", dropna=False)
          .agg(
              companies=("identifiant_unique", "count"),
              pct_new=("is_new_company", lambda s: 100 * s.mean()) if "is_new_company" in df.columns else ("identifiant_unique", "count"),
              pct_digital_high=("digital_signal", lambda s: 100 * (s == "high").mean()),
              pct_b2b=("business_model", lambda s: 100 * (s == "B2B").mean()) if "business_model" in df.columns else ("identifiant_unique", "count"),
              pct_high_connectivity=("connectivity_need", lambda s: 100 * (s == "high").mean()) if "connectivity_need" in df.columns else ("identifiant_unique", "count"),
              avg_capital=("capital", "mean"),
          )
          .reset_index()
          .sort_values("companies", ascending=False)
    )
    for col in ["pct_new", "pct_digital_high", "pct_b2b", "pct_high_connectivity", "avg_capital"]:
        if col in out.columns:
            out[col] = out[col].round(2)
    return out


def build_opportunity_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    The recommendation-engine-ready matrix.

    Cross of company_size × connectivity_need × business_model gives the
    fundamental shape of the opportunity — which audience segments need what
    kind of telecom product. A future recommender can use this directly to
    target each cell with the right offer pack.
    """
    needed = {"company_size", "connectivity_need", "business_model"}
    if not needed.issubset(df.columns):
        return pd.DataFrame()
    out = (
        df.groupby(["company_size", "connectivity_need", "business_model"], dropna=False)
          .agg(
              companies=("identifiant_unique", "count"),
              avg_capital=("capital", "mean"),
              pct_new=("is_new_company", lambda s: 100 * s.mean()) if "is_new_company" in df.columns else ("identifiant_unique", "count"),
          )
          .reset_index()
          .sort_values("companies", ascending=False)
    )
    if "avg_capital" in out.columns:
        out["avg_capital"] = out["avg_capital"].round(0)
    if "pct_new" in out.columns:
        out["pct_new"] = out["pct_new"].round(1)
    return out


def build_timing_summary(df: pd.DataFrame, months: int = 24) -> pd.DataFrame:
    """
    Month-by-month registration count for the last `months` months — surfaces
    the recent-arrivals pipeline, which is the most actionable prospect pool.
    """
    if "date_immatriculation" not in df.columns:
        return pd.DataFrame()
    dates = pd.to_datetime(df["date_immatriculation"], errors="coerce", format="mixed")
    dates = dates.dropna()
    if len(dates) == 0:
        return pd.DataFrame()
    cutoff = dates.max() - pd.DateOffset(months=months)
    recent = dates[dates >= cutoff]
    monthly = (
        recent.dt.to_period("M")
              .astype(str)
              .value_counts()
              .sort_index()
              .reset_index()
    )
    monthly.columns = ["month", "registrations"]
    return monthly


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis(input_csv: str | Path | None = None) -> dict:
    """Run feature engineering + aggregations and write the analytical CSVs."""
    csv_path = Path(input_csv) if input_csv else ANALYSIS_INPUT_CSV

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Segmented CSV not found: {csv_path}\n"
            f"Run segmentation first:  python run.py --skip-extraction"
        )

    logger.info("Analysis — loading %s", csv_path)
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    logger.info("Loaded %d rows", len(df))

    logger.info("Building features...")
    df = build_all_features(df)

    out_dir = csv_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Full feature table (one row per company, every engineered column)
    df.to_csv(FEATURES_CSV, index=False, encoding="utf-8-sig")
    logger.info("Wrote %s (%d rows)", FEATURES_CSV, len(df))

    # 2. Sector KPIs
    sector_kpis = build_sector_kpis(df)
    sector_kpis.to_csv(SECTOR_KPIS_CSV, index=False, encoding="utf-8-sig")
    logger.info("Wrote %s (%d sectors)", SECTOR_KPIS_CSV, len(sector_kpis))

    # 3. Cohort summary
    cohort = build_cohort_summary(df)
    cohort.to_csv(COHORT_SUMMARY_CSV, index=False, encoding="utf-8-sig")
    logger.info("Wrote %s (%d cohorts)", COHORT_SUMMARY_CSV, len(cohort))

    # 4. Geography summary
    geo = build_geography_summary(df)
    geo.to_csv(GEOGRAPHY_CSV, index=False, encoding="utf-8-sig")
    logger.info("Wrote %s (%d cities)", GEOGRAPHY_CSV, len(geo))

    # 5. Vague activities
    vague = build_vague_activities_report(df)
    vague.to_csv(VAGUE_ACTIVITIES_CSV, index=False, encoding="utf-8-sig")
    logger.info("Wrote %s (%d activities)", VAGUE_ACTIVITIES_CSV, len(vague))

    # 6. v2 — Governorate breakdown
    gov = build_governorate_breakdown(df)
    if len(gov):
        gov.to_csv(GOVERNORATE_CSV, index=False, encoding="utf-8-sig")
        logger.info("Wrote %s (%d governorates)", GOVERNORATE_CSV, len(gov))

    # 7. v2 — Opportunity matrix (the recommendation-engine-ready segment grid)
    opp = build_opportunity_matrix(df)
    if len(opp):
        opp.to_csv(OPPORTUNITY_CSV, index=False, encoding="utf-8-sig")
        logger.info("Wrote %s (%d segments)", OPPORTUNITY_CSV, len(opp))

    # 8. v2 — Monthly registration timing
    timing = build_timing_summary(df)
    if len(timing):
        timing.to_csv(TIMING_CSV, index=False, encoding="utf-8-sig")
        logger.info("Wrote %s (%d months)", TIMING_CSV, len(timing))

    summary = {
        "total_rows":             len(df),
        "callable_prospects":     int(df["callable_prospect"].sum()) if "callable_prospect" in df.columns else None,
        "digital_high_count":     int((df["digital_signal"] == "high").sum()),
        "mobility_signal_count":  int(df["mobility_signal"].sum()),
        "multisite_signal_count": int(df["multisite_signal"].sum()),
        # v2 metrics
        "new_companies_count":    int(df["is_new_company"].sum()) if "is_new_company" in df.columns else None,
        "b2b_count":              int((df["business_model"] == "B2B").sum()) if "business_model" in df.columns else None,
        "international_count":    int(df["international_signal"].sum()) if "international_signal" in df.columns else None,
        "high_connectivity_count":int((df["connectivity_need"] == "high").sum()) if "connectivity_need" in df.columns else None,
        # paths
        "features_csv":           str(FEATURES_CSV),
        "sector_kpis_csv":        str(SECTOR_KPIS_CSV),
        "cohort_summary_csv":     str(COHORT_SUMMARY_CSV),
        "geography_csv":          str(GEOGRAPHY_CSV),
        "vague_activities_csv":   str(VAGUE_ACTIVITIES_CSV),
        "governorate_csv":        str(GOVERNORATE_CSV),
        "opportunity_csv":        str(OPPORTUNITY_CSV),
        "timing_csv":             str(TIMING_CSV),
    }

    logger.info("=" * 60)
    logger.info("ANALYSIS SUMMARY")
    logger.info("Total companies        : %d", summary["total_rows"])
    logger.info("Callable prospects     : %s", summary["callable_prospects"])
    logger.info("Digital signal = high  : %d", summary["digital_high_count"])
    logger.info("Mobility signal        : %d", summary["mobility_signal_count"])
    logger.info("Multisite signal       : %d", summary["multisite_signal_count"])
    logger.info("New companies (12mo)   : %s", summary["new_companies_count"])
    logger.info("B2B companies          : %s", summary["b2b_count"])
    logger.info("International companies: %s", summary["international_count"])
    logger.info("High connectivity need : %s", summary["high_connectivity_count"])
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    run_analysis()
