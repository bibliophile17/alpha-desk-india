"""Probe: fetch a few tickers, validate, log. Nothing is dropped, filled or corrected.

Exit codes: 0 = every ticker fetched, parsed and validated.
            1 = at least one failure (see summary.json 'failures').
"""
from __future__ import annotations

import json
import platform
import sys
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

from alphadesk.prices import PriceError, YFinanceProvider
from alphadesk.validate import run_all_checks

IST = ZoneInfo("Asia/Kolkata")
STOCKS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"]
BENCHMARK_FOR_SESSIONS = "^NSEI"      # Nifty 50: used as the trading-day record
EXTRA_INDICES = ["^CNX100"]           # Nifty 100: we need to know if this works
FLAG_COLUMNS = ["ticker", "date", "check", "severity", "detail"]


def record_failure(failures, ticker, stage, exc):
    failures.append({"ticker": ticker, "stage": stage,
                     "error_type": type(exc).__name__, "message": str(exc)})
    print(f"FAIL  [{stage}] {ticker}: {type(exc).__name__}: {exc}")


def main() -> int:
    ist_today = datetime.now(IST).date()
    start = ist_today - timedelta(days=3 * 365)
    start_s, end_s = start.isoformat(), ist_today.isoformat()   # end is exclusive

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path("logs/price_probe") / stamp
    out.mkdir(parents=True, exist_ok=True)

    provider = YFinanceProvider()
    results, all_flags, failures = [], [], []
    session_check_skipped = []
    benchmark_dates = None

    for ticker in [BENCHMARK_FOR_SESSIONS] + STOCKS + EXTRA_INDICES:
        # Stage 1: fetch + format check
        try:
            df = provider.fetch(ticker, start_s, end_s)
        except PriceError as exc:
            record_failure(failures, ticker, exc.stage, exc)
            continue
        except Exception as exc:
            record_failure(failures, ticker, "unclassified", exc)
            continue

        # Stage 2: validation + writing
        try:
            if ticker == BENCHMARK_FOR_SESSIONS:
                benchmark_dates = set(df["date"])
            elif benchmark_dates is None:
                session_check_skipped.append(ticker)

            flags = run_all_checks(df, ticker, benchmark_dates, start_s, end_s)
            for col in df.attrs.get("actions_columns_missing", []):
                flags.append({"ticker": ticker, "date": None,
                              "check": "actions_column_absent", "severity": "review",
                              "detail": f"'{col}' absent; assumed no events, "
                                        "corporate-action checks blind for this ticker"})
            df.to_csv(out / f"prices_{ticker.replace('^', 'IDX_')}.csv", index=False)
        except Exception as exc:
            record_failure(failures, ticker, "processing", exc)
            traceback.print_exc()
            continue

        all_flags += flags
        n_review = sum(f["severity"] == "review" for f in flags)
        n_info = sum(f["severity"] == "info" for f in flags)
        results.append({
            "ticker": ticker, "status": "ok", "rows": len(df),
            "first_date": str(df["date"].min().date()),
            "last_date": str(df["date"].max().date()),
            "review_flags": n_review, "info_flags": n_info,
        })
        print(f"OK    {ticker}: {len(df)} rows, {df['date'].min().date()} to "
              f"{df['date'].max().date()}, review={n_review}, info={n_info}")

    exit_code = 1 if failures else 0
    pd.DataFrame(all_flags, columns=FLAG_COLUMNS).to_csv(out / "flags.csv", index=False)
    summary = {
        "run_at_utc": stamp, "ist_date": ist_today.isoformat(),
        "platform": platform.platform(), "python": platform.python_version(),
        "yfinance": yf.__version__, "start": start_s, "end_exclusive": end_s,
        "tickers": results, "failures": failures,
        "session_check_skipped_for": session_check_skipped,
        "exit_code": exit_code,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\nLogs written to {out}")
    print(f"Failures: {len(failures)}  (exit code {exit_code})")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())