"""
Streamlit dashboard for the multi-agent code review system.

Reads telemetry emitted by `metrics.recorder` (runs/events.jsonl) and renders:

  * Overview KPIs with sparklines (PRs reviewed, findings, throughput, error rate)
  * PRs reviewed table (sortable, filterable)
  * Agent interactions (Sankey of pipeline flow + per-agent timing/findings)
  * LLM telemetry (calls per backend, token totals, retry rate)
  * Watcher cadence (poll history, errors, backoff)

Run:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import json
from collections import Counter
from html import escape
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# --- aesthetic config: dark theme + purple accent ----------------------

ACCENT = "#A78BFA"
ACCENT2 = "#60A5FA"
BG = "#0B0E14"
PANEL = "#141821"
TEXT = "#E5E7EB"
MUTED = "#9CA3AF"
GRID = "#1F2937"

_dark = pio.templates["plotly_dark"]
_dark.layout.paper_bgcolor = BG
_dark.layout.plot_bgcolor = BG
_dark.layout.font.color = TEXT
_dark.layout.xaxis.gridcolor = GRID
_dark.layout.yaxis.gridcolor = GRID
_dark.layout.colorway = [
    "#A78BFA", "#34D399", "#F472B6", "#60A5FA", "#FBBF24", "#F87171", "#22D3EE", "#C084FC",
]
pio.templates.default = "plotly_dark"

# --- data load ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVENTS_PATH = PROJECT_ROOT / "runs" / "events.jsonl"

AGENT_ORDER = [
    "orchestrate",
    "security",
    "bug",
    "style",
    "triage",
    "human_review",
    "patch",
    "tests",
]


@st.cache_data(ttl=10)
def load_events(path_str: str) -> dict[str, pd.DataFrame]:
    """Load JSONL events from disk and split by `type`."""
    path = Path(path_str)
    empty = {k: _empty() for k in ("pr_review", "agent", "llm_call", "poll_cycle")}
    if not path.exists():
        return empty

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not rows:
        return empty

    df = pd.DataFrame(rows)
    if "timestamp_utc" in df.columns:
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)

    out: dict[str, pd.DataFrame] = {}
    for kind in empty:
        out[kind] = df[df["type"] == kind].copy() if "type" in df.columns else _empty()
    return out


def _empty() -> pd.DataFrame:
    return pd.DataFrame()


# --- sparkline + KPI card helpers --------------------------------------


def _svg_sparkline(
    values: Iterable[float],
    color: str = ACCENT,
    width: int = 180,
    height: int = 38,
    grad_id: str = "g",
) -> str:
    vals = [float(v) for v in values if pd.notna(v)]
    if len(vals) < 2:
        # Flat baseline.
        y = height - 6
        return (
            f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
            f'style="width:100%;height:{height}px;">'
            f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" stroke="{color}" '
            f'stroke-opacity="0.55" stroke-width="1.5"/></svg>'
        )

    vmin, vmax = min(vals), max(vals)
    span = vmax - vmin or 1.0
    last = len(vals) - 1
    pts = []
    for i, v in enumerate(vals):
        x = i * width / last
        y = (height - 4) - (v - vmin) / span * (height - 8)
        pts.append((x, y))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    fill = poly + f" {width},{height} 0,{height}"
    lx, ly = pts[-1]
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'style="width:100%;height:{height}px;">'
        f'<defs><linearGradient id="{grad_id}" x1="0" x2="0" y1="0" y2="1">'
        f'<stop offset="0%" stop-color="{color}" stop-opacity="0.35"/>'
        f'<stop offset="100%" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>'
        f'<polygon points="{fill}" fill="url(#{grad_id})"/>'
        f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="1.6"/>'
        f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.5" fill="{color}"/></svg>'
    )


def kpi_card(
    label: str,
    value: str,
    spark_values: Iterable[float] | None = None,
    color: str = ACCENT,
    grad_id: str = "g",
) -> str:
    spark_html = (
        _svg_sparkline(spark_values, color=color, grad_id=grad_id)
        if spark_values is not None
        else ""
    )
    return f"""
        <div class="kpi">
          <div class="kpi-inner">
            <div class="kpi-label">{escape(label)}</div>
            <div class="kpi-value">{escape(value)}</div>
            <div class="kpi-spark">{spark_html}</div>
          </div>
        </div>
    """


# --- page setup ---------------------------------------------------------

st.set_page_config(
    page_title="Multi-Agent Code Review — Dashboard",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      :root {
        --accent: #A78BFA;
        --accent-2: #60A5FA;
        --bg: #0B0E14;
        --panel: #141821;
        --panel-2: #0F1320;
        --border: #1F2937;
        --muted: #9CA3AF;
        --text: #E5E7EB;
      }

      .stApp { background: var(--bg); }
      .block-container { padding-top: 1.5rem; padding-bottom: 4rem; max-width: 1400px; }

      /* ---------- sidebar ---------- */
      [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0E1220 0%, #0B0E14 100%) !important;
        border-right: 1px solid var(--border);
      }
      [data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }

      .brand {
        display: flex; align-items: center; gap: 12px;
        padding: 6px 4px 12px; margin-bottom: 6px;
        border-bottom: 1px solid var(--border);
      }
      .brand-icon {
        width: 38px; height: 38px; border-radius: 10px;
        background: linear-gradient(135deg, #6D28D9 0%, #A78BFA 100%);
        display: flex; align-items: center; justify-content: center;
        font-size: 18px;
        box-shadow: 0 6px 16px rgba(167,139,250,0.30);
      }
      .brand-text .name { color: #F3F4F6; font-weight: 700; font-size: 0.95rem; line-height: 1.1; }
      .brand-text .build { color: var(--muted); font-size: 0.72rem; letter-spacing: 0.04em; text-transform: uppercase; margin-top: 2px; }

      .nav-section {
        color: var(--muted); font-size: 0.7rem; letter-spacing: 0.10em;
        text-transform: uppercase; padding: 14px 4px 6px;
      }

      /* Streamlit radio → vertical icon menu */
      [data-testid="stSidebar"] [role="radiogroup"] { gap: 4px !important; }
      [data-testid="stSidebar"] [role="radiogroup"] > label {
        background: transparent !important;
        border: 1px solid transparent !important;
        border-radius: 10px;
        padding: 8px 10px !important;
        margin: 0 !important;
        color: var(--muted) !important;
        transition: background 120ms, color 120ms, border-color 120ms;
      }
      [data-testid="stSidebar"] [role="radiogroup"] > label:hover {
        background: rgba(167,139,250,0.06) !important;
        color: var(--text) !important;
      }
      [data-testid="stSidebar"] [role="radiogroup"] > label[data-checked="true"],
      [data-testid="stSidebar"] [role="radiogroup"] > label:has(input:checked) {
        background: linear-gradient(135deg, rgba(109,40,217,0.30), rgba(167,139,250,0.10)) !important;
        border-color: rgba(167,139,250,0.35) !important;
        color: #F3F4F6 !important;
      }
      [data-testid="stSidebar"] [role="radiogroup"] [data-baseweb="radio"] > div:first-child { display: none; }
      [data-testid="stSidebar"] [role="radiogroup"] label p {
        font-size: 0.92rem !important; font-weight: 500 !important; margin: 0 !important;
      }

      /* ---------- hero ---------- */
      .hero {
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        align-items: center;
        column-gap: 16px;
        padding: 18px 24px;
        margin-bottom: 20px;
        background:
          radial-gradient(80% 120% at 100% 0%, rgba(96,165,250,0.10), transparent 60%),
          linear-gradient(135deg, rgba(167,139,250,0.10), rgba(96,165,250,0.04));
        border: 1px solid var(--border);
        border-radius: 14px;
      }
      .hero-icon {
        width: 44px; height: 44px; border-radius: 12px;
        background: linear-gradient(135deg, #6D28D9 0%, #A78BFA 100%);
        display: flex; align-items: center; justify-content: center; font-size: 22px;
        box-shadow: 0 8px 22px rgba(167,139,250,0.35);
      }
      .hero-text { min-width: 0; }
      .hero-title {
        font-size: 1.35rem; font-weight: 700; margin: 0; line-height: 1.2;
        color: #F3F4F6; letter-spacing: -0.01em;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .hero-sub {
        color: var(--muted); font-size: 0.85rem; margin-top: 4px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .hero-pill {
        padding: 5px 11px; border-radius: 999px;
        background: rgba(52,211,153,0.10); color: #34D399;
        font-size: 0.78rem; border: 1px solid rgba(52,211,153,0.30);
        white-space: nowrap;
      }
      .hero-pill .dot {
        display: inline-block; width: 7px; height: 7px; border-radius: 50%;
        background: #34D399; margin-right: 6px; vertical-align: middle;
        animation: pulse 1.6s ease-in-out infinite;
      }
      @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }

      /* ---------- KPI cards (gradient border + sparkline) ---------- */
      .kpi {
        position: relative;
        border-radius: 14px;
        padding: 1px;
        background: linear-gradient(135deg, rgba(167,139,250,0.55), rgba(96,165,250,0.18) 55%, rgba(255,255,255,0.04) 100%);
      }
      .kpi:hover { background: linear-gradient(135deg, rgba(167,139,250,0.85), rgba(96,165,250,0.30) 55%, rgba(255,255,255,0.05) 100%); }
      .kpi-inner {
        background: var(--panel);
        border-radius: 13px;
        padding: 14px 16px 10px;
      }
      .kpi-label { color: var(--muted); font-size: 0.78rem; letter-spacing: 0.02em; }
      .kpi-value { color: #F3F4F6; font-size: 1.55rem; font-weight: 700; margin-top: 2px; }
      .kpi-spark { margin-top: 8px; }

      /* Section heading bar */
      .section { display: flex; align-items: center; gap: 8px; margin: 22px 0 10px; }
      .section h3 { color: #F3F4F6; margin: 0; font-size: 1.02rem; font-weight: 600; }
      .section .pip { width: 4px; height: 16px; border-radius: 4px; background: linear-gradient(180deg, var(--accent), var(--accent-2)); }
      .section .hint { color: var(--muted); font-size: 0.82rem; }

      /* Inline code */
      code { color: #C4B5FD; background: rgba(167,139,250,0.10); padding: 1px 6px; border-radius: 4px; }

      /* Tables */
      [data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid var(--border); }

      /* Streamlit's default st.metric (used in nested LLM/Watcher pages) */
      div[data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 12px 14px;
      }
      div[data-testid="stMetricLabel"] p { color: var(--muted); font-size: 0.78rem; }
      div[data-testid="stMetricValue"] { color: #F3F4F6; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- sidebar ----------
NAV_ITEMS = [
    ("Overview", "📊"),
    ("PRs reviewed", "📥"),
    ("Agent interactions", "🧠"),
    ("LLM telemetry", "💬"),
    ("Watcher", "👀"),
]

with st.sidebar:
    st.markdown(
        """
        <div class="brand">
          <div class="brand-icon">🤖</div>
          <div class="brand-text">
            <div class="name">Code Review Agents</div>
            <div class="build">v0.2 · pilot</div>
          </div>
        </div>
        <div class="nav-section">Navigation</div>
        """,
        unsafe_allow_html=True,
    )
    page = st.radio(
        "Section",
        [f"{icon}  {name}" for name, icon in NAV_ITEMS],
        label_visibility="collapsed",
        key="nav",
    )
    # Strip emoji+spaces back to the canonical name.
    page_name = page.split("  ", 1)[1] if "  " in page else page

    st.markdown('<div class="nav-section">Source</div>', unsafe_allow_html=True)
    st.markdown(
        f"<div style='color:var(--muted);font-size:0.78rem;line-height:1.4;'>"
        f"<code>{EVENTS_PATH.relative_to(PROJECT_ROOT)}</code><br>auto-refresh 10s</div>",
        unsafe_allow_html=True,
    )

# ---------- hero ----------
events = load_events(str(EVENTS_PATH))
pr_df = events["pr_review"]
agent_df = events["agent"]
llm_df = events["llm_call"]
poll_df = events["poll_cycle"]

has_data = not (pr_df.empty and agent_df.empty and llm_df.empty and poll_df.empty)

st.markdown(
    f"""
    <div class="hero">
      <div class="hero-icon">🤖</div>
      <div class="hero-text">
        <div class="hero-title">Multi-Agent Code Review</div>
        <div class="hero-sub">{page_name} · live telemetry from <code>runs/events.jsonl</code></div>
      </div>
      <div class="hero-pill"><span class="dot"></span>{'live' if has_data else 'idle'}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not has_data:
    st.warning(
        "No telemetry yet. Run a review (e.g. `python review_pr.py <PR URL>` or "
        "`python watch_prs.py <repo>`) and refresh."
    )
    st.stop()


