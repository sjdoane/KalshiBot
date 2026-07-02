"""v25 shared machinery: as-of data access, the frozen ECM pass-through model, empirical
error distributions, and fire evaluation. Implements research/v25/02-methodology-lock.md
sections 2-5 EXACTLY; every constant here is a lock constant.

Outcome-blind by construction: nothing in this module reads the Kalshi `result` field.
The post-lock backtest joins results; the pre-lock 0b audit does not.
"""
from __future__ import annotations

import bisect
import json
import math
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

DATA = os.path.join("data", "v25")
ET = ZoneInfo("America/New_York")

# ---- lock constants (section references to 02-methodology-lock.md) ----
W_LAG_DAYS = None           # sec 2: None = EIA weekly-release calendar rule (primary);
                            # an int = flat calendar-day lag (non-binding sensitivity)
W_LAG_SENS = 3              # non-binding flat-lag sensitivity
MARGIN_WIN = 180            # sec 3: rolling median window
MARGIN_MIN_PAIRS = 90       # sec 2 (E2)
MIN_FIT_ROWS = 120          # sec 3
MIN_ERRS_H1 = 40            # sec 3
MIN_ERRS_H2 = 200           # sec 6 (E6)
H_MAX = 35                  # sec 3 (E5)
H_BUCKETS = [(1, 3), (4, 7), (8, 14), (15, 35)]
FORECAST_MOVE_CAP_X = 3.0   # sec 3 (E4)
BAND_LO, BAND_HI = 0.03, 0.97          # sec 5
H2_YES_BAND = (0.90, 0.955)            # sec 6 (E7)
H2_NO_BAND = (0.045, 0.10)
H2_MODEL_FLOOR = 0.995
HAIRCUT = 0.03              # sec 4 binding
HAIRCUT_MATCHED = 0.01      # sec 4 reported run
AMBIG_LO, AMBIG_HI = 3, 9   # sec 2 (E1): ET hours [03:00, 09:00) cannot fire


def taker_fee(p_exec: float) -> float:
    """Worst-case taker quadratic, ceil(7*p*(1-p)) cents, in dollars (sec 4)."""
    if p_exec > 1.0:
        raise ValueError(f"p_exec > 1 is definitionally unexecutable: {p_exec}")
    return math.ceil(7.0 * p_exec * (1.0 - p_exec) - 1e-12) / 100.0


def iso_week_utc(close_time: str) -> str:
    d = datetime.strptime(close_time[:10], "%Y-%m-%d").date()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def bucket_of(h: int) -> tuple[int, int] | None:
    for lo, hi in H_BUCKETS:
        if lo <= h <= hi:
            return (lo, hi)
    return None


@dataclass
class FitResult:
    a: float
    th_up: float
    th_dn: float
    rho: float
    n_rows: int
    degenerate: bool          # clamp tripped (spectral radius or later move cap)
    max_move35: float         # largest |35d move| in fitting window


