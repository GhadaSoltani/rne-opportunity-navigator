"""
app/components/charts.py
========================
Reusable chart components. All charts use the shared CATEGORY_COLORS palette
from theme.py and a common dark-navy layout so they sit calmly on the page.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from app.theme import (
    CATEGORY_COLORS, WHITE, OFF_WHITE, MUTED,
    NAVY_HAIRLINE, NAVY_LIGHTER, RED, RED_SOFT,
)

# Shared transparent layout so charts blend into the navy surface
_BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=OFF_WHITE, family="sans-serif", size=13),
    margin=dict(t=24, b=24, l=20, r=20),
    hoverlabel=dict(bgcolor="#102544", bordercolor=NAVY_LIGHTER, font_size=13),
)


def _apply_axes(fig):
    """Soft gridlines + muted axis text, applied consistently."""
    fig.update_xaxes(gridcolor=NAVY_HAIRLINE, zeroline=False,
                     tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    fig.update_yaxes(gridcolor=NAVY_HAIRLINE, zeroline=False,
                     tickfont=dict(color=MUTED), title_font=dict(color=MUTED))
    return fig


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
