"""Kalshi bot monitor dashboard.

Read-only Streamlit app showing live status of the v1 bot. Reads the
state files the bot already writes under data/live_trades/. Does not
modify anything; safe to run alongside the bot.

Launch:
    uv run streamlit run scripts/dashboard.py

Or use the helper:
    .\\scripts\\dashboard.ps1

Default port 8501. Opens at http://localhost:8501.

Auto-refresh every 30s via st.fragment + st_autorefresh.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# Page setup must be the first Streamlit call.
st.set_page_config(
    page_title="Kalshi Bot Monitor",
    page_icon="K",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------- Data paths ----------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "data" / "live_trades"
STATE_FILE = STATE_DIR / "state.json"
KILL_FILE = STATE_DIR / "kill_state.json"
HEARTBEAT_FILE = STATE_DIR / "heartbeat.txt"
PID_FILE = STATE_DIR / "bot.pid"
LIVE_LOG = STATE_DIR / "logs" / "live.log"
LAUNCHER_LOG = STATE_DIR / "logs" / "launcher.log"
SHADOW_LOG = STATE_DIR / "v5_filter_shadow_log.jsonl"
STOP_FILE = STATE_DIR / "STOP"


# ---------- Defensive readers ----------

def safe_read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def safe_read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def humanize_age(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def tail_lines(p: Path, n: int = 30) -> list[str]:
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []


def read_jsonl_tail(p: Path, n: int = 50) -> list[dict]:
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines[-n:]:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


# ---------- Status derivation ----------

@dataclass
class BotStatus:
    label: str
    color: str  # for status badge
    heartbeat: datetime | None
    pid: int | None
    stop_file_present: bool


def derive_status() -> BotStatus:
    hb_str = safe_read_text(HEARTBEAT_FILE).strip()
    hb = parse_iso(hb_str)
    pid: int | None = None
    try:
        pid_str = safe_read_text(PID_FILE).strip()
        if pid_str:
            pid = int(pid_str)
    except Exception:
        pid = None
    stop = STOP_FILE.exists()
    if stop:
        return BotStatus("STOPPING (STOP file present)", "orange", hb, pid, True)
    if hb is None:
        return BotStatus("UNKNOWN (no heartbeat file)", "gray", None, pid, False)
    age = (datetime.now(UTC) - hb.replace(tzinfo=UTC) if hb.tzinfo is None else datetime.now(UTC) - hb).total_seconds()
    if age < 20 * 60:
        return BotStatus("RUNNING", "green", hb, pid, False)
    if age < 60 * 60:
        return BotStatus("STALE (heartbeat > 20m)", "orange", hb, pid, False)
    return BotStatus("DOWN (heartbeat > 1h)", "red", hb, pid, False)


# ---------- Orders DataFrames ----------

def orders_df(bucket: dict) -> pd.DataFrame:
    """Convert one of state['intents'|'resting'|'filled'|'closed'] to a DF."""
    if not bucket:
        return pd.DataFrame()
    rows = []
    for v in bucket.values():
        rows.append(v)
    df = pd.DataFrame(rows)
    # Order the most useful columns first; ignore missing.
    preferred = [
        "ticker", "series_ticker", "side", "target_price_cents",
        "filled_price_cents", "contracts", "filled_count", "status",
        "expected_net_edge", "market_mid_at_placement",
        "placed_ts", "filled_ts", "cancelled_ts",
        "resolution_outcome", "realized_pnl_usd",
    ]
    cols = [c for c in preferred if c in df.columns]
    extras = [c for c in df.columns if c not in cols]
    return df[cols + extras]


def cumulative_pnl_df(state: dict) -> pd.DataFrame:
    """From closed orders with resolution timestamps and realized_pnl_usd,
    produce a chronological cumulative-P&L series."""
    closed = state.get("closed", {})
    rows = []
    for v in closed.values():
        ts = v.get("resolution_ts") or v.get("filled_ts") or v.get("placed_ts")
        pnl = v.get("realized_pnl_usd")
        if ts is None or pnl is None:
            continue
        parsed = parse_iso(ts)
        if parsed is None:
            continue
        rows.append({"ts": parsed, "pnl": float(pnl), "ticker": v.get("ticker", "")})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    df["cumulative_pnl"] = df["pnl"].cumsum()
    return df


# ---------- Page ----------

# Auto-refresh hook. st_autorefresh keys the rerun; bumping the meta_refresh
# count avoids stale browser caches. We set a 30s interval.
try:
    from streamlit_autorefresh import st_autorefresh  # type: ignore
    st_autorefresh(interval=30 * 1000, key="dashboard_refresh")
except Exception:
    # Streamlit's built-in auto-refresh fallback via meta tag. The user
    # can also press R in the browser or the rerun button in the menu.
    st.markdown(
        """<meta http-equiv="refresh" content="30">""",
        unsafe_allow_html=True,
    )


# Read once per render.
state = safe_read_json(STATE_FILE)
kill = safe_read_json(KILL_FILE)
status = derive_status()

# ---------- Header ----------

status_color = {
    "green": "#16a34a",
    "orange": "#ea580c",
    "red": "#dc2626",
    "gray": "#6b7280",
}.get(status.color, "#6b7280")

col_a, col_b = st.columns([3, 2])
with col_a:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="
            display:inline-block;
            width:14px;height:14px;border-radius:50%;
            background:{status_color};
            box-shadow:0 0 6px {status_color};
          "></span>
          <span style="font-size:1.6em;font-weight:600;">Kalshi Bot Monitor</span>
          <span style="font-size:1.1em;color:{status_color};font-weight:500;">
            {status.label}
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    sub_parts = []
    sub_parts.append(f"Heartbeat: **{humanize_age(status.heartbeat)}**")
    if status.pid is not None:
        sub_parts.append(f"PID: **{status.pid}**")
    if status.heartbeat is not None:
        sub_parts.append(f"({status.heartbeat.isoformat()})")
    st.caption(" | ".join(sub_parts))

with col_b:
    st.caption(f"Dashboard refreshed: {datetime.now(UTC).isoformat()} UTC")
    if st.button("Manual refresh"):
        st.rerun()


st.divider()


# ---------- Key metrics ----------

starting = float(state.get("starting_bankroll_usd") or 0.0)
realized_total = float(state.get("realized_pnl_total_usd") or 0.0)
current_bankroll = starting + realized_total
drawdown_pct = (
    (-realized_total / starting * 100.0) if (starting > 0 and realized_total < 0) else 0.0
)

# Open exposure: sum of (target_price_cents * contracts) for resting + filled.
def _exposure(bucket: dict) -> float:
    tot = 0.0
    for v in bucket.values():
        price = v.get("filled_price_cents") or v.get("target_price_cents") or 0
        contracts = v.get("contracts") or 0
        tot += float(price) / 100.0 * float(contracts)
    return tot

open_exposure = _exposure(state.get("resting", {})) + _exposure(state.get("filled", {}))

# Hit rate on resolved (closed with resolution_outcome).
closed_resolved = [
    v for v in state.get("closed", {}).values()
    if v.get("resolution_outcome") in (0, 1)
]
n_resolved = len(closed_resolved)
n_yes = sum(1 for v in closed_resolved if v.get("resolution_outcome") == 1)
hit_rate = (n_yes / n_resolved * 100.0) if n_resolved > 0 else None

# Kill trigger state.
tripped = bool(kill.get("tripped"))
trip_reason = kill.get("trip_reason") or "n/a"
trip_detail = kill.get("trip_detail") or ""

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(
    "Bankroll",
    f"${current_bankroll:.2f}",
    delta=f"{realized_total:+.2f}",
    delta_color=("normal" if realized_total >= 0 else "inverse"),
)
m2.metric(
    "Realized P&L",
    f"${realized_total:+.2f}",
    delta=f"{realized_total / starting * 100:+.1f}%" if starting > 0 else None,
)
m3.metric(
    "Drawdown",
    f"-{drawdown_pct:.1f}%" if drawdown_pct > 0 else "0.0%",
    help="From starting bankroll. KILL trigger fires at 20%.",
)
m4.metric("Open exposure", f"${open_exposure:.2f}", help="Sum of resting + filled position value.")
m5.metric(
    "Hit rate",
    f"{hit_rate:.1f}%" if hit_rate is not None else "n/a",
    help=f"{n_yes} YES / {n_resolved} resolved" if n_resolved else "No resolutions yet",
)


# ---------- Kill trigger panel ----------

with st.container():
    if tripped:
        st.error(
            f"**KILL TRIGGER TRIPPED** - {trip_reason} - {trip_detail}",
            icon=":material/warning:",
        )
    else:
        st.success(
            f"**Kill triggers armed.** Drawdown {drawdown_pct:.1f}% of 20% threshold.",
            icon=":material/check_circle:",
        )

    if kill:
        kc1, kc2, kc3, kc4 = st.columns(4)
        kc1.caption(f"Placement attempts: **{kill.get('placement_attempts_total', 0)}**")
        kc2.caption(f"Filled: **{kill.get('placement_filled_total', 0)}**")
        recent_outcomes = kill.get("recent_outcomes") or []
        rec_yes = sum(1 for o in recent_outcomes if o == 1)
        kc3.caption(f"Recent outcomes: **{rec_yes} YES / {len(recent_outcomes)}**")
        winners = kill.get("winner_pnl_per_contract") or []
        winner_count = sum(1 for x in winners if x > 0)
        kc4.caption(f"Winning contracts on file: **{winner_count}**")


st.divider()


# ---------- Orders ----------

st.subheader("Orders")

tab_resting, tab_filled, tab_closed, tab_intents = st.tabs(
    [
        f"Resting ({len(state.get('resting', {}))})",
        f"Filled ({len(state.get('filled', {}))})",
        f"Closed ({len(state.get('closed', {}))})",
        f"Intents ({len(state.get('intents', {}))})",
    ]
)

with tab_resting:
    df = orders_df(state.get("resting", {}))
    if df.empty:
        st.info("No resting orders.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab_filled:
    df = orders_df(state.get("filled", {}))
    if df.empty:
        st.info("No filled positions.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab_closed:
    df = orders_df(state.get("closed", {}))
    if df.empty:
        st.info("No closed orders.")
    else:
        # Useful sort: most recent first.
        sort_col = (
            "resolution_ts" if "resolution_ts" in df.columns
            else "cancelled_ts" if "cancelled_ts" in df.columns
            else "placed_ts"
        )
        df = df.sort_values(sort_col, ascending=False, na_position="last")
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab_intents:
    df = orders_df(state.get("intents", {}))
    if df.empty:
        st.info("No pending intents.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


st.divider()


# ---------- P&L chart ----------

st.subheader("Performance")

pnl_df = cumulative_pnl_df(state)
if pnl_df.empty:
    st.info("No realized P&L yet (no closed orders with resolution).")
else:
    st.line_chart(
        pnl_df.set_index("ts")["cumulative_pnl"],
        height=240,
        y_label="Cumulative realized P&L (USD)",
    )
    c1, c2 = st.columns(2)
    c1.caption(
        f"**{len(pnl_df)}** resolved closed orders | "
        f"mean per trade: **${pnl_df['pnl'].mean():+.3f}** | "
        f"max win: **${pnl_df['pnl'].max():+.2f}** | "
        f"max loss: **${pnl_df['pnl'].min():+.2f}**"
    )


st.divider()


# ---------- v5 filter activity ----------

st.subheader("v5 Track A filter activity")

shadow = read_jsonl_tail(SHADOW_LOG, n=200)
if not shadow:
    st.info(
        "No filter decisions logged yet. Set SHADOW_MODE_ENABLED=true "
        "in run_live_bot.ps1 and restart the bot to start logging."
    )
else:
    fdf = pd.DataFrame(shadow)
    # Show counts since midnight UTC and overall.
    now = datetime.now(UTC)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    fdf["_ts_parsed"] = fdf["timestamp"].apply(parse_iso)
    today = fdf[fdf["_ts_parsed"] >= midnight]

    skip_today = int((today["should_trade"] == False).sum()) if not today.empty else 0
    pass_today = int((today["should_trade"] == True).sum()) if not today.empty else 0
    skip_total = int((fdf["should_trade"] == False).sum())
    pass_total = int((fdf["should_trade"] == True).sum())

    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Skipped today", skip_today)
    f2.metric("Passed today", pass_today)
    f3.metric("Skipped total", skip_total)
    f4.metric("Passed total", pass_total)

    # Most recent 20 decisions, columns curated.
    show_cols = [
        "timestamp", "ticker", "should_trade", "reason",
        "kalshi_price", "poly_mid", "sportsbook_implied",
        "confidence", "fetch_status",
    ]
    show_cols = [c for c in show_cols if c in fdf.columns]
    recent = fdf.sort_values("_ts_parsed", ascending=False, na_position="last").head(20)[show_cols]
    st.dataframe(recent, use_container_width=True, hide_index=True)


st.divider()


# ---------- Live log tail ----------

st.subheader("Live log (last 40 lines)")

log_lines = tail_lines(LIVE_LOG, n=40)
if not log_lines:
    st.info("No live.log entries yet.")
else:
    # Render as a code block for monospace + scroll.
    st.code("\n".join(log_lines), language="text")

with st.expander("Launcher log (last 30 lines)"):
    launcher_lines = tail_lines(LAUNCHER_LOG, n=30)
    if launcher_lines:
        st.code("\n".join(launcher_lines), language="text")
    else:
        st.caption("No launcher.log entries yet.")


# ---------- Footer ----------

st.caption(
    f"Sources: {STATE_FILE.name}, {KILL_FILE.name}, {HEARTBEAT_FILE.name}, "
    f"{LIVE_LOG.name}, {SHADOW_LOG.name}. Read-only; never writes."
)
