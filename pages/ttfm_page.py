"""
TTrades Fractal Model page — full feature parity with TTrades Fractal Model Analysis/index.html.
Backtest section only (the static canvas diagrams are indicator reference, not dashboard data).
Called from root app.py.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

_ROOT     = Path(__file__).parent.parent
JSON_PATH = _ROOT / "TTrades Fractal Model Analysis" / "ttfm_results.json"


@st.cache_data(show_spinner="Loading TTrades data…")
def _load() -> dict:
    if not JSON_PATH.exists():
        return {}
    with open(JSON_PATH, encoding="utf-8") as f:
        return json.load(f)


_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=0, r=0, t=24, b=0),
    font=dict(size=11),
)
_CS = [[0,"#7f1d1d"],[0.35,"#b91c1c"],[0.5,"#374151"],[0.65,"#065f46"],[1,"#052e16"]]


def _wr_color(wr, be):
    d = wr - be
    if d >=  0.07: return "green"
    if d <= -0.07: return "red"
    return "normal"


def _hm_fig(z, x_labels, y_labels, zmid, title="", height=260):
    text = [[f"{v:.1%}" if v is not None else "—" for v in row] for row in z]
    fig  = go.Figure(go.Heatmap(
        z=z, x=x_labels, y=y_labels,
        text=text, texttemplate="%{text}",
        colorscale=_CS, zmid=zmid,
        zmin=zmid - 0.12, zmax=zmid + 0.12,
        showscale=True, colorbar=dict(title="WR", tickformat=".0%"),
    ))
    fig.update_layout(height=height, title=title,
                      xaxis=dict(side="top"), **_LAYOUT)
    return fig


def _bar_fig(x, y, labels, be, height=280, text=None):
    df  = pd.DataFrame({"x": x, "y": y})
    fig = px.bar(df, x="x", y="y", labels=labels,
                 color="y",
                 color_continuous_scale=["#d62728","#aec7e8","#2ca02c"],
                 range_color=[be - 0.10, be + 0.10],
                 text=text)
    fig.add_hline(y=be, line_dash="dash", line_color="gray",
                  annotation_text=f"BE {be:.1%}", annotation_position="top left")
    fig.update_layout(height=height, coloraxis_showscale=False, **_LAYOUT)
    if text is not None:
        fig.update_traces(textposition="outside")
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY
# ══════════════════════════════════════════════════════════════════════════════

def render():
    d = _load()
    if not d:
        st.error(f"ttfm_results.json not found:\n{JSON_PATH}")
        st.stop()

    meta     = d["meta"]
    overall  = d["overall"]
    be       = 1.0 / (1.0 + meta["rr"])
    variants = d["variants"]
    hours    = d["hours"]
    dows     = d["dows"]
    by_var   = d["by_variant"]

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("TTrades Fractal Model°")
    st.caption(
        f"{meta['table'].upper()} · HTF {meta['htf_min']}min · {meta['rr']}:1 RR · "
        f"min_risk {meta['min_risk']}pts · "
        f"{overall['n']:,} resolved trades · {meta['total_trades']:,} zone touches"
    )

    # ── KPI tiles ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Resolved Trades",  f"{overall['n']:,}")
    k2.metric("Win Rate",         f"{overall['wr']:.1%}")
    k3.metric("EV / trade",       f"{overall['ev']:+.3f}R")
    k4.metric("Resolution Rate",  f"{overall['n']/meta['total_trades']:.1%}")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_ov, tab_time, tab_hm, tab_combo, tab_qtr, tab_trades = st.tabs([
        "Overview", "Time Analysis", "Heatmaps", "Best Combos", "Quarter Detail", "Trades"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — OVERVIEW
    # ══════════════════════════════════════════════════════════════════════════
    with tab_ov:
        # Variant table + Direction split
        col_var, col_dir = st.columns([3, 2])

        with col_var:
            st.subheader("By Variant")
            var_rows = []
            for v in variants:
                s = by_var.get(v, {})
                if not s:
                    continue
                var_rows.append({
                    "Variant":  v,
                    "Dir":      "BULL" if v.endswith("BULL") else "BEAR",
                    "N":        s["n"],
                    "Win Rate": f"{s['wr']:.1%}",
                    "EV (R)":   f"{s['ev']:+.3f}",
                    "PF":       f"{s['pf']:.3f}",
                })
            if var_rows:
                st.dataframe(pd.DataFrame(var_rows), use_container_width=True, hide_index=True)

        with col_dir:
            st.subheader("Direction Split")
            for direction, suffix in [("LONG (BULL)", "BULL"), ("SHORT (BEAR)", "BEAR")]:
                tn = tw = 0
                for v in variants:
                    if v.endswith(suffix):
                        s = by_var.get(v, {})
                        tn += s.get("n", 0)
                        tw += s.get("wins", 0)
                if not tn:
                    continue
                wr = tw / tn
                ev = wr * meta["rr"] - (1 - wr)
                st.markdown(f"**{direction}**")
                st.metric("", f"{wr:.1%} WR", f"{ev:+.3f}R EV · N={tn:,}")
                st.progress(wr)

        st.divider()

        # DOW table
        st.subheader("By Day of Week")
        dow_rows = [
            {"Day": dn,
             "N":        d["by_dow"][dn]["n"],
             "Win Rate": f"{d['by_dow'][dn]['wr']:.1%}",
             "EV (R)":   f"{d['by_dow'][dn]['ev']:+.3f}",
             "PF":       f"{d['by_dow'][dn]['pf']:.3f}"}
            for dn in dows if dn in d["by_dow"]
        ]
        col_d1, col_d2 = st.columns([1, 2])
        with col_d1:
            st.dataframe(pd.DataFrame(dow_rows), use_container_width=True, hide_index=True)
        with col_d2:
            ddf = pd.DataFrame(dow_rows)
            ddf["_wr"] = [d["by_dow"][dn]["wr"] for dn in dows if dn in d["by_dow"]]
            fig_dow = px.bar(ddf, x="Day", y="_wr",
                             labels={"Day": "Day", "_wr": "Win Rate"},
                             color="_wr",
                             color_continuous_scale=["#d62728","#aec7e8","#2ca02c"],
                             range_color=[be - 0.10, be + 0.10],
                             text=ddf["Win Rate"])
            fig_dow.add_hline(y=be, line_dash="dash", line_color="gray")
            fig_dow.update_layout(height=260, coloraxis_showscale=False, **_LAYOUT)
            fig_dow.update_traces(textposition="outside")
            st.plotly_chart(fig_dow, use_container_width=True, key="ttfm_ov_dow_bar")

        st.divider()

        # Variant × DOW table
        st.subheader("Variant × Day of Week")
        vdow = d.get("variant_dow", {})
        if vdow:
            vd_rows = []
            for v in variants:
                row = {"Variant": v}
                for dn in dows:
                    s = vdow.get(v, {}).get(dn, {})
                    row[dn] = f"{s['wr']:.1%}" if s and s.get("n", 0) >= 5 else "—"
                vd_rows.append(row)
            st.dataframe(pd.DataFrame(vd_rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — TIME ANALYSIS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_time:
        st.subheader("Win Rate by Hour (ET)")
        hr_rows = [
            {"Hour": int(h), "WR": d["by_hour"][h]["wr"],
             "N": d["by_hour"][h]["n"],
             "EV": d["by_hour"][h]["ev"]}
            for h in hours if h in d["by_hour"] and d["by_hour"][h]["n"] >= 5
        ]
        if hr_rows:
            hr_df = pd.DataFrame(hr_rows)
            col_hrc, col_hrt = st.columns([2, 1])
            with col_hrc:
                st.plotly_chart(
                    _bar_fig(
                        hr_df["Hour"], hr_df["WR"],
                        {"x": "Hour (ET)", "y": "Win Rate"},
                        be, text=hr_df["WR"].map("{:.1%}".format)
                    ),
                    use_container_width=True, key="ttfm_time_hr_bar"
                )
            with col_hrt:
                hr_disp = hr_df.copy()
                hr_disp["WR"]  = hr_disp["WR"].map("{:.1%}".format)
                hr_disp["EV"]  = hr_disp["EV"].map("{:+.3f}".format)
                st.dataframe(hr_disp[["Hour","N","WR","EV"]],
                             use_container_width=True, hide_index=True)

        st.divider()

        # Variant × Hour table
        st.subheader("Variant × Hour Win Rate")
        vh = d.get("variant_hour", {})
        if vh:
            vh_rows = []
            for v in variants:
                row = {"Variant": v}
                for h in hours:
                    s = vh.get(v, {}).get(h, {})
                    row[f"{h}:00"] = f"{s['wr']:.1%}" if s and s.get("n", 0) >= 5 else "—"
                vh_rows.append(row)
            st.dataframe(pd.DataFrame(vh_rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — HEATMAPS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_hm:
        st.subheader("Win Rate — Day × Hour")
        hour_cols = [f"{h}:00" for h in hours]
        z_wr = []
        for dn in dows:
            row = []
            for h in hours:
                wr_v = d["heatmap_wr"].get(dn, {}).get(h)
                n_v  = d["heatmap_n"].get(dn, {}).get(h, 0)
                row.append(round(wr_v, 4) if (wr_v is not None and n_v >= 5) else None)
            z_wr.append(row)
        st.plotly_chart(
            _hm_fig(z_wr, hour_cols, list(dows), be, title="Win Rate Heatmap", height=280),
            use_container_width=True, key="ttfm_hm_wr"
        )

        st.divider()

        st.subheader("EV — Day × Hour")
        z_ev = []
        for dn in dows:
            row = []
            for h in hours:
                ev_v = d["heatmap_ev"].get(dn, {}).get(h)
                n_v  = d["heatmap_n"].get(dn, {}).get(h, 0)
                row.append(round(ev_v, 4) if (ev_v is not None and n_v >= 5) else None)
            z_ev.append(row)
        text_ev = [[f"{v:+.3f}R" if v is not None else "—" for v in row] for row in z_ev]
        fig_ev = go.Figure(go.Heatmap(
            z=z_ev, x=hour_cols, y=list(dows),
            text=text_ev, texttemplate="%{text}",
            colorscale=[[0,"#7f1d1d"],[0.5,"#374151"],[1,"#065f46"]],
            zmid=0, showscale=True,
            colorbar=dict(title="EV (R)"),
        ))
        fig_ev.update_layout(height=280, xaxis=dict(side="top"),
                             title="EV Heatmap", **_LAYOUT)
        st.plotly_chart(fig_ev, use_container_width=True, key="ttfm_hm_ev")

        st.divider()

        # Hour × Quarter heatmap
        st.subheader("Hour × Quarter Win Rate")
        hq = d.get("hour_quarter", {})
        qs = d.get("quarters", ["1","2","3","4"])
        qnames = d.get("quarter_names", {q: f"Q{q}" for q in qs})
        if hq:
            q_labels = [qnames.get(q, f"Q{q}") for q in qs]
            z_hq = []
            y_hq = []
            for h in hours:
                row = []
                y_hq.append(f"{h}:00")
                for q in qs:
                    s = hq.get(h, {}).get(q, {})
                    row.append(s.get("wr") if s and s.get("n", 0) >= 5 else None)
                z_hq.append(row)
            st.plotly_chart(
                _hm_fig(z_hq, q_labels, y_hq, be, title="Hour × Quarter WR", height=340),
                use_container_width=True, key="ttfm_hm_hr_qtr"
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — BEST COMBOS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_combo:
        st.subheader("Best Variant × Hour Combinations  (N ≥ 10, sorted by WR)")
        vh = d.get("variant_hour", {})
        combo_rows = []
        for v in variants:
            for h in hours:
                s = vh.get(v, {}).get(h, {})
                if s and s.get("n", 0) >= 10:
                    combo_rows.append({
                        "Variant":  v,
                        "Dir":      "BULL" if v.endswith("BULL") else "BEAR",
                        "Hour":     f"{h}:00",
                        "N":        s["n"],
                        "Win Rate": s["wr"],
                        "EV (R)":   s["ev"],
                        "PF":       s["pf"],
                    })
        if combo_rows:
            cdf = (pd.DataFrame(combo_rows)
                   .sort_values("Win Rate", ascending=False)
                   .reset_index(drop=True))
            cdf["Win Rate"] = cdf["Win Rate"].map("{:.1%}".format)
            cdf["EV (R)"]   = cdf["EV (R)"].map("{:+.3f}".format)
            cdf["PF"]       = cdf["PF"].map("{:.3f}".format)
            st.dataframe(cdf, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 5 — QUARTER DETAIL
    # ══════════════════════════════════════════════════════════════════════════
    with tab_qtr:
        # Quarter summary bars
        st.subheader("Quarter of Hour Breakdown")
        bq = d.get("by_quarter", {})
        if bq:
            q_labels_list = [qnames.get(k.replace("Q","").strip(), k) for k in bq.keys()]
            q_wrs  = [v["wr"] for v in bq.values()]
            q_rows = [{"Quarter": qnames.get(k.replace("Q","").strip(), k),
                       "N":        v["n"],
                       "Win Rate": f"{v['wr']:.1%}",
                       "EV (R)":   f"{v['ev']:+.3f}",
                       "PF":       f"{v['pf']:.3f}"}
                      for k, v in bq.items()]
            col_qt, col_qb = st.columns([1, 2])
            with col_qt:
                st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)
            with col_qb:
                st.plotly_chart(
                    _bar_fig(
                        [r["Quarter"] for r in q_rows], q_wrs,
                        {"x": "Quarter", "y": "Win Rate"}, be,
                        text=[r["Win Rate"] for r in q_rows]
                    ),
                    use_container_width=True, key="ttfm_qtr_bar"
                )

        st.divider()

        # Variant × Quarter table
        st.subheader("Variant × Quarter")
        vq = d.get("variant_quarter", {})
        if vq:
            vq_rows = []
            for v in variants:
                row = {"Variant": v}
                for q in qs:
                    s = vq.get(v, {}).get(q, {})
                    row[qnames.get(q, f"Q{q}")] = (
                        f"{s['wr']:.1%} (N={s['n']})" if s and s.get("n", 0) >= 5 else "—"
                    )
                vq_rows.append(row)
            st.dataframe(pd.DataFrame(vq_rows), use_container_width=True, hide_index=True)

        st.divider()

        # DOW × Quarter table
        st.subheader("Day of Week × Quarter")
        dq = d.get("dow_quarter", {})
        if dq:
            dq_rows = []
            for dn in dows:
                row = {"Day": dn}
                for q in qs:
                    s = dq.get(dn, {}).get(q, {})
                    row[qnames.get(q, f"Q{q}")] = (
                        f"{s['wr']:.1%} (N={s['n']})" if s and s.get("n", 0) >= 5 else "—"
                    )
                dq_rows.append(row)
            st.dataframe(pd.DataFrame(dq_rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 6 — TRADES
    # ══════════════════════════════════════════════════════════════════════════
    with tab_trades:
        st.subheader("Recent Trades by Variant")
        recent = d.get("recent_trades", {})
        if recent:
            sel = st.selectbox("Variant", options=variants, key="ttfm_variant_sel")
            tv  = recent.get(sel, [])
            if tv:
                rt_df = pd.DataFrame(tv)
                cols  = [c for c in
                         ["date","dow_name","hr","quarter","direction",
                          "entry","stop","target","risk_pts","outcome"]
                         if c in rt_df.columns]
                rt_df = rt_df[cols].copy()
                rt_df.rename(columns={
                    "date":"Date","dow_name":"Day","hr":"Hour","quarter":"Q",
                    "direction":"Dir","entry":"Entry","stop":"Stop",
                    "target":"Target","risk_pts":"Risk pts","outcome":"Outcome",
                }, inplace=True)
                st.dataframe(
                    rt_df, use_container_width=True, hide_index=True,
                    column_config={
                        "Entry":    st.column_config.NumberColumn(format="%.2f"),
                        "Stop":     st.column_config.NumberColumn(format="%.2f"),
                        "Target":   st.column_config.NumberColumn(format="%.2f"),
                        "Risk pts": st.column_config.NumberColumn(format="%.1f"),
                    },
                    height=500,
                )
            else:
                st.info(f"No recent trades stored for {sel}.")
