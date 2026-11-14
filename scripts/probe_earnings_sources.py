"""Probe whether yfinance exposes usable earnings dates for Indian tickers.

  python scripts/probe_earnings_sources.py

UNTESTED against real data when written. Prints what comes back so we can judge:
how many past dates, whether times are present, and whether they look plausible
against the company's own filings. Run it locally AND from GitHub Actions.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

TICKERS = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ITC.NS"]
res, bad = [], 0
for tk in TICKERS:
    try:
        df = yf.Ticker(tk).get_earnings_dates(limit=24)
        if df is None or len(df) == 0:
            raise RuntimeError("empty")
        idx = df.index
        res.append({"ticker": tk, "rows": len(df), "columns": list(df.columns),
                    "oldest": str(idx.min()), "newest": str(idx.max()),
                    "distinct_times": sorted({str(t.time()) for t in idx})[:10]})
        print(tk, len(df), "rows;", idx.min(), "->", idx.max(), "; times:", res[-1]["distinct_times"])
    except Exception as exc:
        bad += 1
        res.append({"ticker": tk, "error": f"{type(exc).__name__}: {exc}"})
        print("FAIL", tk, exc)
d = Path("logs/earnings_probe")
d.mkdir(parents=True, exist_ok=True)
(d / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")).write_text(json.dumps(res, indent=2))
sys.exit(1 if bad else 0)