def section_heading(title: str, hint: str = "") -> None:
    st.markdown(
        f'<div class="section"><div class="pip"></div><h3>{escape(title)}</h3>'
        + (f'<div class="hint">· {escape(hint)}</div>' if hint else "")
        + "</div>",
        unsafe_allow_html=True,
    )


# =======================================================================
#  PAGE: Overview
# =======================================================================
def render_overview() -> None:
    # ---- compute KPI values + sparklines ----
    pr_sorted = pr_df.sort_values("timestamp_utc") if not pr_df.empty else pr_df
    agent_sorted = (
        agent_df.sort_values("timestamp_utc") if not agent_df.empty else agent_df
    )

    prs_reviewed = len(pr_df)
    total_findings = int(pr_df["total_findings"].sum()) if not pr_df.empty else 0
    avg_duration = float(pr_df["duration_sec"].mean()) if not pr_df.empty else 0.0

    if not pr_df.empty:
        last24 = pr_df[
            pr_df["timestamp_utc"]
            >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=24)
        ]
        pr_per_hour_24 = len(last24) / 24.0
    else:
        pr_per_hour_24 = 0.0

    if not agent_df.empty:
        agent_error_rate = (agent_df["error"].notna().sum() / len(agent_df)) * 100
    else:
        agent_error_rate = 0.0

    # Sparkline series.
    spark_prs = (
        list(range(1, len(pr_sorted) + 1)) if not pr_sorted.empty else []
    )  # cumulative count
    spark_findings = (
        pr_sorted["total_findings"].cumsum().tolist() if not pr_sorted.empty else []
    )
    spark_duration = (
        pr_sorted["duration_sec"].tolist() if not pr_sorted.empty else []
    )
    if not pr_df.empty:
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=24)
        recent = pr_df[pr_df["timestamp_utc"] >= cutoff]
        hourly = (
            recent.set_index("timestamp_utc")
            .sort_index()
            .resample("1h")
            .size()
            .tolist()
        )
        spark_throughput = hourly or [0]
    else:
        spark_throughput = []
    if not agent_sorted.empty:
        # Rolling error rate over last 20 events.
        is_err = agent_sorted["error"].notna().astype(int)
        rolling = is_err.rolling(window=10, min_periods=1).mean() * 100
        spark_errors = rolling.tolist()
    else:
        spark_errors = []

    cards = [
        ("PRs reviewed", f"{prs_reviewed}", spark_prs, "#A78BFA"),
        ("Total findings", f"{total_findings}", spark_findings, "#34D399"),
        ("Avg PR review", f"{avg_duration:.1f}s", spark_duration, "#60A5FA"),
        ("PRs / hr (24h)", f"{pr_per_hour_24:.2f}", spark_throughput, "#F472B6"),
        ("Agent error rate", f"{agent_error_rate:.1f}%", spark_errors, "#F87171"),
    ]

    cols = st.columns(5, gap="medium")
    for col, (label, value, series, color) in zip(cols, cards):
        col.markdown(
            kpi_card(label, value, series, color=color, grad_id=f"g_{label.replace(' ', '_')}"),
            unsafe_allow_html=True,
        )

    # ---- recent activity feed ----
    section_heading("Recent activity", "last 8 PR reviews")
    if pr_df.empty:
        st.info("No PR reviews yet.")
    else:
        recent = pr_df.sort_values("timestamp_utc", ascending=False).head(8)
        rows: list[str] = []
        cell = "padding:10px 12px;"
        chip_review = (
            '<span title="Triage flagged Critical/High security findings — '
            'human review recommended" '
            'style="display:inline-block;padding:2px 8px;border-radius:999px;'
            'background:rgba(251,191,36,0.16);color:#FBBF24;'
            'font-size:0.72rem;font-weight:600;letter-spacing:0.04em;'
            'margin-left:8px;">human review</span>'
        )
        for _, r in recent.iterrows():
            ts = (
                r["timestamp_utc"].strftime("%Y-%m-%d %H:%M")
                if pd.notna(r["timestamp_utc"])
                else ""
            )
            chip = chip_review if r.get("needs_human_review") else ""
            rows.append(
                f'<tr style="border-top:1px solid var(--border);">'
                f'<td style="{cell}color:var(--muted);font-family:ui-monospace,monospace;">{ts}</td>'
                f'<td style="{cell}"><code>{escape(r["owner"])}/{escape(r["repo"])}#{int(r["pr_number"])}</code>{chip}</td>'
                f'<td style="{cell}color:#F3F4F6;">{escape(str(r["title"])[:80])}</td>'
                f'<td style="{cell}color:var(--muted);">{int(r["files_reviewed"])}</td>'
                f'<td style="{cell}color:var(--muted);">{int(r["total_findings"])}</td>'
                f'<td style="{cell}color:var(--muted);">{float(r["duration_sec"]):.1f}s</td>'
                f"</tr>"
            )
        st.markdown(
            f"""
            <div style="border:1px solid var(--border);border-radius:12px;background:var(--panel);overflow:hidden;">
              <table style="width:100%;border-collapse:collapse;font-size:0.86rem;">
                <thead>
                  <tr style="background:var(--panel-2);color:var(--muted);text-align:left;">
                    <th style="{cell}font-weight:500;">Time</th>
                    <th style="{cell}font-weight:500;">PR</th>
                    <th style="{cell}font-weight:500;">Title</th>
                    <th style="{cell}font-weight:500;">Files</th>
                    <th style="{cell}font-weight:500;">Findings</th>
                    <th style="{cell}font-weight:500;">Duration</th>
                  </tr>
                </thead>
                <tbody>{''.join(rows)}</tbody>
              </table>
            </div>
            """,
            unsafe_allow_html=True,
        )


