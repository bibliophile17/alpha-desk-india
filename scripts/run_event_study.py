"""Run the earnings event study from saved prices + an announcements CSV.

  python scripts/run_event_study.py --events data/reference/earnings_announcements.csv ^
         --prices-dir data/raw/prices --benchmark ^CNX100

Defaults (documented in docs/known_issues.md): stock returns from adj_close,
benchmark = price index close, sessions = observed ^NSEI dates, estimation window
[-130,-11], min 100 usable estimation days. Gaps are never filled: a benchmark gap
drops that day from estimation and voids any event window that touches it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import scipy

from alphadesk.announcements import add_performance_proxy, align_events, load_announcements
from alphadesk.eventstudy import EST_WINDOW, WINDOWS, run_event_study, session_returns
from alphadesk.inference import group_summary, summarize
from alphadesk.placebo import placebo_shift_test
from alphadesk.tradingcalendar import TradingCalendar


def load_price_dir(d, price_col):
    series = {}
    for f in sorted(Path(d).glob("prices_*.csv")):
        name = f.stem[len("prices_"):]
        is_index = name.startswith("IDX_")
        name = "^" + name[4:] if is_index else name
        df = pd.read_csv(f, parse_dates=["date"])
        series[name] = df.set_index("date")["close" if is_index else price_col]
    return series


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--prices-dir", required=True)
    ap.add_argument("--benchmark", default="^CNX100")
    ap.add_argument("--calendar", default="^NSEI")
    ap.add_argument("--price-col", default="adj_close", choices=["adj_close", "close"])
    ap.add_argument("--out", default="outputs/event_study")
    ap.add_argument("--min-n", type=int, default=30)
    ap.add_argument("--min-n-sector", type=int, default=15)
    ap.add_argument("--min-est-obs", type=int, default=100)
    a = ap.parse_args()

    series = load_price_dir(a.prices_dir, a.price_col)
    for need in (a.calendar, a.benchmark):
        if need not in series:
            print(f"ERROR: no price file for {need} in {a.prices_dir}")
            return 1
    cal = TradingCalendar(series[a.calendar].dropna().index)
    bench = session_returns(series[a.benchmark], cal)
    stock_rets = {t: session_returns(s, cal) for t, s in series.items() if not t.startswith("^")}
    if not stock_rets:
        print("ERROR: no stock price files found")
        return 1

    raw = add_performance_proxy(load_announcements(a.events))
    events, dropped = align_events(raw, cal)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    events.to_csv(out / "events_aligned.csv", index=False)
    dropped.to_csv(out / "events_dropped_duplicates.csv", index=False)
    if not events["eligible_primary"].any():
        print("ERROR: no eligible events after timestamp alignment")
        print(events["timing_class"].value_counts().to_string())
        return 1

    res = run_event_study(events, stock_rets, bench, cal, min_est_obs=a.min_est_obs)
    res.to_csv(out / "results_by_event.csv", index=False)
    ok = res[res["status"].isin(["ok", "partial_missing_event_prices"])]

    overall, sector = [], []
    for w in WINDOWS:
        col = f"car_{w}"
        s = summarize(ok[col].to_numpy(float), ok["day0"].to_numpy(), min_n=a.min_n)
        overall.append({"window": w, **s})
        g = group_summary(ok, "sector", col, "day0", a.min_n_sector)
        g.insert(0, "window", w)
        sector.append(g)
    overall = pd.DataFrame(overall)
    overall.to_csv(out / "summary_overall.csv", index=False)
    pd.concat(sector).to_csv(out / "summary_by_sector.csv", index=False)

    prof = [{"day": k, "mean_ar": ok[f"ar_{k}"].mean(), "n": int(ok[f"ar_{k}"].notna().sum())}
            for k in range(-1, 6)]
    pd.DataFrame(prof).to_csv(out / "avg_ar_profile.csv", index=False)

    placebo = placebo_shift_test(ok, stock_rets, bench, cal, min_est_obs=a.min_est_obs)
    placebo.to_csv(out / "placebo.csv", index=False)

    meta = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "pandas": pd.__version__,
        "numpy": np.__version__, "scipy": scipy.__version__,
        "benchmark": a.benchmark, "calendar": a.calendar, "price_col": a.price_col,
        "estimation_window": EST_WINDOW, "windows": WINDOWS,
        "min_est_obs": a.min_est_obs, "min_n_overall": a.min_n,
        "min_n_sector": a.min_n_sector, "calendar_range": [str(cal.first.date()), str(cal.last.date())],
        "events_loaded": int(len(raw)), "events_after_dedup": int(len(events)),
        "events_eligible": int(events["eligible_primary"].sum()),
        "timing_class_counts": {k: int(v) for k, v in events["timing_class"].value_counts().items()},
        "result_status_counts": {k: int(v) for k, v in res["status"].value_counts().items()},
        "events_file_sha256": sha256(a.events),
        "price_files_sha256": hashlib.sha256("".join(
            sha256(f) for f in sorted(Path(a.prices_dir).glob("prices_*.csv"))).encode()).hexdigest(),
        "note": "CLUSTER p-values (cluster = day 0) are primary; results with n below "
                "threshold are exploratory.",
    }
    (out / "run_metadata.json").write_text(json.dumps(meta, indent=2, default=str))

    pd.set_option("display.width", 200)
    cols = ["window", "n", "n_clusters", "mean", "median", "pos_share", "t_p", "cluster_p",
            "wilcoxon_p", "sign_p", "label"]
    print("\nOVERALL (CAR, simple returns)")
    print(overall[cols].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print("\nPLACEBO (common shifts)")
    print(placebo.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    print(f"\nEligible events: {meta['events_eligible']} of {meta['events_after_dedup']}; "
          f"statuses: {meta['result_status_counts']}")
    print(f"Outputs in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
