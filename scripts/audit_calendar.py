"""Audit the observed session calendar against the manually reviewed holiday CSV.

  python scripts/audit_calendar.py logs/price_probe/<ts>/prices_IDX_NSEI.csv

Prints every weekday with no session (candidate holiday), weekend sessions, and listed
holidays that traded. Confirm each candidate against NSE's official holiday circulars,
then add it to data/reference/nse_holidays.csv (date, description, source_url, reviewed_on).
"""
import sys
from pathlib import Path

import pandas as pd

from alphadesk.tradingcalendar import TradingCalendar, audit_calendar

cal = TradingCalendar.from_price_csv(sys.argv[1])
hol = Path("data/reference/nse_holidays.csv")
if not hol.exists():
    hol.parent.mkdir(parents=True, exist_ok=True)
    hol.write_text("date,description,source_url,reviewed_on\n")
a = audit_calendar(cal, hol)
a.to_csv("data/reference/calendar_audit.csv", index=False)
print(f"sessions {cal.first.date()}..{cal.last.date()}: {len(cal.sessions)}")
print(a["item"].value_counts().to_string() if len(a) else "no items")
print(a[a["item"] != "confirmed_holiday"].to_string(index=False))
