r"""Append ONE verified announcement to data/reference/earnings_announcements.csv, with checks.

  python scripts\add_event.py --ticker TCS.NS --quarter Q2FY26 --date 2025-10-09 --time 15:42 ^
      --time-source bse_filing --url https://www.bseindia.com/... [--sector "Information Technology"]
  python scripts\add_event.py ... --no-time     (date known, time unknown: row is kept but will be excluded)

Only enter what a filing or the company's own page states. Times are IST, 24-hour HH:MM.
Refuses: unknown ticker, bad date/time, future date, missing URL, duplicate (ticker, quarter).
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

COLS = ["ticker", "company", "sector", "fiscal_quarter", "announce_date", "announce_time", "time_source",
        "revenue", "pat", "eps", "prior_revenue", "prior_pat", "prior_eps", "source_url", "retrieved_at"]
ap = argparse.ArgumentParser()
ap.add_argument("--ticker", required=True)
ap.add_argument("--quarter", required=True, help="e.g. Q2FY26 (April-March fiscal year)")
ap.add_argument("--date", required=True)
ap.add_argument("--time", default=None)
ap.add_argument("--no-time", action="store_true")
ap.add_argument("--time-source", default=None, help="e.g. bse_filing, nse_filing, company_site")
ap.add_argument("--url", required=True)
ap.add_argument("--revenue", type=float); ap.add_argument("--pat", type=float)
ap.add_argument("--prior-revenue", type=float); ap.add_argument("--prior-pat", type=float)
ap.add_argument("--file", default="data/reference/earnings_announcements.csv")
ap.add_argument("--universe", default="config/universe.csv")
a = ap.parse_args()

if not re.fullmatch(r"Q[1-4]FY\d{2}", a.quarter):
    sys.exit("BAD --quarter: use the form Q2FY26")
if not a.url.startswith(("http://", "https://")):
    sys.exit("BAD --url: must be a link to the filing or page")
try:
    d = pd.Timestamp(a.date)
except Exception:
    sys.exit("BAD --date: use YYYY-MM-DD")
if d > pd.Timestamp.now().normalize():
    sys.exit("BAD --date: in the future")
if a.no_time == (a.time is not None):
    sys.exit("give exactly one of --time HH:MM or --no-time")
if a.time and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", a.time):
    sys.exit("BAD --time: use 24-hour HH:MM in IST")
if a.time and not a.time_source:
    sys.exit("--time needs --time-source (where did the time come from?)")
uni = pd.read_csv(a.universe).set_index("ticker")
if a.ticker not in uni.index:
    sys.exit(f"ticker {a.ticker} not in {a.universe}")

p = Path(a.file)
df = pd.read_csv(p, dtype=str) if p.exists() and p.stat().st_size > 0 else pd.DataFrame(columns=COLS)
if ((df.get("ticker") == a.ticker) & (df.get("fiscal_quarter") == a.quarter)).any():
    sys.exit(f"duplicate: {a.ticker} {a.quarter} already present (edit the file by hand if it is wrong)")
row = {"ticker": a.ticker, "company": uni.at[a.ticker, "company"], "sector": uni.at[a.ticker, "sector"],
       "fiscal_quarter": a.quarter, "announce_date": str(d.date()), "announce_time": a.time or "",
       "time_source": a.time_source or "", "revenue": a.revenue, "pat": a.pat, "eps": "",
       "prior_revenue": a.prior_revenue, "prior_pat": a.prior_pat, "prior_eps": "",
       "source_url": a.url, "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
pd.concat([df, pd.DataFrame([row])], ignore_index=True)[COLS].to_csv(p, index=False)
print(f"added {a.ticker} {a.quarter} {d.date()} {a.time or '(no time)'}; file now has {len(df) + 1} rows")
