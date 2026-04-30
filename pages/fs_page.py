"""
Fractal Sweep page — full feature parity with model_dashboard.html.
All 6 tabs: Overview · Edge · Filters · Risk · Excursion · Trades
Called from root app.py.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_ROOT     = Path(__file__).parent.parent
JSON_PATH = _ROOT / "Fractal Sweep" / "model_stats.json"

MODEL_LABELS = {
    "1H_5M_PREV_CISD":  "1H Sweep · 5M CISD",
    "30M_3M_PREV_CISD": "30M Sweep · 3M CISD",
}
FILTER_LABELS = {
    "F3":  "Shallow Sweep (F3)",
    "F4":  "Closed Back Inside (F4)",
    "SMT": "NQ-ES Divergence (SMT)",
}
DOW_NAMES = {0:"Sun", 1:"Mon", 2:"Tue", 3:"Wed", 4:"Thu", 5:"Fri", 6:"Sat"}
SESSION_ORDER = ["NY1", "NY2", "OTHER", "OVERNIGHT", "PRE"]


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading model data…", ttl=3600)
def _load() -> dict:
    if not JSON_PATH.exists():
        return {}
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


# ── Filter helpers ────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, ttl=3600)
def _load_trades(model_key: str, profile_key: str) -> list:
    parquet_path = JSON_PATH.parent / (JSON_PATH.stem + ".parquet")
    if parquet_path.exists():
        try:
            df = pd.read_parquet(parquet_path)
            mask = (df["model_key"] == model_key) & (df["profile_key"] == profile_key)
            result = df[mask].to_dict("records")
            if result:
                return result
        except Exception:
            pass
    data = _load()
    if data:
        return (data.get(model_key, {})
                .get("profiles", {})
                .get(profile_key, {})
                .get("recent_trades", []))
    return []


def _apply_filters(trades, f3, f4, smt):
    out = trades
    if f3:  out = [t for t in out if t.get("passes_f3")]
    if f4:  out = [t for t in out if t.get("passes_f4")]
    if smt: out = [t for t in out if t.get("smt")]
    return out


def _summary(trades):
    if not trades:
        return {}
    n    = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "WIN")
    wr   = wins / n
    ev   = sum(t["r"] for t in trades) / n
    pf_w = sum(t["r"] for t in trades if t["r"] > 0)
    pf_l = abs(sum(t["r"] for t in trades if t["r"] < 0))
    pf   = pf_w / pf_l if pf_l else float("inf")
    return {"n": n, "wins": wins, "wr": wr, "ev": ev, "pf": pf}


# Trades-based compute functions accept a tuple so Streamlit can hash them.
# Call sites use: _equity_curve(tuple(trades), account, risk)

@st.cache_data(show_spinner=False)
def _equity_curve(trades: tuple, account: float, risk: float) -> pd.DataFrame:
    rows, eq = [], account
    for t in sorted(trades, key=lambda x: (x["date"], x["hr"], x["mn"])):
        eq += t["r"] * risk
        rows.append({"date": t["date"], "equity": round(eq, 2)})
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def _recompute_by_year(trades: tuple) -> list:
    ym = {}
    for t in trades:
        yr = int(t["date"][:4])
        r  = ym.setdefault(yr, {"n": 0, "wins": 0, "ev_sum": 0.0})
        r["n"] += 1
        r["wins"] += t["outcome"] == "WIN"
        r["ev_sum"] += t["r"]
    return [{"yr": yr, "n": v["n"], "wr": v["wins"]/v["n"],
             "ev": v["ev_sum"]/v["n"]}
            for yr, v in sorted(ym.items())]


@st.cache_data(show_spinner=False)
def _recompute_by_hour(trades: tuple) -> list:
    hm = {}
    for t in trades:
        r = hm.setdefault(t["hr"], {"n": 0, "wins": 0, "ev_sum": 0.0})
        r["n"] += 1; r["wins"] += t["outcome"] == "WIN"; r["ev_sum"] += t["r"]
    return [{"hr": h, "n": v["n"], "wr": v["wins"]/v["n"],
             "ev": v["ev_sum"]/v["n"]}
            for h, v in sorted(hm.items()) if v["n"] >= 5]


@st.cache_data(show_spinner=False)
def _recompute_by_dow(trades: tuple) -> list:
    dm = {}
    for t in trades:
        dw = t["dow"]
        r  = dm.setdefault(dw, {"n": 0, "wins": 0, "ev_sum": 0.0})
        r["n"] += 1; r["wins"] += t["outcome"] == "WIN"; r["ev_sum"] += t["r"]
    return [{"dow": dw, "dow_name": DOW_NAMES.get(dw, str(dw)),
             "n": v["n"], "wr": v["wins"]/v["n"], "ev": v["ev_sum"]/v["n"]}
            for dw, v in sorted(dm.items()) if v["n"] >= 5]


# ── Chart helpers ─────────────────────────────────────────────────────────────
_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=0, r=0, t=10, b=0),
    font=dict(size=11),
)
_RED_GRN = ["#d62728", "#aec7e8", "#2ca02c"]


def _bar(df, x, y, color_col=None, hline=None, text_col=None,
          height=260, x_label=None, y_label=None, range_color=None):
    kwargs = dict(
        x=x, y=y,
        labels={x: x_label or x, y: y_label or y},
        color=color_col or y,
        color_continuous_scale=_RED_GRN,
        range_color=range_color or [0.35, 0.65],
    )
    if text_col is not None:
        kwargs["text"] = text_col
    fig = px.bar(df, **kwargs)
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dash", line_color="gray")
    fig.update_layout(height=height, coloraxis_showscale=False, **_LAYOUT)
    if text_col is not None:
        fig.update_traces(textposition="outside")
    return fig


def _line(df, x, y, color="#00b4d8", hline=None, height=360,
          x_label=None, y_label=None):
    fig = px.line(df, x=x, y=y,
                  labels={x: x_label or x, y: y_label or y},
                  color_discrete_sequence=[color])
    if hline is not None:
        fig.add_hline(y=hline, line_dash="dash", line_color="gray",
                      annotation_text="Starting equity", annotation_position="top left")
    fig.update_layout(height=height,
                      xaxis=dict(showgrid=False),
                      yaxis=dict(gridcolor="rgba(128,128,128,0.15)"),
                      **_LAYOUT)
    return fig


def _hist_fig(edges, counts, color="#3b82f6", height=220, title="", vline=None):
    mids = [(edges[i] + edges[i+1]) / 2 for i in range(len(counts))]
    fig  = go.Figure(go.Bar(x=mids, y=counts, marker_color=color, marker_opacity=0.75))
    if vline is not None:
        fig.add_vline(x=vline, line_dash="dash", line_color="orange",
                      annotation_text=f"median {vline:.3f}")
    fig.update_layout(height=height, title=title,
                      xaxis_title="", yaxis_title="Count", **_LAYOUT)
    return fig


def _heatmap_fig(z, x_labels, y_labels, title="", zmid=0.5, height=240,
                 colorscale=None, fmt=".1%"):
    cs = colorscale or [[0, "#7f1d1d"], [0.4, "#b91c1c"],
                        [0.5, "#374151"], [0.6, "#065f46"], [1, "#052e16"]]
    text = [[f"{v:{fmt}}" if v is not None else "" for v in row] for row in z]
    fig  = go.Figure(go.Heatmap(
        z=z, x=x_labels, y=y_labels,
        text=text, texttemplate="%{text}",
        colorscale=cs, zmid=zmid,
        zmin=zmid - 0.15, zmax=zmid + 0.15,
        showscale=True,
        colorbar=dict(title="WR", tickformat=".0%"),
    ))
    fig.update_layout(height=height, xaxis=dict(side="top"),
                      title=title, **_LAYOUT)
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ══════════════════════════════════════════════════════════════════════════════

EXEC_MODELS = {
    "market_1acc":   "Market Breakout (1 Acc)",
    "cisd_1acc":     "CISD Pullback (1 Acc)",
    "cascade_2tier": "2-Tier Cascade (2 Accs)",
    "cascade_3tier": "3-Tier Cascade (3 Accs)",
}


def render():
    # ── Sidebar controls ──────────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("Fractal Sweep")
        data = _load()
        if not data:
            st.error(f"model_stats.json not found:\n{JSON_PATH}")
            st.stop()

        model_key = st.selectbox(
            "Model",
            options=list(MODEL_LABELS.keys()),
            format_func=lambda k: MODEL_LABELS[k],
        )
        profile_key = st.selectbox(
            "Risk Profile",
            options=["simple_1r", "raw_measure"],
            format_func=lambda k: {"simple_1r": "Simple 1R", "raw_measure": "Raw Measure"}[k],
        )
        st.divider()
        st.subheader("Filters")
        f3  = st.toggle(FILTER_LABELS["F3"],  value=False)
        f4  = st.toggle(FILTER_LABELS["F4"],  value=False)
        smt = st.toggle(FILTER_LABELS["SMT"], value=False)
        st.divider()
        st.subheader("Account")
        account_size   = st.number_input("Account size ($)",   value=2000, step=500)
        risk_per_trade = st.number_input("Risk per trade ($)", value=200,  step=25)
        st.divider()
        if st.button("Clear cache", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


    profile    = data[model_key]["profiles"][profile_key]
    meta       = profile["meta"]
    trading_days = meta['trading_days'] 
    #all_trades = profile["recent_trades"]
    all_trades = _load_trades(model_key, profile_key)
    trades     = _apply_filters(all_trades, f3, f4, smt)
    stats_d    = _summary(trades)
    any_filter = f3 or f4 or smt

    # ── Header ────────────────────────────────────────────────────────────────
    st.title(f"Fractal Sweep — {MODEL_LABELS[model_key]}")
    active = " · ".join(k for k, v in {"F3": f3, "F4": f4, "SMT": smt}.items() if v)
    st.caption(f"Data: {meta['date_range']}  ·  {active or 'No filters'}  ·  Profile: {profile_key}")

    if not stats_d:
        st.warning("No trades match the current filter combination.")
        st.stop()

    # ── Global KPI row ────────────────────────────────────────────────────────
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Trades",        f"{stats_d['n']:,}")
    k2.metric("Win Rate",      f"{stats_d['wr']:.1%}")
    k3.metric("EV / trade",    f"{stats_d['ev']:+.3f}R")
    k4.metric("Profit Factor", f"{stats_d['pf']:.3f}")
    k5.metric("Setups / day",  f"{meta['setups_per_day_ny']:.2f}")
    k6.metric("Date range",    meta["date_range"].replace(" to ", "→").split("→")[0][:7] + "…")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_ov, tab_edge, tab_filt, tab_risk, tab_exc, tab_trades, tab_cascade = st.tabs(
        ["Overview", "Edge", "Filters", "Risk", "Excursion", "Trades", "Cascade"]
    )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — OVERVIEW
    # ══════════════════════════════════════════════════════════════════════════
    with tab_ov:
        st.subheader("Model Anatomy")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("""