class GasData:
    """As-of accessors per lock section 2."""

    def __init__(self, aaa: dict[str, float], w: dict[str, float]):
        self.aaa = {date.fromisoformat(k): v for k, v in aaa.items()}
        self.w_dates = sorted(date.fromisoformat(k) for k in w)
        self.w_vals = {date.fromisoformat(k): v for k, v in w.items()}
        self.aaa_dates = sorted(self.aaa)
        self._margin_cache: dict[tuple[date, int], float | None] = {}

    def r(self, d: date) -> float | None:
        return self.aaa.get(d)

    @staticmethod
    def _release_cutoff(d: date) -> date:
        """EIA petroleum spot publishes WEEKLY on Wednesdays, covering through the
        prior Monday (verified 2026-07-02: freshest DGASNYH obs was Mon 06-29 after
        the Wed 07-01 release; eia.gov release dates 7/1 and 7/8). Visibility: the
        last Wednesday W <= d-1 (one-day FRED-mirror margin), data through W-2."""
        w = d - timedelta(days=1)
        while w.weekday() != 2:
            w -= timedelta(days=1)
        return w - timedelta(days=2)

    def w_asof(self, d: date, lag: int | None = W_LAG_DAYS) -> float | None:
        cut = (d - timedelta(days=lag)) if lag is not None else self._release_cutoff(d)
        i = bisect.bisect_right(self.w_dates, cut)
        if i == 0:
            return None
        return self.w_vals[self.w_dates[i - 1]]

    def margin(self, s: date, lag: int = W_LAG_DAYS) -> float | None:
        """m(s): rolling 180d median of R - W_asof over valid pairs (sec 2)."""
        key = (s, lag)
        if key in self._margin_cache:
            return self._margin_cache[key]
        pairs = []
        for u_off in range(MARGIN_WIN):
            u = s - timedelta(days=u_off)
            r = self.aaa.get(u)
            if r is None:
                continue
            w = self.w_asof(u, lag)
            if w is None:
                continue
            pairs.append(r - w)
        out = None
        if len(pairs) >= MARGIN_MIN_PAIRS:
            out = float(np.median(pairs))
        self._margin_cache[key] = out
        return out

    def valid_rows(self, upto: date, lag: int = W_LAG_DAYS):
        """Regression rows s with s+1 <= upto (R(s+1) known at as-of date), per sec 2."""
        rows = []
        for s in self.aaa_dates:
            if s + timedelta(days=1) > upto:
                break
            r_m1 = self.aaa.get(s - timedelta(days=1))
            r_0 = self.aaa.get(s)
            r_p1 = self.aaa.get(s + timedelta(days=1))
            if r_m1 is None or r_0 is None or r_p1 is None:
                continue
            w = self.w_asof(s, lag)
            if w is None:
                continue
            m = self.margin(s, lag)
            if m is None:
                continue
            g = (w + m) - r_0
            rows.append((s, g, r_0 - r_m1, r_p1 - r_0))
        return rows