# =======================================================================
#  PAGE: PRs reviewed
# =======================================================================
def render_prs() -> None:
    if pr_df.empty:
        st.info("No PR reviews recorded yet.")
        return

    repos = sorted({f"{r}/{p}" for r, p in zip(pr_df["owner"], pr_df["repo"])})
    repo_filter = st.multiselect("Filter by repo", repos, default=repos)
    view = pr_df[(pr_df["owner"] + "/" + pr_df["repo"]).isin(repo_filter)].copy()
    view = view.sort_values("timestamp_utc", ascending=False)

    # Daily throughput.
    section_heading("Throughput", "PRs reviewed per day")
    daily = (
        view.set_index("timestamp_utc")
        .resample("1D")
        .size()
        .rename("PRs reviewed")
        .reset_index()
    )
    if not daily.empty:
        fig = px.bar(daily, x="timestamp_utc", y="PRs reviewed")
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=240)
        fig.update_traces(marker_color=ACCENT)
        st.plotly_chart(fig, use_container_width=True)

    section_heading("All reviewed PRs")
    display_cols = [
        "timestamp_utc",
        "owner",
        "repo",
        "pr_number",
        "title",
        "author",
        "files_reviewed",
        "files_skipped",
        "total_findings",
        "needs_human_review",
        "duration_sec",
        "agent_proposal_status",
    ]
    present = [c for c in display_cols if c in view.columns]
    st.dataframe(view[present], use_container_width=True, hide_index=True)


