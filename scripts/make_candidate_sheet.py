r"""Build a WORKSHEET of candidate past results dates from yfinance, for you to verify by hand.

  python scripts/make_candidate_sheet.py --tickers RELIANCE.NS TCS.NS INFY.NS

Writes data/reference/candidates_to_verify.csv, NOT the study file. Yahoo's times are not
trusted (the probe showed implausible hours), so announce_time/source_url are left blank.
Only dates in the past are kept. A candidate becomes a study row only after you check the
company's own filing (BSE/NSE announcement or investor page), fill announce_time (IST),
time_source, source_url, and copy the row into earnings_announcements.csv.
"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ap = argparse.ArgumentParser()
ap.add_argument("--tickers", nargs="+", required=True)
ap.add_argument("--limit", type=int, default=12)
ap.add_argument("--out", default="data/reference/candidates_to_verify.csv")
a = ap.parse_args()

uni = Path("config/universe.csv")
sectors = dict(pd.read_csv(uni)[["ticker", "sector"]].values) if uni.exists() else {}
now = pd.Timestamp.now(tz="UTC")
rows = []
for tk in a.tickers:
    try:
        df = yf.Ticker(tk).get_earnings_dates(limit=a.limit)
    except Exception as exc:
        print("FAIL", tk, type(exc).__name__, exc)
        continue
    if df is None or df.empty:
        print("EMPTY", tk)
        continue
    for ts in df.index:
        if ts.tz_convert("UTC") >= now:
            continue                                  # future/projected dates are never candidates
        rows.append({"ticker": tk, "sector": sectors.get(tk), "yahoo_date": ts.date(),
                     "fiscal_quarter": "", "announce_date": "", "announce_time": "",
                     "time_source": "", "source_url": "",
                     "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
out = pd.DataFrame(rows)
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
out.to_csv(a.out, index=False)
print(f"{len(out)} candidate rows for {out['ticker'].nunique() if len(out) else 0} tickers -> {a.out}")