class Model:
    """Frozen primary spec + control + walk-forward empirical errors (sec 3)."""

    def __init__(self, data: GasData, lag: int = W_LAG_DAYS, fallback: bool = False,
                 subsample_errors: bool = False):
        self.d = data
        self.lag = lag
        self.fallback = fallback
        self.subsample_errors = subsample_errors  # non-binding E5 sensitivity
        self._fit_cache: dict[date, FitResult | None] = {}
        self._err_cache: dict[date, dict] = {}
        self._path_cache: dict[date, list[float] | None] = {}

    # ---- fitting ----
    def fit(self, t0: date) -> FitResult | None:
        if t0 in self._fit_cache:
            return self._fit_cache[t0]
        rows = self.d.valid_rows(t0, self.lag)
        out: FitResult | None = None
        if len(rows) >= MIN_FIT_ROWS:
            g = np.array([r[1] for r in rows])
            dr_lag = np.array([r[2] for r in rows])
            y = np.array([r[3] for r in rows])
            if self.fallback:
                x = np.column_stack([np.ones_like(g), g])
                beta, *_ = np.linalg.lstsq(x, y, rcond=None)
                a, th = float(beta[0]), float(beta[1])
                fit = FitResult(a, th, th, 0.0, len(rows), False, 0.0)
            else:
                x = np.column_stack([np.ones_like(g), np.maximum(g, 0), np.minimum(g, 0), dr_lag])
                beta, *_ = np.linalg.lstsq(x, y, rcond=None)
                fit = FitResult(float(beta[0]), float(beta[1]), float(beta[2]), float(beta[3]),
                                len(rows), False, 0.0)
            # stability clamp (E4): companion spectral radius per regime.
            # State (R, dR): dR' = th*(Weq - R) + rho*dR + a; R' = R + dR'.
            sr = 0.0
            for th in (fit.th_up, fit.th_dn):
                jac = np.array([[1.0 - th, fit.rho], [-th, fit.rho]])
                ev = np.linalg.eigvals(jac)
                sr = max(sr, float(np.max(np.abs(ev))))
            # max historical 35d move in fitting window
            r_series = [(s, self.d.aaa[s]) for s in self.d.aaa_dates if s <= t0]
            mv = 0.0
            vals = dict(r_series)
            for s, v in r_series:
                v2 = vals.get(s + timedelta(days=35))
                if v2 is not None:
                    mv = max(mv, abs(v2 - v))
            fit.max_move35 = mv
            fit.degenerate = sr >= 1.0
            out = fit
        self._fit_cache[t0] = out
        return out

    def path(self, t0: date, horizon: int) -> list[float] | None:
        """Forecast path R_hat(t0+1..t0+horizon); W, m frozen at as-of values."""
        key = t0
        if key not in self._path_cache:
            self._path_cache[key] = self._path(t0)
        p = self._path_cache[key]
        if p is None or len(p) < horizon:
            return None
        return p[:horizon]

    def _path(self, t0: date) -> list[float] | None:
        fit = self.fit(t0)
        if fit is None or fit.degenerate:
            return None
        r0 = self.d.r(t0)
        w = self.d.w_asof(t0, self.lag)
        m = self.d.margin(t0, self.lag)
        if r0 is None or w is None or m is None:
            return None
        r_m1 = self.d.r(t0 - timedelta(days=1))
        if r_m1 is None:
            return None  # dR seed requires R(t0-1); no implicit fill (E2, review M3)
        dr = r0 - r_m1
        weq = w + m
        out = []
        r = r0
        for _ in range(H_MAX):
            g = weq - r
            dr = fit.a + fit.th_up * max(g, 0.0) + fit.th_dn * min(g, 0.0) + fit.rho * dr
            r = r + dr
            out.append(r)
        # forecast-move cap (E4)
        if fit.max_move35 > 0 and abs(out[-1] - r0) > FORECAST_MOVE_CAP_X * fit.max_move35:
            return None
        return out

    # ---- walk-forward empirical errors, sqrt(h)-normalized within bucket (E5) ----
    def errors_at(self, t0: date) -> dict:
        """bucket -> sorted list of sqrt(h)-normalized errors realized by t0
        (pairs (u, u+h) with u+h <= t0). Cached incrementally per t0."""
        if t0 in self._err_cache:
            return self._err_cache[t0]
        buckets: dict[tuple[int, int], list[float]] = {b: [] for b in H_BUCKETS}
        cbuckets: dict[tuple[int, int], list[float]] = {b: [] for b in H_BUCKETS}
        for u in self.d.aaa_dates:
            if u + timedelta(days=1) > t0:
                break
            if self.subsample_errors and u.toordinal() % 7 != 0:
                continue  # ~independent weekly spacing (non-binding sensitivity)
            path = None
            for h in range(1, H_MAX + 1):
                tgt = u + timedelta(days=h)
                if tgt > t0:
                    break
                r_real = self.d.r(tgt)
                if r_real is None:
                    continue
                b = bucket_of(h)
                if b is None:
                    continue
                if path is None:
                    path = self.path(u, H_MAX) or []
                if len(path) >= h:
                    buckets[b].append((r_real - path[h - 1]) / math.sqrt(h))
                r_u = self.d.r(u)
                if r_u is not None:
                    cbuckets[b].append((r_real - r_u) / math.sqrt(h))
        out = {
            "model": {b: sorted(v) for b, v in buckets.items()},
            "control": {b: sorted(v) for b, v in cbuckets.items()},
        }
        self._err_cache[t0] = out
        # keep only the two most recent t0 entries (trades arrive chronologically;
        # a full cache would hold hundreds of MB of error lists)
        while len(self._err_cache) > 2:
            self._err_cache.pop(next(iter(self._err_cache)))
        return out

    @staticmethod
    def p_above(point: float, strike: float, errs_norm: list[float], h: int) -> float | None:
        """P(point + err > strike) from the empirical CDF (linear interp, E5 scaling)."""
        n = len(errs_norm)
        if n == 0:
            return None
        need = (strike - point) / math.sqrt(h)
        i = bisect.bisect_right(errs_norm, need)
        if i == 0:
            return 1.0 - 0.5 / n
        if i == n:
            return 0.5 / n
        lo, hi = errs_norm[i - 1], errs_norm[i]
        frac = (need - lo) / (hi - lo) if hi > lo else 0.0
        cdf = (i - 1 + frac + 0.5) / n
        return max(min(1.0 - cdf, 1.0 - 0.5 / n), 0.5 / n)