# =======================================================================
#  PAGE: Agent interactions
# =======================================================================
def render_agents() -> None:
    if agent_df.empty:
        st.info("No agent events yet.")
        return

    section_heading("Pipeline flow (Sankey)", "agent-to-agent edges across all runs")

    edges: Counter[tuple[str, str]] = Counter()
    if {"run_id", "file_name"}.issubset(agent_df.columns):
        grouped = agent_df.sort_values("timestamp_utc").groupby(["run_id", "file_name"])
        for _, sub in grouped:
            seq = list(sub["agent_name"])
            for a, b in zip(seq, seq[1:]):
                edges[(a, b)] += 1

    if edges:
        nodes = list(dict.fromkeys([n for edge in edges for n in edge]))
        nodes_sorted = [n for n in AGENT_ORDER if n in nodes] + [
            n for n in nodes if n not in AGENT_ORDER
        ]
        idx = {n: i for i, n in enumerate(nodes_sorted)}
        sankey = go.Figure(
            go.Sankey(
                node=dict(
                    label=nodes_sorted,
                    pad=22,
                    thickness=18,
                    color=ACCENT,
                    line=dict(width=0),
                ),
                link=dict(
                    source=[idx[a] for (a, _) in edges],
                    target=[idx[b] for (_, b) in edges],
                    value=list(edges.values()),
                    color="rgba(167,139,250,0.32)",
                ),
            )
        )
        sankey.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(sankey, use_container_width=True)
    else:
        st.info("Need at least one full pipeline run to draw the Sankey.")

    col_a, col_b = st.columns(2, gap="medium")

    with col_a:
        section_heading("Per-agent duration", "seconds")
        box = px.box(
            agent_df,
            x="agent_name",
            y="duration_sec",
            category_orders={"agent_name": AGENT_ORDER},
            points="outliers",
        )
        box.update_layout(yaxis_title="", xaxis_title="", margin=dict(l=10, r=10, t=10, b=10), height=300)
        st.plotly_chart(box, use_container_width=True)

    with col_b:
        section_heading("Findings contributed", "by agent")
        findings_per_agent = (
            agent_df.groupby("agent_name")["findings_added"]
            .sum()
            .reindex(AGENT_ORDER, fill_value=0)
            .reset_index()
        )
        bar = px.bar(
            findings_per_agent,
            x="agent_name",
            y="findings_added",
            labels={"findings_added": "", "agent_name": ""},
        )
        bar.update_traces(marker_color=ACCENT)
        bar.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
        st.plotly_chart(bar, use_container_width=True)

    errs = agent_df[agent_df["error"].notna()]
    if not errs.empty:
        section_heading("Agent errors")
        st.dataframe(
            errs[["timestamp_utc", "agent_name", "file_name", "error"]],
            use_container_width=True,
            hide_index=True,
        )


