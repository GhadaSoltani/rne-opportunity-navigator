"""
app/components/charts.py
========================
Reusable chart components. All charts use the shared CATEGORY_COLORS palette
from theme.py and a common dark-navy layout so they sit calmly on the page.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from app.theme import (
    CATEGORY_COLORS, WHITE, OFF_WHITE, MUTED,
    NAVY_HAIRLINE, NAVY_LIGHT, NAVY_LIGHTER, RED, RED_SOFT,
)

# Shared transparent layout so charts blend into the navy surface
_BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=OFF_WHITE, family="sans-serif", size=13),
    margin=dict(t=24, b=24, l=20, r=20),
    hoverlabel=dict(bgcolor="#102544", bordercolor=NAVY_LIGHTER, font_size=13),
)

# Offer-family color map — harmonized with the brand palette
FAMILY_COLORS = {
    "mobile":        "#5B8FE0",
    "mobile_data":   "#3FB8B0",
    "fixed":         "#E0A24C",
    "security":      "#EF4B52",
    "cloud":         "#9B89E6",
    "collaboration": "#37C2A0",
    "iot":           "#E07CB0",
    "managed":       "#7286A6",
}

FAMILY_LABELS = {
    "mobile":        "Mobile",
    "mobile_data":   "Data",
    "fixed":         "Fixed",
    "security":      "Security",
    "cloud":         "Cloud",
    "collaboration": "Collab",
    "iot":           "IoT",
    "managed":       "Managed",
}


def _apply_axes(fig):
    """Soft gridlines + muted axis text, applied consistently."""
    fig.update_xaxes(gridcolor=NAVY_HAIRLINE, zeroline=False,
                     tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_yaxes(gridcolor=NAVY_HAIRLINE, zeroline=False,
                     tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# Existing charts (unchanged)
# ──────────────────────────────────────────────────────────────────────────────

def category_distribution_chart(df: pd.DataFrame, chart_type: str = "bar"):
    """Render a category distribution chart (bar or pie/donut)."""
    if "category" not in df.columns or df.empty:
        st.info("No category data to display yet.")
        return

    counts = df["category"].value_counts().reset_index()
    counts.columns = ["category", "count"]
    color_map = {cat: CATEGORY_COLORS.get(cat, "#7286A6") for cat in counts["category"]}

    if chart_type == "pie":
        fig = px.pie(
            counts, names="category", values="count", color="category",
            color_discrete_map=color_map, hole=0.55,
        )
        fig.update_traces(
            textposition="inside", textinfo="percent",
            marker=dict(line=dict(color="#0A1B38", width=2)),
        )
        fig.update_layout(**_BASE_LAYOUT, height=380, showlegend=True,
                          legend=dict(font=dict(color=OFF_WHITE)))
    else:
        fig = px.bar(
            counts, x="category", y="count", color="category",
            color_discrete_map=color_map, text="count",
        )
        fig.update_traces(textposition="outside",
                          textfont=dict(color=OFF_WHITE),
                          marker=dict(line=dict(width=0)),
                          cliponaxis=False)
        fig.update_layout(**_BASE_LAYOUT, height=380, showlegend=False)
        _apply_axes(fig)

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def method_distribution_chart(df: pd.DataFrame):
    """Render a horizontal bar chart of classification methods."""
    if "method" not in df.columns or df.empty:
        return

    counts = df["method"].value_counts().reset_index()
    counts.columns = ["method", "count"]
    counts = counts.sort_values("count")  # ascending so longest bar is on top

    fig = px.bar(counts, x="count", y="method", orientation="h", text="count")
    fig.update_traces(marker_color="#5B8FE0", textposition="outside",
                      textfont=dict(color=OFF_WHITE), cliponaxis=False)
    fig.update_layout(**_BASE_LAYOUT, height=320, showlegend=False)
    _apply_axes(fig)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def offer_distribution_chart(df: pd.DataFrame, offer_col: str = "recommended_offer"):
    """
    Horizontal bar chart of recommended offers — used on the prospects page.
    Bars use a single calm red ramp so the chart reads as one cohesive set.
    """
    if offer_col not in df.columns or df.empty:
        st.info("No offer data to display yet.")
        return

    counts = df[offer_col].value_counts().reset_index()
    counts.columns = ["offer", "companies"]
    counts = counts.sort_values("companies")

    fig = px.bar(counts, x="companies", y="offer", orientation="h", text="companies")
    fig.update_traces(marker_color=RED, marker_line_width=0,
                      textposition="outside", textfont=dict(color=OFF_WHITE),
                      cliponaxis=False)
    fig.update_layout(**_BASE_LAYOUT, height=max(300, 38 * len(counts)), showlegend=False)
    _apply_axes(fig)
    fig.update_yaxes(title="")
    fig.update_xaxes(title="Companies")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ──────────────────────────────────────────────────────────────────────────────
# Recommendation charts (new)
# ──────────────────────────────────────────────────────────────────────────────

def recommendation_top_offers_chart(recs_df: pd.DataFrame):
    """
    Horizontal bar chart of rank-1 recommended offers.
    Each bar colored by offer family. Shows how many companies get each offer
    as their top recommendation.
    """
    if recs_df.empty or "offer_name" not in recs_df.columns:
        st.info("No recommendation data to display.")
        return

    top1 = recs_df[recs_df["rank"] == 1].copy()
    counts = top1.groupby(["offer_name", "family"], as_index=False).size()
    counts.columns = ["offer_name", "family", "companies"]
    counts = counts.sort_values("companies")

    colors = [FAMILY_COLORS.get(f, "#7286A6") for f in counts["family"]]

    fig = go.Figure(go.Bar(
        x=counts["companies"],
        y=counts["offer_name"],
        orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=counts["companies"],
        textposition="outside",
        textfont=dict(color=OFF_WHITE),
        cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x} companies<extra></extra>",
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        height=max(300, 36 * len(counts)),
        showlegend=False,
    )
    _apply_axes(fig)
    fig.update_yaxes(title="")
    fig.update_xaxes(title="Companies")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def score_anatomy_chart(recs_df: pd.DataFrame):
    """
    Grouped bar chart showing average rule / content / collab scores
    for rank-1 recommendations, broken out by sector.

    Reveals WHERE the signal comes from for each sector.
    """
    if recs_df.empty or "category" not in recs_df.columns:
        st.info("No score data to display.")
        return

    top1 = recs_df[recs_df["rank"] == 1].copy()
    if top1.empty:
        return

    agg = top1.groupby("category", as_index=False).agg(
        rule_score=("rule_score", "mean"),
        content_score=("content_score", "mean"),
        collab_score=("collab_score", "mean"),
    ).sort_values("rule_score", ascending=False)

    # Map labels
    cat_labels = {
        "retail": "Retail", "manufacturing": "Manufacturing",
        "transport": "Transport", "tourism": "Tourism",
        "healthcare": "Healthcare", "education": "Education",
        "financial_services": "Finance", "others": "Others",
    }
    agg["label"] = agg["category"].map(lambda c: cat_labels.get(c, c))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Rules", x=agg["label"], y=agg["rule_score"].round(3),
        marker_color="#5B8FE0", text=agg["rule_score"].round(2),
        textposition="outside", textfont=dict(color="#5B8FE0", size=11),
        cliponaxis=False,
    ))
    fig.add_trace(go.Bar(
        name="Content", x=agg["label"], y=agg["content_score"].round(3),
        marker_color="#37C2A0", text=agg["content_score"].round(2),
        textposition="outside", textfont=dict(color="#37C2A0", size=11),
        cliponaxis=False,
    ))
    fig.add_trace(go.Bar(
        name="Peers", x=agg["label"], y=agg["collab_score"].round(3),
        marker_color="#E0A24C", text=agg["collab_score"].round(2),
        textposition="outside", textfont=dict(color="#E0A24C", size=11),
        cliponaxis=False,
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        height=380,
        barmode="group",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0, font=dict(color=OFF_WHITE, size=12),
        ),
    )
    _apply_axes(fig)
    fig.update_yaxes(title="Avg score", range=[0, 1.05])
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def family_donut_chart(recs_df: pd.DataFrame):
    """
    Donut chart showing the distribution of offer families across all
    rank-1 recommendations.
    """
    if recs_df.empty or "family" not in recs_df.columns:
        st.info("No family data to display.")
        return

    top1 = recs_df[recs_df["rank"] == 1].copy()
    counts = top1["family"].value_counts().reset_index()
    counts.columns = ["family", "count"]
    counts["label"] = counts["family"].map(lambda f: FAMILY_LABELS.get(f, f))
    colors = [FAMILY_COLORS.get(f, "#7286A6") for f in counts["family"]]

    fig = go.Figure(go.Pie(
        labels=counts["label"],
        values=counts["count"],
        hole=0.55,
        marker=dict(colors=colors, line=dict(color="#0A1B38", width=2)),
        textposition="inside",
        textinfo="percent",
        hovertemplate="<b>%{label}</b><br>%{value} companies<br>%{percent}<extra></extra>",
    ))
    fig.update_layout(
        **_BASE_LAYOUT, height=340,
        showlegend=True,
        legend=dict(font=dict(color=OFF_WHITE)),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