def load_data(series: str = "DGASNYH") -> GasData:
    aaa = json.load(open(os.path.join(DATA, "aaa_daily.json"), encoding="utf-8"))
    fred = json.load(open(os.path.join(DATA, "fred_wholesale.json"), encoding="utf-8"))
    return GasData(aaa, fred[series])


def load_markets() -> dict:
    return json.load(open(os.path.join(DATA, "markets_all.json"), encoding="utf-8"))


def iter_trades():
    """Yield trades deduplicated on the full identity tuple (code review H1: the
    historical/live endpoint split re-serves ~2.9 percent of prints)."""
    seen: set[tuple] = set()
    with open(os.path.join(DATA, "trades.jsonl"), encoding="utf-8") as f:
        for line in f:
            t = json.loads(line)
            key = (t.get("ticker"), t.get("created_time"), t.get("yes_price_dollars"),
                   t.get("count_fp"), t.get("taker_side"))
            if key in seen:
                continue
            seen.add(key)
            yield t


def assert_aaa_coverage(aaa: dict) -> None:
    """Code review C1: refuse to run on a partial AAA series (zero-staleness would
    silently no-fire the missing era and fabricate an UNDERPOWERED-NULL)."""
    dates = sorted(aaa)
    if len(dates) < 480 or dates[0] > "2024-10-01" or dates[-1] < "2026-06-28":
        raise AssertionError(
            f"aaa_daily.json incomplete: {len(dates)} dates {dates[0]}..{dates[-1]}; "
            "finish scripts/v25/pull_aaa_history.py before running audits/backtest")


@dataclass
class Fire:
    ticker: str
    event: str
    series: str
    cluster: str
    month_cluster: str
    et_date: str
    h: int
    p_print: float
    side: str                 # "yes" or "no"
    taker_side_matched: bool
    p_model: float
    p_control: float
    divergence: float
    close_time: str
    strike: float