# =======================================================================
#  PAGE: LLM telemetry
# =======================================================================
def render_llm() -> None:
    if llm_df.empty:
        st.info("No LLM calls recorded.")
        return

    total_calls = len(llm_df)
    success = llm_df[llm_df["error"].isna()]
    retry_rate = (
        ((llm_df["attempt"] > 1).sum() / total_calls * 100) if total_calls else 0.0
    )
    total_tokens = (
        int(llm_df["total_tokens"].dropna().sum()) if "total_tokens" in llm_df else 0
    )
    p95 = float(success["duration_sec"].quantile(0.95)) if not success.empty else 0.0

    sorted_calls = llm_df.sort_values("timestamp_utc")
    spark_calls = list(range(1, len(sorted_calls) + 1))
    spark_tokens = sorted_calls["total_tokens"].fillna(0).cumsum().tolist()
    spark_lat = sorted_calls["duration_sec"].tolist()

    cards = [
        ("LLM calls", f"{total_calls}", spark_calls, "#A78BFA"),
        ("Total tokens", f"{total_tokens:,}", spark_tokens, "#34D399"),
        ("Retry rate", f"{retry_rate:.1f}%", spark_lat, "#F87171"),
        ("p95 latency", f"{p95:.2f}s", spark_lat, "#60A5FA"),
    ]
    cols = st.columns(4, gap="medium")
    for col, (label, value, series, color) in zip(cols, cards):
        col.markdown(
            kpi_card(label, value, series, color=color, grad_id=f"l_{label.replace(' ', '_')}"),
            unsafe_allow_html=True,
        )

    col_l, col_r = st.columns(2, gap="medium")
    with col_l:
        section_heading("Calls by backend / model")
        bm = llm_df.groupby(["backend", "model"]).size().reset_index(name="calls")
        bar = px.bar(bm, x="model", y="calls", color="backend")
        bar.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280)
        st.plotly_chart(bar, use_container_width=True)

    with col_r:
        section_heading("Calls by agent")
        if "agent_name" in llm_df.columns:
            ag = (
                llm_df["agent_name"]
                .fillna("(uncaptured)")
                .value_counts()
                .reset_index()
            )
            ag.columns = ["agent_name", "calls"]
            bar = px.bar(ag, x="agent_name", y="calls")
            bar.update_traces(marker_color=ACCENT)
            bar.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=280)
            st.plotly_chart(bar, use_container_width=True)

    errs = llm_df[llm_df["error"].notna()]
    if not errs.empty:
        section_heading("LLM errors")
        err_counts = errs["error"].astype(str).value_counts().head(10).reset_index()
        err_counts.columns = ["error", "count"]
        st.dataframe(err_counts, use_container_width=True, hide_index=True)


