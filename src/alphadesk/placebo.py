"""Common-shift placebo test.

Every real event date is moved by the SAME shift (-50..+50 sessions, excluding
|shift| <= 10) and the identical pipeline is re-run. Using one shift for all events
keeps same-day clustering intact, so the null distribution has the right spread.
If the real mean CAR is not unusual versus the 80 placebo means, the 'effect' is
not specific to announcement dates.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from alphadesk.eventstudy import WINDOWS, compute_event, reaction_blank_set

SHIFTS = [s for s in range(-50, 51) if abs(s) >= 11]


def placebo_shift_test(results: pd.DataFrame, stock_rets: dict, bench_ret, cal,
                       windows=WINDOWS, shifts=SHIFTS, min_est_obs=100,
                       buffer=10) -> pd.DataFrame:
    ev = results[results["status"].isin(["ok", "partial_missing_event_prices"])]
    real = {tk: sorted(cal.index_of(d) for d in g["day0"]) for tk, g in ev.groupby("ticker")}
    blank = {tk: reaction_blank_set(v) for tk, v in real.items()}
    null = {w: [] for w in windows}
    for s in shifts:
        cars = {w: [] for w in windows}
        for r in ev.to_dict("records"):
            tk = r["ticker"]
            t_new = cal.index_of(r["day0"]) + s
            if t_new < 0 or t_new >= len(cal.sessions):
                continue
            if any(abs(t_new - t) <= buffer for t in real[tk]):
                continue
            res = compute_event(stock_rets[tk], bench_ret, cal, cal.session_at(t_new),
                                windows=windows, min_est_obs=min_est_obs,
                                blank_idx=blank[tk])
            for w in windows:
                cars[w].append(res[f"car_{w}"])
        for w in windows:
            a = np.array(cars[w], float)
            a = a[np.isfinite(a)]
            null[w].append(a.mean() if len(a) else np.nan)
    rows = []
    for w in windows:
        obs_vals = ev[f"car_{w}"].to_numpy(float)
        obs = float(np.nanmean(obs_vals)) if np.isfinite(obs_vals).any() else np.nan
        nv = np.array(null[w], float)
        nv = nv[np.isfinite(nv)]
        p = (1 + int((np.abs(nv) >= abs(obs)).sum())) / (len(nv) + 1) if len(nv) else np.nan
        rows.append({"window": w, "observed_mean_car": obs, "placebo_mean": float(nv.mean()) if len(nv) else np.nan,
                     "placebo_sd": float(nv.std(ddof=1)) if len(nv) > 1 else np.nan,
                     "n_shifts_used": len(nv), "placebo_p_two_sided": p})
    return pd.DataFrame(rows)