def evaluate_fires(data: GasData, model: Model, control_min_errs: int = MIN_ERRS_H1,
                   threshold: float = 0.08, signal_control: bool = False,
                   mode: str = "h1", verbose: bool = False):
    """Walk every trade; emit Fire records per lock sections 2-6. Outcome-blind.
    signal_control=True runs the CONTROL STRATEGY (fires on P_control divergence,
    gate 3). mode="h2" applies the H2 certainty-stratum rules (repaired bands,
    both-model floor, 200-error minimum) instead of the divergence rule."""
    markets = load_markets()
    # group trades by (ticker, ET date), keep chronological order
    fires: list[Fire] = []
    taken: set[tuple[str, str]] = set()
    n = {"prints": 0, "band": 0, "ambig": 0, "stale": 0, "h": 0, "fit": 0, "errs": 0,
         "fired": 0, "dedup": 0, "nostrike": 0, "h2_unexecutable": 0, "fit_degenerate_days": 0,
         "fit_days": 0}
    deg_days: set = set()
    fit_days: set = set()
    trades = sorted(iter_trades(), key=lambda t: t["created_time"])
    for t in trades:
        n["prints"] += 1
        m = markets.get(t["ticker"])
        if m is None:
            continue
        if m.get("strike_type") != "greater" or m.get("floor_strike") is None:
            n["nostrike"] += 1
            continue
        p = float(t["yes_price_dollars"])
        if mode == "h2":
            in_yes = H2_YES_BAND[0] <= p <= H2_YES_BAND[1]
            in_no = H2_NO_BAND[0] <= p <= H2_NO_BAND[1]
            if not (in_yes or in_no):
                # E7 reporting duty: certainty-region prints outside the feasibility band
                if H2_YES_BAND[1] < p <= 0.985 or 0.015 <= p < H2_NO_BAND[0]:
                    n["h2_unexecutable"] += 1
                continue
        elif not (BAND_LO <= p <= BAND_HI):
            continue
        n["band"] += 1
        dt_utc = datetime.strptime(t["created_time"][:19], "%Y-%m-%dT%H:%M:%S")
        dt_et = dt_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ET)
        if AMBIG_LO <= dt_et.hour < AMBIG_HI:
            n["ambig"] += 1
            continue
        t0 = dt_et.date() if dt_et.hour >= AMBIG_HI else dt_et.date() - timedelta(days=1)
        if data.r(t0) is None:
            n["stale"] += 1
            continue
        key = (t["ticker"], str(dt_et.date()))
        if key in taken:
            n["dedup"] += 1
            continue
        d_close = date.fromisoformat(m["close_time"][:10])
        h = (d_close - t0).days
        if not (1 <= h <= H_MAX):
            n["h"] += 1
            continue
        fit_days.add(t0)
        fit = model.fit(t0)
        if fit is not None and fit.degenerate:
            deg_days.add(t0)
        path = model.path(t0, h)
        if path is None:
            n["fit"] += 1
            continue
        b = bucket_of(h)
        errs = model.errors_at(t0)
        e_m = errs["model"][b]
        e_c = errs["control"][b]
        min_m = MIN_ERRS_H2 if mode == "h2" else MIN_ERRS_H1
        min_c = MIN_ERRS_H2 if mode == "h2" else control_min_errs
        if len(e_m) < min_m or len(e_c) < min_c:
            n["errs"] += 1
            continue
        k = m.get("floor_strike")
        if k is None:
            continue
        p_model = Model.p_above(path[h - 1], k, e_m, h)
        r0 = data.r(t0)
        p_control = Model.p_above(r0, k, e_c, h)
        if p_model is None or p_control is None:
            n["errs"] += 1
            continue
        if mode == "h2":
            if H2_YES_BAND[0] <= p <= H2_YES_BAND[1] and p_model >= H2_MODEL_FLOOR and p_control >= H2_MODEL_FLOOR:
                side = "yes"
            elif H2_NO_BAND[0] <= p <= H2_NO_BAND[1] and p_model <= 1 - H2_MODEL_FLOOR and p_control <= 1 - H2_MODEL_FLOOR:
                side = "no"
            else:
                continue
            div = p_model - p
        else:
            p_sig = p_control if signal_control else p_model
            div = p_sig - p
            if abs(div) < threshold:
                continue
            side = "yes" if div > 0 else "no"
        matched = (t.get("taker_side") or "").lower() == side
        iso = iso_week_utc(m["close_time"])
        fires.append(Fire(
            ticker=t["ticker"], event=m.get("event_ticker") or "", series=t.get("series") or "",
            cluster=iso, month_cluster=m["close_time"][:7], et_date=str(dt_et.date()),
            h=h, p_print=p, side=side, taker_side_matched=matched,
            p_model=p_model, p_control=p_control, divergence=div,
            close_time=m["close_time"], strike=float(k),
        ))
        taken.add(key)
        n["fired"] += 1
        if verbose and n["fired"] % 50 == 0:
            print(f"fires: {n['fired']}", flush=True)
    n["fit_days"] = len(fit_days)
    n["fit_degenerate_days"] = len(deg_days)
    return fires, n
