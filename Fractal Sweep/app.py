"""
Fractal Sweep — Streamlit Dashboard (MOVED)
=============================================
This file is kept for historical reference.
The unified dashboard has moved to the repo root:

    streamlit run app.py          ← run this instead

from the TradingHub/ root directory.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
JSON_PATH = _HERE / "model_stats.json"

MODEL_LABELS = {
    "1H_5M_PREV_CISD":  "1H Sweep · 5M CISD",
    "30M_3M_PREV_CISD": "30M Sweep · 3M CISD",
}

FILTER_FIELDS = {"F3": "passes_f3", "F4": "passes_f4", "SMT": "smt"}
FILTER_LABELS = {
    "F3":  "Shallow Sweep (F3)",
    "F4":  "Closed Back Inside (F4)",
    "SMT": "NQ-ES Divergence (SMT)",
}

# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading model_stats.json …")
def load_stats() -> dict:
    if not JSON_PATH.exists():
        return {}
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_profile(stats: dict, model_key: str) -> dict:
    return stats[model_key]["profiles"]["simple_1r"]


# ── Filter helpers ────────────────────────────────────────────────────────────
def apply_filters(trades: list[dict], f3: bool, f4: bool, smt: bool) -> list[dict]:
    out = trades
    if f3:
        out = [t for t in out if t.get("passes_f3")]
    if f4:
        out = [t for t in out if t.get("passes_f4")]
    if smt:
        out = [t for t in out if t.get("smt")]
    return out


def equity_curve(trades: list[dict], account: float = 4500, risk: float = 225) -> pd.DataFrame:
    rows = []
    equity = account
    for t in sorted(trades, key=lambda x: (x["date"], x["hr"], x["mn"])):
        equity += t["r"] * risk
        rows.append({"date": t["date"], "equity": round(equity, 2)})
    return pd.DataFrame(rows)


def summary_stats(trades: list[dict]) -> dict:
    if not trades:
        return {}
    n     = len(trades)
    wins  = sum(1 for t in trades if t["outcome"] == "WIN")
    wr    = wins / n
    ev    = sum(t["r"] for t in trades) / n
    pf_w  = sum(t["r"] for t in trades if t["r"] > 0)
    pf_l  = abs(sum(t["r"] for t in trades if t["r"] < 0))
    pf    = pf_w / pf_l if pf_l else float("inf")
    return {"n": n, "wins": wins, "wr": wr, "ev": ev, "pf": pf}


# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Fractal Sweep",
    page_icon="📊",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("Fractal Sweep")
    st.caption("ICT Sweep + CISD Backtester")

    stats = load_stats()
    if not stats:
        st.error(f"model_stats.json not found at:\n{JSON_PATH}")
        st.stop()

    model_key = st.selectbox(
        "Model",
        options=list(MODEL_LABELS.keys()),
        format_func=lambda k: MODEL_LABELS[k],
    )

    st.divider()
    st.subheader("Filters")
    f3  = st.toggle(FILTER_LABELS["F3"],  value=False)
    f4  = st.toggle(FILTER_LABELS["F4"],  value=False)
    smt = st.toggle(FILTER_LABELS["SMT"], value=False)

    st.divider()
    st.subheader("Account")
    account_size = st.number_input("Account size ($)", value=4500, step=500)
    risk_per_trade = st.number_input("Risk per trade ($)", value=225, step=25)

# ── Load data ─────────────────────────────────────────────────────────────────
profile  = get_profile(stats, model_key)
meta     = profile["meta"]
all_trades = profile["recent_trades"]
trades   = apply_filters(all_trades, f3, f4, smt)
stats_d  = summary_stats(trades)

# ── Header ────────────────────────────────────────────────────────────────────
st.title(f"Fractal Sweep — {MODEL_LABELS[model_key]}")
st.caption(
    f"Data: {meta['date_range']}  ·  "
    f"{'F3 ' if f3 else ''}{'F4 ' if f4 else ''}{'SMT ' if smt else ''}{'(no filters)' if not (f3 or f4 or smt) else ''}"
)

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
if stats_d:
    k1.metric("Trades",       f"{stats_d['n']:,}")
    k2.metric("Win Rate",     f"{stats_d['wr']:.1%}")
    k3.metric("EV / trade",   f"{stats_d['ev']:+.3f}R")
    k4.metric("Profit Factor",f"{stats_d['pf']:.3f}")
    k5.metric("Setups / day", f"{meta['setups_per_day_ny']:.2f}")
else:
    st.warning("No trades match the current filter combination.")
    st.stop()

st.divider()

# ── Equity curve ──────────────────────────────────────────────────────────────
st.subheader("Equity Curve")

eq_df = equity_curve(trades, account=account_size, risk=risk_per_trade)
if not eq_df.empty:
    fig_eq = px.line(
        eq_df, x="date", y="equity",
        labels={"date": "Date", "equity": "Equity ($)"},
        color_discrete_sequence=["#00b4d8"],
    )
    fig_eq.add_hline(
        y=account_size,
        line_dash="dash", line_color="gray",
        annotation_text="Starting equity",
        annotation_position="top left",
    )
    fig_eq.update_layout(
        height=360,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

st.divider()

# ── Performance by Year ───────────────────────────────────────────────────────
st.subheader("Performance by Year")

by_year_raw = profile["by_year"]

# If filters are active, recompute by year from filtered trades
if f3 or f4 or smt:
    by_year_map: dict[int, dict] = {}
    for t in trades:
        yr = int(t["date"][:4])
        row = by_year_map.setdefault(yr, {"n": 0, "wins": 0})
        row["n"] += 1
        row["wins"] += 1 if t["outcome"] == "WIN" else 0
    by_year_data = [
        {
            "yr": yr,
            "n": v["n"],
            "wr": v["wins"] / v["n"],
            "ev": sum(t["r"] for t in trades if t["date"][:4] == str(yr)) / v["n"],
        }
        for yr, v in sorted(by_year_map.items())
    ]
else:
    by_year_data = by_year_raw

yr_df = pd.DataFrame(by_year_data)[["yr", "n", "wr", "ev"]]
yr_df.columns = ["Year", "Trades", "Win Rate", "EV (R)"]
yr_df["Win Rate"] = yr_df["Win Rate"].map("{:.1%}".format)
yr_df["EV (R)"]   = yr_df["EV (R)"].map("{:+.3f}".format)

col_yr, col_hr = st.columns([1, 1])

with col_yr:
    st.dataframe(yr_df, use_container_width=True, hide_index=True)

with col_hr:
    # Win rate by hour heatmap (all filters applied via trade list)
    st.subheader("Win Rate by Hour")
    if f3 or f4 or smt:
        hr_map: dict[int, dict] = {}
        for t in trades:
            h = t["hr"]
            row = hr_map.setdefault(h, {"n": 0, "wins": 0})
            row["n"] += 1
            row["wins"] += 1 if t["outcome"] == "WIN" else 0
        hr_data = [
            {"hr": h, "wr": v["wins"] / v["n"], "n": v["n"]}
            for h, v in sorted(hr_map.items()) if v["n"] >= 5
        ]
    else:
        hr_data = [r for r in profile["by_hour"] if r["n"] >= 5]

    if hr_data:
        hr_df = pd.DataFrame(hr_data)
        fig_hr = px.bar(
            hr_df, x="hr", y="wr",
            labels={"hr": "Hour (ET)", "wr": "Win Rate"},
            color="wr",
            color_continuous_scale=["#d62728", "#aec7e8", "#2ca02c"],
            range_color=[0.3, 0.7],
        )
        fig_hr.add_hline(y=0.5, line_dash="dash", line_color="gray")
        fig_hr.update_layout(
            height=280,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig_hr, use_container_width=True)

st.divider()

# ── Filter combinations ───────────────────────────────────────────────────────
st.subheader("Filter Combinations (all 8)")

combos = profile["filter_variants"]["all_combinations"]
combo_df = pd.DataFrame(combos)[["label", "n", "wr", "ev", "pf", "max_dd_pct"]]
combo_df.columns = ["Combination", "N", "Win Rate", "EV (R)", "PF", "Max DD %"]
combo_df["Win Rate"] = combo_df["Win Rate"].map("{:.1%}".format)
combo_df["EV (R)"]   = combo_df["EV (R)"].map("{:+.3f}".format)
combo_df["PF"]       = combo_df["PF"].map("{:.3f}".format)
combo_df["Max DD %"] = combo_df["Max DD %"].map("{:.1f}%".format)
combo_df = combo_df.sort_values("EV (R)", ascending=False)
st.dataframe(combo_df, use_container_width=True, hide_index=True)

st.divider()

# ── SMT divergence split ──────────────────────────────────────────────────────
st.subheader("SMT Divergence Split")

smt_data = profile["smt_summary"]
smt_df = pd.DataFrame(smt_data)
smt_df["label"] = smt_df["smt"].map({True: "SMT (NQ only)", False: "Non-SMT"})
smt_df = smt_df[["label", "n", "wr", "ev", "pf"]]
smt_df.columns = ["Group", "N", "Win Rate", "EV (R)", "PF"]
smt_df["Win Rate"] = smt_df["Win Rate"].map("{:.1%}".format)
smt_df["EV (R)"]   = smt_df["EV (R)"].map("{:+.3f}".format)
smt_df["PF"]       = smt_df["PF"].map("{:.3f}".format)
st.dataframe(smt_df, use_container_width=True, hide_index=True)

st.divider()

# ── Day-of-week breakdown ─────────────────────────────────────────────────────
st.subheader("Performance by Day of Week")

DOW_NAMES = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}

if f3 or f4 or smt:
    dow_map: dict[int, dict] = {}
    for t in trades:
        dw = t["dow"]
        row = dow_map.setdefault(dw, {"n": 0, "wins": 0, "r_sum": 0.0})
        row["n"] += 1
        row["wins"] += 1 if t["outcome"] == "WIN" else 0
        row["r_sum"] += t["r"]
    dow_data = [
        {"dow": dw, "dow_name": DOW_NAMES.get(dw, str(dw)),
         "n": v["n"], "wr": v["wins"] / v["n"], "ev": v["r_sum"] / v["n"]}
        for dw, v in sorted(dow_map.items()) if v["n"] >= 5
    ]
else:
    dow_data = [
        {**r, "dow_name": DOW_NAMES.get(r["dow"], str(r["dow"]))}
        for r in profile["by_dow"] if r["n"] >= 5
    ]

if dow_data:
    dow_df = pd.DataFrame(dow_data)[["dow_name", "n", "wr", "ev"]]
    dow_df.columns = ["Day", "N", "Win Rate", "EV (R)"]

    fig_dow = px.bar(
        dow_df, x="Day", y="Win Rate",
        color="Win Rate",
        color_continuous_scale=["#d62728", "#aec7e8", "#2ca02c"],
        range_color=[0.3, 0.7],
        labels={"Win Rate": "Win Rate"},
        text=dow_df["Win Rate"].map("{:.1%}".format),
    )
    fig_dow.add_hline(y=0.5, line_dash="dash", line_color="gray")
    fig_dow.update_layout(
        height=280,
        margin=dict(l=0, r=0, t=10, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        coloraxis_showscale=False,
    )
    fig_dow.update_traces(textposition="outside")
    st.plotly_chart(fig_dow, use_container_width=True)

st.divider()

# ── Recent trades table ───────────────────────────────────────────────────────
st.subheader("Trades")
st.caption(f"{len(trades):,} trades  (sorted newest first)")

rt_df = pd.DataFrame(trades)[
    ["date", "direction", "hr", "session", "dow_name", "entry_price",
     "risk_pts", "r", "outcome", "passes_f3", "passes_f4", "smt"]
].copy()
rt_df.columns = ["Date", "Dir", "Hour (ET)", "Session", "DoW",
                  "Entry", "Risk pts", "R", "Outcome", "F3", "F4", "SMT"]
rt_df = rt_df.sort_values("Date", ascending=False)

st.dataframe(
    rt_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "R":       st.column_config.NumberColumn(format="%.2f"),
        "Entry":   st.column_config.NumberColumn(format="%.2f"),
        "F3":      st.column_config.CheckboxColumn(),
        "F4":      st.column_config.CheckboxColumn(),
        "SMT":     st.column_config.CheckboxColumn(),
        "Outcome": st.column_config.TextColumn(),
    },
    height=400,
)
