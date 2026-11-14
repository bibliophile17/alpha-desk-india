"""Market-model event study in plain numpy, so every step can be explained.

  R_i,t = alpha_i + beta_i * R_m,t + e_i,t      (fit on the estimation window)
  AR_i,t  = R_i,t - (alpha_hat + beta_hat * R_m,t)   abnormal return, one day
  CAR_i[a,b] = sum_{t=a..b} AR_i,t                   cumulative abnormal return

The estimation window [-130,-11] ends 10 sessions BEFORE day 0, so the event's
own price reaction (and any pre-announcement drift) cannot leak into alpha/beta.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from alphadesk.tradingcalendar import TradingCalendar

EST_WINDOW = (-130, -11)
WINDOWS = {"[0,+1]": (0, 1), "[0,+3]": (0, 3), "[0,+5]": (0, 5), "[-1,+1]": (-1, 1)}
EVENT_SPAN = (-1, 5)   # sessions any reported window can touch


def session_returns(prices: pd.Series, cal: TradingCalendar) -> pd.Series:
    """Simple returns on calendar sessions: P_t / P_{t-1} - 1.

    A missing price gives NaN for that day AND the next day (a return across a
    gap is not a daily return). Nothing is filled and nothing becomes 0.
    """
    p = prices.copy()
    p.index = pd.DatetimeIndex(p.index).normalize()
    if p.index.has_duplicates:
        raise ValueError("duplicate dates in price series")
    p = p.reindex(cal.sessions)
    return p / p.shift(1) - 1


def ols_market_model(y, x) -> dict:
    """Closed-form OLS with an intercept: beta = Sxy/Sxx, alpha = ybar - beta*xbar."""
    y = np.asarray(y, float)
    x = np.asarray(x, float)
    m = np.isfinite(y) & np.isfinite(x)
    y, x = y[m], x[m]
    n = len(y)
    if n < 3:
        raise ValueError("need at least 3 observations")
    xm, ym = x.mean(), y.mean()
    sxx = ((x - xm) ** 2).sum()
    if sxx == 0:
        raise ValueError("benchmark has no variance in the estimation window")
    beta = ((x - xm) * (y - ym)).sum() / sxx
    alpha = ym - beta * xm
    resid = y - alpha - beta * x
    ssr = (resid ** 2).sum()
    sst = ((y - ym) ** 2).sum()
    return {"alpha": alpha, "beta": beta, "sigma": float(np.sqrt(ssr / (n - 2))),
            "r2": float(1 - ssr / sst) if sst > 0 else np.nan, "n": n}


def compute_event(stock_ret, bench_ret, cal, day0, est=EST_WINDOW, windows=WINDOWS,
                  min_est_obs=100, blank_idx=()) -> dict:
    """AR for sessions -1..+5 and CAR for each window, for one event.

    blank_idx: absolute session indices removed from the estimation window
    (other announcements' reaction days for the same stock).
    """
    k_lo = min(EVENT_SPAN[0], *(a for a, _ in windows.values()))
    k_hi = max(EVENT_SPAN[1], *(b for _, b in windows.values()))
    out = {"status": "ok", "est_obs": 0, "alpha": np.nan, "beta": np.nan,
           "sigma": np.nan, "r2": np.nan}
    for k in range(k_lo, k_hi + 1):
        out[f"ar_{k}"] = np.nan
    for w in windows:
        out[f"car_{w}"] = np.nan

    t0 = cal.index_of(day0)
    lo, hi = t0 + est[0], t0 + est[1]
    if lo < 0 or t0 + k_lo < 0 or t0 + k_hi >= len(cal.sessions):
        out["status"] = "insufficient_calendar"
        return out

    s = stock_ret.to_numpy(float)
    b = bench_ret.to_numpy(float)
    y, x = s[lo:hi + 1].copy(), b[lo:hi + 1].copy()
    for j in blank_idx:
        if lo <= j <= hi:
            y[j - lo] = np.nan
    ok = np.isfinite(y) & np.isfinite(x)
    out["est_obs"] = int(ok.sum())
    if ok.sum() < min_est_obs:
        out["status"] = "insufficient_estimation_obs"
        return out

    fit = ols_market_model(y[ok], x[ok])
    out.update(alpha=fit["alpha"], beta=fit["beta"], sigma=fit["sigma"], r2=fit["r2"])
    for k in range(k_lo, k_hi + 1):
        ri, rm = s[t0 + k], b[t0 + k]
        if np.isfinite(ri) and np.isfinite(rm):
            out[f"ar_{k}"] = ri - (fit["alpha"] + fit["beta"] * rm)
    for w, (a, c) in windows.items():
        v = [out[f"ar_{k}"] for k in range(a, c + 1)]
        if np.all(np.isfinite(v)):
            out[f"car_{w}"] = float(np.sum(v))
    if any(not np.isfinite(out[f"car_{w}"]) for w in windows):
        out["status"] = "partial_missing_event_prices"
    return out


def reaction_blank_set(day0_indices, span=EVENT_SPAN) -> set:
    return {t + k for t in day0_indices for k in range(span[0], span[1] + 1)}


def run_event_study(events: pd.DataFrame, stock_rets: dict, bench_ret, cal,
                    est=EST_WINDOW, windows=WINDOWS, min_est_obs=100) -> pd.DataFrame:
    """One row per eligible event. Failures keep their row with a status."""
    elig = events[events["eligible_primary"]]
    idx = {tk: sorted(cal.index_of(d) for d in g["day0"])
           for tk, g in elig.groupby("ticker")}
    rows = []
    for r in elig.to_dict("records"):
        base = {k: r.get(k) for k in ("ticker", "sector", "fiscal_quarter",
                                      "announce_date", "announce_time",
                                      "timing_class", "day0")}
        ret = stock_rets.get(r["ticker"])
        if ret is None:
            rows.append({**base, "status": "no_price_data"})
            continue
        t0 = cal.index_of(r["day0"])
        blank = reaction_blank_set([t for t in idx[r["ticker"]] if t != t0])
        rows.append({**base, **compute_event(ret, bench_ret, cal, r["day0"], est,
                                             windows, min_est_obs, blank)})
    return pd.DataFrame(rows)