**Setup conditions**
1. Prior candle (HTF) sweeps to new extreme
2. Price returns inside the prior range
3. CISD fires (Change in State of Delivery) on the LTF

**Trade mechanics**
- Entry: next bar open after CISD bar closes
- Stop: sweep extreme
- Target: 1R (simple_1r) / measured (raw_measure)
""")
        with c2:
            st.markdown(f"""
| | |
|---|---|
| Sweep TF | {meta.get('sweep_mode', '—')} |
| CISD TF | {meta.get('cisd_mode_label', '—')} |
| Instrument | {meta.get('instrument', 'NQ')} |
| Min risk | {meta.get('avg_risk_pts', '—')} pts (avg) |
| RR target | {meta.get('rr_target', 1.0)}:1 |
| Trading days | {meta.get('trading_days', '—'):,} |
| Total raw setups | {meta.get('total_raw', '—'):,} |
| Expired setups | {meta.get('total_expired', '—'):,} |
""")

        st.divider()
        st.subheader("Equity Curve")
        eq_df_ov = _equity_curve(tuple(trades), account_size, risk_per_trade)
        if not eq_df_ov.empty:
            st.plotly_chart(
                _line(eq_df_ov, "date", "equity", hline=account_size,
                      x_label="Date", y_label="Equity ($)"),
                use_container_width=True, key="fs_ov_equity"
            )

        st.divider()
        st.subheader("Streak Statistics")
        _sorted_ov = sorted(trades, key=lambda x: (x["date"], x["hr"], x["mn"]))
        _runs_l, _runs_w, _cl, _cw = [], [], 0, 0
        for t in _sorted_ov:
            if t["outcome"] == "LOSS":
                _cl += 1
                if _cw > 0: _runs_w.append(_cw); _cw = 0
            else:
                _cw += 1
                if _cl > 0: _runs_l.append(_cl); _cl = 0
        if _cl > 0: _runs_l.append(_cl)
        if _cw > 0: _runs_w.append(_cw)
        max_l_run = max(_runs_l) if _runs_l else 0
        avg_l_run = sum(_runs_l) / len(_runs_l) if _runs_l else 0.0
        max_w_run = max(_runs_w) if _runs_w else 0
        avg_w_run = sum(_runs_w) / len(_runs_w) if _runs_w else 0.0
        sk1, sk2, sk3, sk4 = st.columns(4)
        sk1.metric("Max Consec Losses", max_l_run)
        sk2.metric("Avg Consec Losses", f"{avg_l_run:.1f}")
        sk3.metric("Max Consec Wins",   max_w_run)
        sk4.metric("Avg Consec Wins",   f"{avg_w_run:.1f}")

        st.divider()
        st.subheader("Direction Summary — Long vs Short")
        dir_data = profile.get("dir_summary", [])
        if dir_data:
            dc1, dc2 = st.columns(2)
            for col, row in zip([dc1, dc2], dir_data):
                with col:
                    d = row["direction"]
                    colour = "normal" if d == "LONG" else "inverse"
                    st.metric(
                        f"{d}",
                        f"{row['wr']:.1%} WR",
                        f"{row['ev']:+.3f}R EV  ·  N={row['n']:,}",
                    )
                    st.progress(row["wr"])
                    st.caption(
                        f"PF {row['pf']:.3f}  ·  Avg risk {row['avg_risk_pts']:.1f}pts  "
                        f"·  Avg MAE {row['avg_mae']:.2%}  ·  Avg MFE {row['avg_mfe']:.2%}"
                    )

        st.divider()
        st.subheader("Risk Profile Comparison — simple_1r vs raw_measure")
        prof_rows = []
        for pk in ["simple_1r", "raw_measure"]:
            pm = data[model_key]["profiles"].get(pk, {}).get("meta", {})
            if pm:
                prof_rows.append({
                    "Profile":    pk,
                    "N":          pm.get("total_wl", "—"),
                    "Win Rate":   f"{pm.get('win_rate', 0):.1%}",
                    "EV (R)":     f"{pm.get('ev_per_trade', 0):+.3f}",
                    "PF":         f"{pm.get('profit_factor', 0):.3f}",
                    "Avg Risk pts": f"{pm.get('avg_risk_pts', 0):.1f}",
                })
        if prof_rows:
            st.dataframe(pd.DataFrame(prof_rows), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Classification Breakdown")
        bc = profile.get("by_classification", {})
        if bc and isinstance(bc, dict) and bc:
            bc_rows = [{"Class": k, **{kk: vv for kk, vv in v.items()
                                       if kk in ("n", "wr", "ev", "pf")}}
                       for k, v in bc.items()]
            bc_df = pd.DataFrame(bc_rows)
            bc_df["wr"] = bc_df["wr"].map("{:.1%}".format)
            bc_df["ev"] = bc_df["ev"].map("{:+.3f}".format)
            bc_df["pf"] = bc_df["pf"].map("{:.3f}".format)
            st.dataframe(bc_df, use_container_width=True, hide_index=True)
        else:
            st.info("No classification data in this output (DATE_CLASSIFICATION not populated).")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — EDGE
    # ══════════════════════════════════════════════════════════════════════════
    with tab_edge:
        # ── EV heatmap (Hour × DOW) ───────────────────────────────────────────
        st.subheader("EV Heatmap — Hour × Day of Week")
        hm_data = profile.get("heatmap", [])
        if hm_data:
            hrs  = sorted({r["hr"] for r in hm_data})
            dows = sorted({r["dow"] for r in hm_data})
            z_ev, z_wr, x_lbl, y_lbl = [], [], [], []
            x_lbl = [f"{h:02d}:00" for h in hrs]
            y_lbl = [DOW_NAMES.get(d, str(d)) for d in dows]
            lookup = {(r["hr"], r["dow"]): r for r in hm_data}
            for dw in dows:
                z_ev.append([lookup.get((h, dw), {}).get("ev") for h in hrs])
                z_wr.append([lookup.get((h, dw), {}).get("wr") for h in hrs])

            col_ev, col_wr = st.columns(2)
            with col_ev:
                text_ev = [[f"{v:+.3f}R" if v is not None else "" for v in row] for row in z_ev]
                fig = go.Figure(go.Heatmap(
                    z=z_ev, x=x_lbl, y=y_lbl,
                    text=text_ev, texttemplate="%{text}",
                    colorscale=[[0,"#7f1d1d"],[0.5,"#374151"],[1,"#065f46"]],
                    zmid=0, showscale=True,
                    colorbar=dict(title="EV (R)"),
                ))
                fig.update_layout(height=240, xaxis=dict(side="top"),
                                  title="Expected Value per Trade", **_LAYOUT)
                st.plotly_chart(fig, use_container_width=True, key="fs_edge_ev_hm")
            with col_wr:
                st.plotly_chart(
                    _heatmap_fig(z_wr, x_lbl, y_lbl, title="Win Rate", zmid=0.5),
                    use_container_width=True, key="fs_edge_wr_hm"
                )

        st.divider()

        # ── Yearly EV bar chart ───────────────────────────────────────────────
        st.subheader("Temporal Edge Stability — Yearly EV")
        by_year = _recompute_by_year(tuple(trades)) if any_filter else profile["by_year"]
        yr_df   = pd.DataFrame(by_year)
        col_yr, col_yr_wr = st.columns(2)
        with col_yr:
            fig_ev = px.bar(yr_df, x="yr", y="ev",
                            labels={"yr": "Year", "ev": "EV (R)"},
                            color="ev",
                            color_continuous_scale=["#d62728","#374151","#2ca02c"],
                            range_color=[-0.15, 0.15])
            fig_ev.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_ev.update_layout(height=240, coloraxis_showscale=False, **_LAYOUT)
            st.plotly_chart(fig_ev, use_container_width=True, key="fs_edge_yearly_ev")
        with col_yr_wr:
            wr_df  = yr_df.copy()
            wr_df["wr_fmt"] = wr_df["wr"].map("{:.1%}".format)
            st.plotly_chart(
                _bar(wr_df, "yr", "wr", hline=0.5, text_col="wr_fmt",
                     x_label="Year", y_label="Win Rate"),
                use_container_width=True, key="fs_edge_yearly_wr"
            )

        st.divider()

        # ── Session + DOW ─────────────────────────────────────────────────────
        st.subheader("Session & Day Decomposition")
        col_sess, col_dow = st.columns(2)
        with col_sess:
            st.markdown("**By Session**")
            sess_data = profile.get("by_session", [])
            if sess_data:
                sess_df = pd.DataFrame(sess_data)
                sess_disp = sess_df.groupby("session").agg(
                    n=("n","sum"), wins=("wins","sum")
                ).reset_index()
                sess_disp["wr"] = sess_disp["wins"] / sess_disp["n"]
                sess_disp["WR"] = sess_disp["wr"].map("{:.1%}".format)
                sess_disp = sess_disp.sort_values("n", ascending=False)
                st.dataframe(sess_disp[["session","n","WR"]]
                             .rename(columns={"session":"Session","n":"N"}),
                             use_container_width=True, hide_index=True)
        with col_dow:
            st.markdown("**By Day of Week**")
            dow_data = _recompute_by_dow(tuple(trades)) if any_filter else [
                {**r, "dow_name": DOW_NAMES.get(r["dow"], str(r["dow"]))}
                for r in profile["by_dow"] if r["n"] >= 5
            ]
            if dow_data:
                dow_df = pd.DataFrame(dow_data)
                dow_df["WR"] = dow_df["wr"].map("{:.1%}".format)
                dow_df["EV"] = dow_df["ev"].map("{:+.3f}".format)
                st.dataframe(dow_df[["dow_name","n","WR","EV"]]
                             .rename(columns={"dow_name":"Day","n":"N"}),
                             use_container_width=True, hide_index=True)

        st.divider()

        # ── Highest / Lowest conviction setups ────────────────────────────────
        col_top, col_bot = st.columns(2)
        with col_top:
            st.subheader("Strongest Edge  (top combos)")
            top = profile.get("top_combos", [])
            if top:
                tc = pd.DataFrame(top)[["label","n","wr","ev","pf","direction"]]
                tc.columns = ["Setup","N","WR","EV","PF","Dir"]
                tc["WR"] = tc["WR"].map("{:.1%}".format)
                tc["EV"] = tc["EV"].map("{:+.3f}".format)
                tc["PF"] = tc["PF"].map("{:.3f}".format)
                st.dataframe(tc.head(15), use_container_width=True, hide_index=True)
        with col_bot:
            st.subheader("Weakest Edge  (worst combos)")
            worst = profile.get("worst_combos", [])
            if worst:
                wc = pd.DataFrame(worst)[["label","n","wr","ev","pf","direction"]]
                wc.columns = ["Setup","N","WR","EV","PF","Dir"]
                wc["WR"] = wc["WR"].map("{:.1%}".format)
                wc["EV"] = wc["EV"].map("{:+.3f}".format)
                wc["PF"] = wc["PF"].map("{:.3f}".format)
                st.dataframe(wc.head(15), use_container_width=True, hide_index=True)

        st.divider()

        # ── Win rate by hour ──────────────────────────────────────────────────
        st.subheader("Win Rate by Hour")
        hr_data = _recompute_by_hour(tuple(trades)) if any_filter else \
                  [r for r in profile["by_hour"] if r["n"] >= 5]
        if hr_data:
            hr_df       = pd.DataFrame(hr_data)
            hr_df["wr_fmt"] = hr_df["wr"].map("{:.1%}".format)
            st.plotly_chart(
                _bar(hr_df, "hr", "wr", hline=0.5, text_col="wr_fmt",
                     x_label="Hour (ET)", y_label="Win Rate"),
                use_container_width=True, key="fs_edge_hr_wr"
            )

        st.divider()

        # ── SMT split ─────────────────────────────────────────────────────────
        st.subheader("SMT Divergence Split")
        smt_df = pd.DataFrame(profile.get("smt_summary", []))
        if not smt_df.empty:
            smt_df["Group"]    = smt_df["smt"].map({True: "SMT (NQ only)", False: "Non-SMT"})
            smt_df["Win Rate"] = smt_df["wr"].map("{:.1%}".format)
            smt_df["EV (R)"]   = smt_df["ev"].map("{:+.3f}".format)
            smt_df["PF"]       = smt_df["pf"].map("{:.3f}".format)
            st.dataframe(smt_df[["Group","n","Win Rate","EV (R)","PF"]],
                         use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — FILTERS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_filt:
        st.subheader("Filter Variant Analysis — all 8 combinations")
        fv = profile.get("filter_variants", {})
        combos = fv.get("all_combinations", [])
        if combos:
            cdf = pd.DataFrame(combos)[["label","n","wr","ev","pf","max_dd_pct"]]
            cdf.columns = ["Combination","N","Win Rate","EV (R)","PF","Max DD %"]
            cdf["Win Rate"] = cdf["Win Rate"].map("{:.1%}".format)
            cdf["EV (R)"]   = cdf["EV (R)"].map("{:+.3f}".format)
            cdf["PF"]       = cdf["PF"].map("{:.3f}".format)
            cdf["Max DD %"] = cdf["Max DD %"].map("{:.1f}%".format)
            cdf = cdf.sort_values("EV (R)", ascending=False)
            st.dataframe(cdf, use_container_width=True, hide_index=True)

        best = fv.get("best_combination")
        if best:
            st.success(f"Best combination: **{best.get('label','—')}**  "
                       f"WR {best.get('wr',0):.1%}  EV {best.get('ev',0):+.3f}R  "
                       f"N={best.get('n',0):,}")

        st.divider()
        st.subheader("Individual Filter Impact")
        indiv = fv.get("individual_removal", [])
        if indiv:
            idf = pd.DataFrame(indiv)
            for col in ["wr","ev","pf"]:
                if col in idf.columns:
                    fmt = "{:.1%}" if col == "wr" else ("{:+.3f}" if col == "ev" else "{:.3f}")
                    idf[col] = idf[col].map(fmt.format)
            st.dataframe(idf, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Outcome Distribution")
        r_hist = profile.get("r_hist", [])
        if r_hist:
            rh_df = pd.DataFrame(r_hist)
            fig_rh = px.bar(rh_df, x="bucket", y="n",
                            labels={"bucket": "R bucket", "n": "Count"},
                            color_discrete_sequence=["#3b82f6"])
            fig_rh.update_layout(height=240, **_LAYOUT)
            st.plotly_chart(fig_rh, use_container_width=True, key="fs_filt_r_hist")

        st.divider()
        st.subheader("Win Rate by Year — Regime Check")
        yr_data = _recompute_by_year(tuple(trades)) if any_filter else profile["by_year"]
        if yr_data:
            yr_df2 = pd.DataFrame(yr_data)
            yr_df2["wr_fmt"] = yr_df2["wr"].map("{:.1%}".format)
            col_yrw, col_yrt = st.columns([2, 1])
            with col_yrw:
                st.plotly_chart(
                    _bar(yr_df2, "yr", "wr", hline=0.5, text_col="wr_fmt",
                         x_label="Year", y_label="Win Rate"),
                    use_container_width=True, key="fs_filt_yr_wr"
                )
            with col_yrt:
                yr_disp = yr_df2[["yr","n","wr_fmt"]].copy()
                yr_disp.columns = ["Year","N","WR"]
                st.dataframe(yr_disp, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Equity Curve")
        eq_df = _equity_curve(tuple(trades), account_size, risk_per_trade)
        if not eq_df.empty:
            st.plotly_chart(
                _line(eq_df, "date", "equity", hline=account_size,
                      x_label="Date", y_label="Equity ($)"),
                use_container_width=True, key="fs_filt_equity"
            )

        st.divider()
        st.subheader("Stop Size Distribution")
        rd = profile.get("risk_dist", {})
        if rd and isinstance(rd, dict):
            col_rd1, col_rd2 = st.columns(2)
            with col_rd1:
                pts = [
                    ("Mean", rd.get("mean")),
                    ("Median", rd.get("median")),
                    ("P25", rd.get("p25")),
                    ("P75", rd.get("p75")),
                    ("P90", rd.get("p90")),
                    ("Max", rd.get("max")),
                ]
                st.dataframe(
                    pd.DataFrame(pts, columns=["Stat", "Value"]),
                    use_container_width=True, hide_index=True
                )
            with col_rd2:
                edges  = rd.get("hist_edges", [])
                counts = rd.get("hist_counts", [])
                if edges and counts:
                    mids = [(edges[i]+edges[i+1])/2 for i in range(len(counts))]
                    fig_rd = go.Figure(go.Bar(x=mids, y=counts, marker_color="#8b5cf6",
                                             marker_opacity=0.75))
                    fig_rd.update_layout(height=220, xaxis_title="Risk (pts)",
                                        yaxis_title="Count", **_LAYOUT)
                    st.plotly_chart(fig_rd, use_container_width=True, key="fs_filt_risk_dist")

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — RISK
    # ══════════════════════════════════════════════════════════════════════════
    with tab_risk:
        st.subheader("Account Risk Statistics")
        rs = profile.get("risk_stats", {})

        # Compute dollar metrics live from filtered trades + user's sidebar inputs
        def _risk_metrics(trades, account, risk):
            if not trades:
                return {}
            sorted_t = sorted(trades, key=lambda x: (x["date"], x["hr"], x["mn"]))
            eq = float(account); peak = eq; min_eq = eq; max_dd_usd = 0.0; max_dd_pct = 0.0
            daily_r: dict = {}
            for t in sorted_t:
                r_val = t.get("r") or 0.0
                eq += r_val * risk
                if eq < min_eq: min_eq = eq
                if eq > peak: peak = eq
                dd_usd = peak - eq
                dd_pct = dd_usd / peak * 100 if peak > 0 else 0.0
                if dd_usd > max_dd_usd:
                    max_dd_usd = dd_usd
                    max_dd_pct = dd_pct
                d = t["date"][:10]
                daily_r[d] = daily_r.get(d, 0.0) + r_val * risk
            total_pnl = eq - account
            blown = eq <= 0
            dp = list(daily_r.values())
            sharpe = None
            if len(dp) > 1:
                arr = np.array(dp)
                if arr.std(ddof=1) > 0:
                    sharpe = round(float(arr.mean() / arr.std(ddof=1) * np.sqrt(252)), 2)
            return dict(total_pnl=total_pnl, min_eq=min_eq, max_dd_usd=max_dd_usd,
                        max_dd_pct=max_dd_pct, blown=blown, sharpe=sharpe)

        rm = _risk_metrics(trades, account_size, risk_per_trade)
        if rm:
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            col_r1.metric("Total P&L",        f"${rm['total_pnl']:+,.0f}")
            col_r2.metric("Max DD",            f"${rm['max_dd_usd']:,.0f}  ({rm['max_dd_pct']:.1f}%)")
            col_r3.metric("Sharpe",            f"{rm['sharpe']:+.2f}" if rm['sharpe'] is not None else "—")
            col_r4.metric("Max consec losses", str(rs.get("max_consec_losses", "—")))
            col_r5, col_r6, col_r7, col_r8 = st.columns(4)
            col_r5.metric("Max consec wins",   str(rs.get("max_consec_wins", "—")))
            col_r6.metric("Min equity",        f"${rm['min_eq']:,.0f}")
            col_r7.metric("Account blown",     "YES" if rm["blown"] else "NO")
            col_r8.metric("Certainty Equiv",   f"{rs.get('ce', 0):+.4f}R")

        st.divider()
        st.subheader("R Distribution")
        r_hist = profile.get("r_hist", [])
        if r_hist:
            rh_df = pd.DataFrame(r_hist)
            fig_r = px.bar(rh_df, x="bucket", y="n",
                           labels={"bucket": "Outcome bucket", "n": "Count"},
                           color_discrete_sequence=["#3b82f6"])
            fig_r.update_layout(height=260, **_LAYOUT)
            st.plotly_chart(fig_r, use_container_width=True, key="fs_risk_r_hist")

        st.divider()
        st.subheader("Win Rate by Year")
        yr_d   = _recompute_by_year(tuple(trades)) if any_filter else profile["by_year"]
        yr_df3 = pd.DataFrame(yr_d)
        yr_df3["wr_fmt"] = yr_df3["wr"].map("{:.1%}".format)
        st.plotly_chart(
            _bar(yr_df3, "yr", "wr", hline=0.5, text_col="wr_fmt",
                 x_label="Year", y_label="Win Rate"),
            use_container_width=True, key="fs_risk_yr_wr"
        )

        st.divider()
        st.subheader("Equity Curve — Cumulative P&L")
        eq_df2 = _equity_curve(tuple(trades), account_size, risk_per_trade)
        if not eq_df2.empty:
            st.plotly_chart(
                _line(eq_df2, "date", "equity", hline=account_size,
                      x_label="Date", y_label="Equity ($)"),
                use_container_width=True, key="fs_risk_equity"
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 5 — EXCURSION (MAE / MFE)
    # ══════════════════════════════════════════════════════════════════════════
    with tab_exc:
        st.subheader("MAE — Maximum Adverse Excursion")

        rich_mae = profile.get("rich_mae", {})
        rich_mfe = profile.get("rich_mfe", {})

        def _excursion_section(rich, label, color, key_prefix):
            if not rich:
                st.info(f"No {label} data available.")
                return
            hist = rich.get("histogram", {})
            edges  = hist.get("edges", [])
            counts = hist.get("counts", [])
            median = rich.get("median", 0)
            clusters = rich.get("clusters", [])

            col_h, col_s = st.columns([2, 1])
            with col_h:
                if edges and counts:
                    st.plotly_chart(
                        _hist_fig(edges, counts, color=color, height=260,
                                  vline=median, title=f"{label} Distribution"),
                        use_container_width=True, key=f"fs_{key_prefix}_hist"
                    )
            with col_s:
                pct = rich.get("percentiles", {})
                pct_rows = [(k.upper(), f"{v:.4f}") for k, v in pct.items()]
                st.markdown(f"**{label} Percentiles**")
                st.dataframe(pd.DataFrame(pct_rows, columns=["Pct", "Value"]),
                             use_container_width=True, hide_index=True)

            if clusters:
                st.markdown(f"**{label} Clusters**")
                cl_df = pd.DataFrame(clusters)[["label","range","n","pct_of_trades","mean","median"]]
                cl_df.columns = ["Cluster","Range","N","% Trades","Mean","Median"]
                cl_df["% Trades"] = cl_df["% Trades"].map("{:.1f}%".format)
                cl_df["Mean"]     = cl_df["Mean"].map("{:.4f}".format)
                cl_df["Median"]   = cl_df["Median"].map("{:.4f}".format)
                st.dataframe(cl_df, use_container_width=True, hide_index=True)

        _excursion_section(rich_mae, "MAE", "#ef4444", "mae")

        st.divider()
        st.subheader("MFE — Maximum Favourable Excursion")
        _excursion_section(rich_mfe, "MFE", "#10b981", "mfe")

        st.divider()
        st.subheader("MAE Bell — SL Sweep Probabilities")
        rs = profile.get("risk_stats", {})
        bell = rs.get("mae_bell", {}) if rs else {}
        if bell:
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                st.markdown(f"""
| Threshold | % Trades reaching |
|---|---|
| Mean {bell.get('mean',0):.3f} | {bell.get('cov_mean',0):.1f}% |
| +0.5σ {bell.get('plus_0_5s',0):.3f} | {bell.get('cov_0_5s',0):.1f}% |
| +1σ {bell.get('plus_1s',0):.3f} | {bell.get('cov_1s',0):.1f}% |
| +1.5σ {bell.get('plus_1_5s',0):.3f} | {bell.get('cov_1_5s',0):.1f}% |
| +2σ {bell.get('plus_2s',0):.3f} | {bell.get('cov_2s',0):.1f}% |
""")

        st.divider()
        st.subheader("Wins vs Losses — MAE & MFE")
        col_w, col_l = st.columns(2)
        for col, key_w, key_l, lbl in [
            (col_w, "rich_mae_wins", "rich_mae_losses", "MAE"),
            (col_l, "rich_mfe_wins", "rich_mfe_losses", "MFE"),
        ]:
            with col:
                rw = profile.get(key_w, {})
                rl = profile.get(key_l, {})
                rows = []
                for grp, r in [("Wins", rw), ("Losses", rl)]:
                    if r:
                        rows.append({"Group": grp,
                                     "N": r.get("n","—"),
                                     "Mean": f"{r.get('mean',0):.4f}",
                                     "Median": f"{r.get('median',0):.4f}",
                                     "Std": f"{r.get('std',0):.4f}"})
                if rows:
                    st.markdown(f"**{lbl} — Wins vs Losses**")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("SL Sweep Probabilities (MAE thresholds)")
        sl_sweep = rich_mae.get("sl_sweep", []) if rich_mae else []
        if sl_sweep:
            sw_df = pd.DataFrame(sl_sweep)[["threshold","exceed_pct","p_recovered","p_ko"]]
            sw_df.columns = ["MAE Threshold","% Trades Reach","P(recover)","P(stop out)"]
            sw_df["MAE Threshold"]  = sw_df["MAE Threshold"].map("{:.4f}".format)
            sw_df["% Trades Reach"] = sw_df["% Trades Reach"].map("{:.1f}%".format)
            sw_df["P(recover)"]     = sw_df["P(recover)"].map("{:.2%}".format)
            sw_df["P(stop out)"]    = sw_df["P(stop out)"].map("{:.2%}".format)
            st.dataframe(sw_df.head(20), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 6 — TRADES
    # ══════════════════════════════════════════════════════════════════════════
    with tab_trades:
        st.subheader("Trades")
        st.caption(f"{len(trades):,} trades (newest first)")

        col_avail = [c for c in [
            "date", "direction", "hr", "session", "dow_name",
            "entry_price", "sweep_extreme", "target_price",
            "risk_pts", "r", "outcome",
            "mae_pct", "mfe_pct",
            "passes_f3", "passes_f4", "smt", "classification"
        ] if c in (trades[0].keys() if trades else [])]

        rt_df = pd.DataFrame(trades)[col_avail].copy()
        rt_df = rt_df.sort_values("date", ascending=False)

        col_cfg = {
            "r":           st.column_config.NumberColumn("R",        format="%.2f"),
            "entry_price": st.column_config.NumberColumn("Entry",    format="%.2f"),
            "sweep_extreme": st.column_config.NumberColumn("Stop",   format="%.2f"),
            "target_price":  st.column_config.NumberColumn("Target", format="%.2f"),
            "risk_pts":    st.column_config.NumberColumn("Risk pts", format="%.1f"),
            "mae_pct":     st.column_config.NumberColumn("MAE %",   format="%.3f"),
            "mfe_pct":     st.column_config.NumberColumn("MFE %",   format="%.3f"),
            "passes_f3":   st.column_config.CheckboxColumn("F3"),
            "passes_f4":   st.column_config.CheckboxColumn("F4"),
            "smt":         st.column_config.CheckboxColumn("SMT"),
        }
        st.dataframe(
            rt_df, use_container_width=True, hide_index=True,
            column_config=col_cfg, height=500,
        )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 7 — CASCADE EXECUTION MODEL
    # ══════════════════════════════════════════════════════════════════════════
    with tab_cascade:
        st.subheader("Execution Model Configuration")

        # --- Model & capital inputs (now inside the tab) ---
        exec_model = st.selectbox(
            "Execution Model",
            options=list(EXEC_MODELS.keys()),
            format_func=lambda k: EXEC_MODELS[k],
            key="cascade_exec_model",
        )
        col1, col2 = st.columns(2)
        with col1:
            total_capital = st.number_input("Total Capital ($)", value=float(account_size), step=500.0)
        with col2:
            total_risk_pct = st.number_input(
                "Total Risk (% of capital)", value=5.0, step=0.5, min_value=0.1, max_value=50.0
            )

        # --- Derived values ---
        if exec_model == "market_1acc":
            n_accs = 1
            per_acc_capital = total_capital
            per_acc_risk    = total_capital * total_risk_pct / 100.0
        elif exec_model == "cisd_1acc":
            n_accs = 1
            per_acc_capital = total_capital
            per_acc_risk    = total_capital * total_risk_pct / 100.0
        elif exec_model == "cascade_2tier":
            n_accs = 2
            per_acc_capital = total_capital / 2
            per_acc_risk    = total_capital * total_risk_pct / 100.0 / 2
        elif exec_model == "cascade_3tier":
            n_accs = 3
            per_acc_capital = total_capital / 3
            per_acc_risk    = total_capital * total_risk_pct / 100.0 / 3

        total_risk_usd = total_capital * total_risk_pct / 100.0

        st.caption(
            f"Capital per tier: ${per_acc_capital:,.0f}  |  "
            f"Risk per tier: ${per_acc_risk:,.2f}  |  "
            f"Total risk: ${total_risk_usd:,.2f}"
        )

        # --- Filter feedback ---
        active_filters = ", ".join(
            k for k, v in {"F3": f3, "F4": f4, "SMT": smt}.items() if v
        ) or "None"
        n_trades_cascade = len(trades)
        st.info(f"Filters active: {active_filters}  —  {n_trades_cascade} trades eligible")

        # --- Check required columns ---
        if exec_model != "market_1acc":
            required_cols = ["cisd_level", "sl_price", "level_33", "level_50", "level_66",
                            "deepest_adverse_price"]
            missing = [c for c in required_cols if not (trades and c in trades[0])]
            if missing:
                st.warning(
                    f"Missing columns: {', '.join(missing)}. "
                    "Re-run engine to generate them, then reload."
                )
                st.stop()

        # --- Run cascade PnL ---
        def _cascade_pnl(trades, exec_model, total_risk_usd, n_tiers):
            results = []
            per_risk_acc = total_risk_usd / max(n_tiers, 1)
            for t in trades:
                d         = t.get("direction")
                outcome   = t.get("outcome", "")
                entry_pr  = t.get("entry_price")
                sl_pr     = t.get("sl_price")
                cisd      = t.get("cisd_level")
                l33       = t.get("level_33")
                l50       = t.get("level_50")
                l66       = t.get("level_66")
                target_pr = t.get("target_price")
                dap       = t.get("deepest_adverse_price")
                base_r    = t.get("r", 0.0) or 0.0

                def _reached(level):
                    if dap is None or level is None:
                        return False
                    return dap <= level if d == "LONG" else dap >= level

                def _leg_r(entry_lvl, stop_lvl, original_entry, original_sl):
                    if not _reached(entry_lvl):
                        return 0.0, False
                    if entry_lvl is None or stop_lvl is None or target_pr is None:
                        return 0.0, True
                    risk_leg = abs(entry_lvl - stop_lvl)
                    if risk_leg <= 0:
                        return 0.0, True
                    if _reached(stop_lvl):
                        return -1.0, True
                    if outcome == "WIN":
                        return round(abs(target_pr - entry_lvl) / risk_leg, 3), True
                    if outcome == "LOSS":
                        return -1.0, True
                    # EXPIRED: scale base R by leg's share of original risk
                    if original_entry is not None and original_sl is not None \
                    and abs(original_entry - original_sl) > 0:
                        scale = risk_leg / abs(original_entry - original_sl)
                        return round(base_r * scale, 3), True
                    return round(base_r, 3), True

                if exec_model == "market_1acc":
                    results.append({
                        "r_total": base_r, "filled": True,
                        "r_acc1": base_r, "filled_acc1": True,
                        "pnl_usd": base_r * per_risk_acc,
                    })
                elif exec_model == "cisd_1acc":
                    r1, fa1 = _leg_r(cisd, sl_pr, entry_pr, sl_pr)
                    results.append({
                        "r_total": r1, "filled": fa1,
                        "r_acc1": r1, "filled_acc1": fa1,
                        "pnl_usd": r1 * per_risk_acc,
                    })
                elif exec_model == "cascade_2tier":
                    r1, fa1 = _leg_r(cisd, l50, entry_pr, sl_pr)
                    r2, fa2 = _leg_r(l50,  sl_pr, entry_pr, sl_pr)
                    results.append({
                        "r_total": round(r1 + r2, 3), "filled": fa1 or fa2,
                        "r_acc1": r1, "filled_acc1": fa1,
                        "r_acc2": r2, "filled_acc2": fa2,
                        "pnl_usd": round((r1 + r2) * per_risk_acc, 2),
                    })
                elif exec_model == "cascade_3tier":
                    r1, fa1 = _leg_r(cisd, l33, entry_pr, sl_pr)
                    r2, fa2 = _leg_r(l33,  l66, entry_pr, sl_pr)
                    r3, fa3 = _leg_r(l66,  sl_pr, entry_pr, sl_pr)
                    results.append({
                        "r_total": round(r1 + r2 + r3, 3), "filled": fa1 or fa2 or fa3,
                        "r_acc1": r1, "filled_acc1": fa1,
                        "r_acc2": r2, "filled_acc2": fa2,
                        "r_acc3": r3, "filled_acc3": fa3,
                        "pnl_usd": round((r1 + r2 + r3) * per_risk_acc, 2),
                    })
                else:
                    results.append({"r_total": 0.0, "filled": False, "pnl_usd": 0.0})
            return results

        n_tiers = n_accs
        per_risk_usd = total_risk_usd / max(n_tiers, 1)

        # Sort trades chronologically before all per-tier analysis
        sorted_pairs = sorted(
            zip(trades, _cascade_pnl(trades, exec_model, total_risk_usd, n_tiers)),
            key=lambda x: (x[0]["date"], x[0].get("hr", 0), x[0].get("mn", 0)),
        )
        leg_results = [lr for _, lr in sorted_pairs]
        sorted_trades = [tr for tr, _ in sorted_pairs]
        n_total = len(sorted_trades)

        # Per-tier accumulators
        tier_fills  = {t: 0   for t in range(1, n_tiers + 1)}
        tier_wins   = {t: 0   for t in range(1, n_tiers + 1)}
        tier_pnl    = {t: 0.0 for t in range(1, n_tiers + 1)}
        tier_r_sum  = {t: 0.0 for t in range(1, n_tiers + 1)}
        tier_r_win  = {t: 0.0 for t in range(1, n_tiers + 1)}
        tier_r_loss = {t: 0.0 for t in range(1, n_tiers + 1)}
        # Streak tracking: one running counter per tier, closed into streaks_loss list
        streaks_loss   = {t: [] for t in range(1, n_tiers + 1)}
        cur_loss_streak = {t: 0  for t in range(1, n_tiers + 1)}

        for lr in leg_results:
            for t in range(1, n_tiers + 1):
                r_key    = f"r_acc{t}"
                fill_key = f"filled_acc{t}"
                if not (fill_key in lr and lr[fill_key]):
                    continue
                r_val = lr[r_key]
                tier_fills[t] += 1
                tier_pnl[t]   += r_val * per_risk_usd
                tier_r_sum[t] += r_val
                if r_val > 0:
                    tier_wins[t]   += 1
                    tier_r_win[t]  += r_val
                    # win closes any open loss streak
                    if cur_loss_streak[t] > 0:
                        streaks_loss[t].append(cur_loss_streak[t])
                        cur_loss_streak[t] = 0
                else:
                    tier_r_loss[t]      += abs(r_val)
                    cur_loss_streak[t]  += 1

        # Close any streak still open at end of series
        for t in range(1, n_tiers + 1):
            if cur_loss_streak[t] > 0:
                streaks_loss[t].append(cur_loss_streak[t])

        def _streak_stats(runs):
            if not runs:
                return 0, 0.0
            return max(runs), sum(runs) / len(runs)

        # Aggregate across all tiers
        total_filled = sum(tier_fills.values())
        total_wins   = sum(tier_wins.values())
        total_pnl_all = sum(tier_pnl.values())

        st.subheader("Tier Performance")
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.metric("Total P&L (all tiers)", f"${total_pnl_all:,.0f}")
            st.caption(f"Aggregate filled opportunities: {total_filled}")
        with col_t2:
            if total_filled:
                st.metric("Overall Win Rate", f"{total_wins / total_filled:.1%}")
                st.caption(f"{total_wins} wins / {total_filled} filled")
            else:
                st.metric("Overall Win Rate", "N/A")
        with col_t3:
            st.metric("Total trades", n_total)

        # Per‑tier numbers
        st.divider()
        for t in range(1, n_tiers + 1):
            nf       = tier_fills[t]
            wr       = tier_wins[t] / nf if nf else 0.0
            pnl_tier = tier_pnl[t]
            max_cl, avg_cl = _streak_stats(streaks_loss[t])
            with st.expander(
                f"Tier {t} — Initial ${total_capital / n_tiers:,.0f}  ·  "
                f"Risk ${per_risk_usd:,.2f}  ·  {nf} filled  ·  {wr:.1%} WR",
                expanded=(n_tiers == 1),
            ):
                ev_r    = tier_r_sum[t] / nf if nf else 0.0
                pf_tier = tier_r_win[t] / tier_r_loss[t] if tier_r_loss[t] > 0 else float("inf")
                spd     = nf / max(trading_days, 1)

                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Filled",       nf)
                col_b.metric("Win Rate",     f"{wr:.1%}")
                col_c.metric("P&L",          f"${pnl_tier:,.0f}")

                col_d, col_e, col_f = st.columns(3)
                col_d.metric("EV / trade",   f"{ev_r:+.3f}R")
                col_e.metric("Profit Factor", f"{pf_tier:.2f}" if pf_tier < 999 else "∞")
                col_f.metric("Setups / day", f"{spd:.2f}")

                col_g, col_h, _ = st.columns(3)
                col_g.metric("Max Consec Losses", max_cl)
                col_h.metric("Avg Consec Losses", f"{avg_cl:.1f}")

                # Tier equity curve (chronological)
                eq_tier = total_capital / n_tiers
                r_key, fill_key = f"r_acc{t}", f"filled_acc{t}"
                eq_tier_rows = [{"trade_num": 0, "equity": eq_tier}]
                for idx, lr in enumerate(leg_results, 1):
                    if fill_key in lr and lr[fill_key]:
                        eq_tier += lr[r_key] * per_risk_usd
                    eq_tier_rows.append({"trade_num": idx, "equity": round(eq_tier, 2)})
                fig_tier = px.line(pd.DataFrame(eq_tier_rows), x="trade_num", y="equity",
                                   height=200, color_discrete_sequence=["#10b981"])
                fig_tier.add_hline(y=total_capital / n_tiers, line_dash="dash", line_color="gray")
                fig_tier.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                       margin=dict(l=0, r=0, t=10, b=0),
                                       yaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
                st.plotly_chart(fig_tier, use_container_width=True)

        # Combined equity curve
        st.subheader("Combined Equity Curve")
        eq_total = total_capital
        eq_rows = [{"trade_num": 0, "equity": eq_total}]
        for lr in leg_results:
            eq_total += lr.get("pnl_usd", 0)
            eq_rows.append({"trade_num": len(eq_rows), "equity": round(eq_total, 2)})
        fig_comb = px.line(pd.DataFrame(eq_rows), x="trade_num", y="equity", height=300,
                           color_discrete_sequence=["#00b4d8"])
        fig_comb.add_hline(y=total_capital, line_dash="dash", line_color="gray",
                           annotation_text="Initial Capital")
        fig_comb.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                               margin=dict(l=0, r=0, t=10, b=0),
                               yaxis=dict(gridcolor="rgba(128,128,128,0.15)"))
        st.plotly_chart(fig_comb, use_container_width=True)

        # Trade detail table
        st.divider()
        st.subheader("Trade Detail")
        detail_rows = []
        for trade, lr in zip(sorted_trades, leg_results):
            row = {
                "Date":      trade.get("date", ""),
                "Dir":       trade.get("direction", ""),
                "Entry":     trade.get("entry_price"),
                "CISD":      trade.get("cisd_level"),
                "L33":       trade.get("level_33"),
                "L50":       trade.get("level_50"),
                "L66":       trade.get("level_66"),
                "SL":        trade.get("sl_price"),
                "DAP":       trade.get("deepest_adverse_price"),
                "Orig":      trade.get("outcome", ""),
                "Filled":    lr["filled"],
                "R total":   lr["r_total"],
                "PnL $":     lr["pnl_usd"],
            }
            # add per-acc R if available
            if "r_acc1" in lr:
                row["R Acc1"] = lr["r_acc1"]
            if "r_acc2" in lr:
                row["R Acc2"] = lr["r_acc2"]
            if "r_acc3" in lr:
                row["R Acc3"] = lr["r_acc3"]
            detail_rows.append(row)

        detail_df = pd.DataFrame(detail_rows)
        detail_cfg = {
            "Entry":   st.column_config.NumberColumn(format="%.2f"),
            "CISD":    st.column_config.NumberColumn(format="%.2f"),
            "L33":     st.column_config.NumberColumn(format="%.2f"),
            "L50":     st.column_config.NumberColumn(format="%.2f"),
            "L66":     st.column_config.NumberColumn(format="%.2f"),
            "SL":      st.column_config.NumberColumn(format="%.2f"),
            "DAP":     st.column_config.NumberColumn("Deepest Adv", format="%.2f"),
            "Filled":  st.column_config.CheckboxColumn(),
            "R total": st.column_config.NumberColumn(format="%.3f"),
            "PnL $":   st.column_config.NumberColumn(format="%.2f"),
        }
        if "R Acc1" in detail_df.columns:
            detail_cfg["R Acc1"] = st.column_config.NumberColumn(format="%.3f")
            detail_cfg["R Acc2"] = st.column_config.NumberColumn(format="%.3f")
            detail_cfg["R Acc3"] = st.column_config.NumberColumn(format="%.3f")

        st.dataframe(detail_df, use_container_width=True, hide_index=True,
                    column_config=detail_cfg, height=500)