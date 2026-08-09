"""Streamlit dashboard for the Telegram expense tracker.

Read-only by design: it authenticates with the *publishable* key, which is
subject to RLS and has SELECT permission only. The secret key never appears
here — Streamlit Community Cloud apps are public URLs, and anything in this
process is one misconfiguration away from being world-readable.

Local:  streamlit run dashboard.py
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Expenses", page_icon="💸", layout="wide")

TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Kolkata"))
SYMBOL = "₹"


def secret(name: str, default: str = "") -> str:
    """Read from Streamlit secrets first, then the environment."""
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)


# --------------------------------------------------------------------------- #
# Auth gate — the Streamlit Cloud URL is public
# --------------------------------------------------------------------------- #

def check_password() -> bool:
    expected = secret("DASHBOARD_PASSWORD")
    if not expected:
        st.error(
            "DASHBOARD_PASSWORD is not set. Refusing to serve your financial "
            "data on a public URL without a password."
        )
        return False

    if st.session_state.get("authed"):
        return True

    st.title("💸 Expenses")
    with st.form("login"):
        attempt = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            # Constant-time-ish compare; the value is short and low-value but
            # there is no reason to leak length via early exit.
            if len(attempt) == len(expected) and attempt == expected:
                st.session_state["authed"] = True
                st.rerun()
            else:
                st.error("Nope.")
    return False


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #

@st.cache_resource
def client():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_ANON_KEY")
    if not url or not key:
        st.error("SUPABASE_URL / SUPABASE_ANON_KEY missing from secrets.")
        st.stop()
    return create_client(url, key)


@st.cache_data(ttl=60, show_spinner="Loading expenses…")
def load() -> pd.DataFrame:
    rows = (
        client()
        .table("expenses")
        .select("spent_on, created_at, amount, category, description")
        .is_("deleted_at", "null")
        .order("spent_on", desc=True)
        .limit(5000)
        .execute()
        .data
        or []
    )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=["spent_on", "created_at", "amount", "category", "description"]
        )
    frame["spent_on"] = pd.to_datetime(frame["spent_on"]).dt.date
    frame["created_at"] = pd.to_datetime(frame["created_at"], format="mixed", utc=True)
    frame["amount"] = frame["amount"].astype(float)
    return frame


def money(value: float) -> str:
    return f"{SYMBOL}{value:,.0f}"


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #

def main() -> None:
    st.title("💸 Expenses")

    data = load()
    if data.empty:
        st.info("No expenses yet. Message your Telegram bot to log the first one.")
        st.stop()

    today = pd.Timestamp.now(TZ).date()
    month_start = today.replace(day=1)

    with st.sidebar:
        st.header("Filters")
        preset = st.radio(
            "Period",
            ["This month", "Last 30 days", "This year", "All time", "Custom"],
            index=0,
        )
        if preset == "This month":
            start, end = month_start, today
        elif preset == "Last 30 days":
            start, end = today - timedelta(days=29), today
        elif preset == "This year":
            start, end = date(today.year, 1, 1), today
        elif preset == "All time":
            start, end = data["spent_on"].min(), today
        else:
            picked = st.date_input(
                "Range", value=(month_start, today), max_value=today
            )
            start, end = picked if isinstance(picked, tuple) else (picked, picked)

        categories = sorted(data["category"].unique())
        chosen = st.multiselect("Categories", categories, default=categories)

        if st.button("↻ Refresh"):
            st.cache_data.clear()
            st.rerun()

    window = data[
        (data["spent_on"] >= start)
        & (data["spent_on"] <= end)
        & (data["category"].isin(chosen))
    ]

    if window.empty:
        st.warning("Nothing in that range.")
        st.stop()

    # --- headline metrics ---------------------------------------------------
    days = max((end - start).days + 1, 1)
    total = window["amount"].sum()

    previous = data[
        (data["spent_on"] >= start - timedelta(days=days))
        & (data["spent_on"] < start)
        & (data["category"].isin(chosen))
    ]["amount"].sum()
    delta = None if previous == 0 else f"{(total - previous) / previous:+.0%} vs prev"

    left, mid, right, far = st.columns(4)
    left.metric("Total", money(total), delta, delta_color="inverse")
    mid.metric("Daily average", money(total / days))
    right.metric("Transactions", f"{len(window):,}")
    far.metric("Largest", money(window["amount"].max()))

    st.divider()

    # --- category split + trend --------------------------------------------
    chart_col, trend_col = st.columns([1, 1.3])

    by_category = (
        window.groupby("category", as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
    )

    with chart_col:
        st.subheader("By category")
        bars = (
            alt.Chart(by_category)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("amount:Q", title=None, axis=alt.Axis(format="~s")),
                y=alt.Y("category:N", sort="-x", title=None),
                tooltip=[
                    alt.Tooltip("category:N", title="Category"),
                    alt.Tooltip("amount:Q", title="Spent", format=",.0f"),
                ],
                color=alt.Color("category:N", legend=None, scale=alt.Scale(scheme="tableau20")),
            )
            .properties(height=max(260, 28 * len(by_category)))
        )
        st.altair_chart(bars, use_container_width=True)

    with trend_col:
        st.subheader("Daily spend")
        daily = window.groupby("spent_on", as_index=False)["amount"].sum()
        line = (
            alt.Chart(daily)
            .mark_area(
                line={"color": "#4c78a8"},
                color=alt.Gradient(
                    gradient="linear",
                    stops=[
                        alt.GradientStop(color="white", offset=0),
                        alt.GradientStop(color="#4c78a8", offset=1),
                    ],
                    x1=1, x2=1, y1=1, y2=0,
                ),
                interpolate="monotone",
            )
            .encode(
                x=alt.X("spent_on:T", title=None),
                y=alt.Y("amount:Q", title=None, axis=alt.Axis(format="~s")),
                tooltip=[
                    alt.Tooltip("spent_on:T", title="Date"),
                    alt.Tooltip("amount:Q", title="Spent", format=",.0f"),
                ],
            )
            .properties(height=max(260, 28 * len(by_category)))
        )
        st.altair_chart(line, use_container_width=True)

    # --- share of wallet ----------------------------------------------------
    st.subheader("Share of spending")
    share = by_category.assign(pct=lambda f: f["amount"] / f["amount"].sum())
    st.dataframe(
        share.rename(columns={"category": "Category", "amount": "Spent", "pct": "Share"}),
        hide_index=True,
        use_container_width=True,
        column_config={
            "Spent": st.column_config.NumberColumn(format=f"{SYMBOL}%,.0f"),
            "Share": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=1
            ),
        },
    )

    # --- ledger -------------------------------------------------------------
    st.subheader("Transactions")
    ledger = (
        window.sort_values(["spent_on", "created_at"], ascending=False)
        .loc[:, ["spent_on", "amount", "category", "description"]]
        .rename(
            columns={
                "spent_on": "Date",
                "amount": "Amount",
                "category": "Category",
                "description": "Note",
            }
        )
    )
    st.dataframe(
        ledger,
        hide_index=True,
        use_container_width=True,
        height=420,
        column_config={
            "Amount": st.column_config.NumberColumn(format=f"{SYMBOL}%,.2f"),
        },
    )
    st.download_button(
        "Download CSV",
        ledger.to_csv(index=False).encode(),
        file_name=f"expenses_{start}_{end}.csv",
        mime="text/csv",
    )


if check_password():
    main()