# =======================================================================
#  PAGE: Watcher
# =======================================================================
def render_watcher() -> None:
    if poll_df.empty:
        st.info("No watcher activity. Run `python watch_prs.py <repo>` and refresh.")
        return

    view = poll_df.sort_values("timestamp_utc")

    spark_open = view["open_pr_count"].tolist()
    spark_reviewed = view["reviewed_count"].cumsum().tolist()
    spark_errors = view["error_count"].cumsum().tolist()

    cards = [
        ("Total polls", f"{len(view)}", list(range(1, len(view) + 1)), "#A78BFA"),
        (
            "Reviewed (watcher)",
            f"{int(view['reviewed_count'].sum())}",
            spark_reviewed,
            "#34D399",
        ),
        ("Errors", f"{int(view['error_count'].sum())}", spark_errors, "#F87171"),
        ("Avg open PRs", f"{view['open_pr_count'].mean():.1f}", spark_open, "#60A5FA"),
    ]
    cols = st.columns(4, gap="medium")
    for col, (label, value, series, color) in zip(cols, cards):
        col.markdown(
            kpi_card(label, value, series, color=color, grad_id=f"w_{label.replace(' ', '_')}"),
            unsafe_allow_html=True,
        )

    section_heading("Poll history", "open / new / reviewed / errors over time")
    ts_long = view.melt(
        id_vars=["timestamp_utc"],
        value_vars=["open_pr_count", "new_pr_count", "reviewed_count", "error_count"],
        var_name="metric",
        value_name="count",
    )
    line = px.line(ts_long, x="timestamp_utc", y="count", color="metric")
    line.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=320)
    st.plotly_chart(line, use_container_width=True)

    section_heading("Raw poll cycles")
    st.dataframe(view, use_container_width=True, hide_index=True)


# ---------- dispatch ----------
RENDERERS = {
    "Overview": render_overview,
    "PRs reviewed": render_prs,
    "Agent interactions": render_agents,
    "LLM telemetry": render_llm,
    "Watcher": render_watcher,
}
RENDERERS.get(page_name, render_overview)()
