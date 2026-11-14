"""Fetch prices for the whole universe + benchmarks using the existing yfinance provider.

  python scripts/fetch_prices.py --universe config/universe.csv --start 2022-01-01

Saves data/raw/prices/prices_<ticker>.csv, flags and summary under logs/fetch_prices/<ts>/.
Nothing is dropped or filled. Exit code 1 if any ticker failed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from alphadesk.prices import PriceError, YFinanceProvider
from alphadesk.validate import run_all_checks

IST = ZoneInfo("Asia/Kolkata")
INDICES = ["^NSEI", "^CNX100"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", default="config/universe.csv")
    ap.add_argument("--start", default="2022-01-01")
    ap.add_argument("--out", default="data/raw/prices")
    ap.add_argument("--sleep", type=float, default=0.3)
    a = ap.parse_args()

    uni = pd.read_csv(a.universe)
    tickers = INDICES + [t for t in uni["ticker"].dropna().unique() if t not in INDICES]
    end = datetime.now(IST).date().isoformat()          # exclusive: last completed session
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    logd = Path("logs/fetch_prices") / stamp
    logd.mkdir(parents=True, exist_ok=True)

    prov = YFinanceProvider()
    flags, failures, ok_rows, bench_dates = [], [], [], None
    for tk in tickers:
        try:
            df = prov.fetch(tk, a.start, end)
        except PriceError as exc:
            failures.append({"ticker": tk, "stage": exc.stage, "message": str(exc)})
            print(f"FAIL [{exc.stage}] {tk}: {exc}")
            continue
        except Exception as exc:
            failures.append({"ticker": tk, "stage": "unclassified", "message": f"{type(exc).__name__}: {exc}"})
            print(f"FAIL [unclassified] {tk}: {exc}")
            continue
        if tk == "^NSEI":
            bench_dates = set(df["date"])
        try:
            flags += run_all_checks(df, tk, bench_dates, a.start, end)
            df.to_csv(out / f"prices_{tk.replace('^', 'IDX_')}.csv", index=False)
        except Exception as exc:
            failures.append({"ticker": tk, "stage": "processing", "message": f"{type(exc).__name__}: {exc}"})
            print(f"FAIL [processing] {tk}: {exc}")
            continue
        ok_rows.append({"ticker": tk, "rows": len(df), "first": str(df["date"].min().date()),
                        "last": str(df["date"].max().date())})
        time.sleep(a.sleep)

    fl = pd.DataFrame(flags, columns=["ticker", "date", "check", "severity", "detail"])
    fl.to_csv(logd / "flags.csv", index=False)
    summ = {"run_at_utc": stamp, "start": a.start, "end_exclusive": end,
            "requested": len(tickers), "succeeded": len(ok_rows), "failures": failures,
            "review_flags_by_check": fl[fl["severity"] == "review"]["check"].value_counts().to_dict(),
            "tickers": ok_rows}
    (logd / "summary.json").write_text(json.dumps(summ, indent=2, default=str))
    print(f"\n{len(ok_rows)}/{len(tickers)} fetched; failures={len(failures)}; "
          f"review flags={int((fl['severity'] == 'review').sum())}. Logs: {logd}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
