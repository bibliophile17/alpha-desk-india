r"""Check an announcements CSV before running the study. Read-only: flags, never edits.

  python scripts\validate_announcements.py --events data\reference\earnings_announcements.csv
Exit code 1 if any row has a blocking problem (bad date, no source_url, unknown ticker, no price file).
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from alphadesk.announcements import align_events, load_announcements
from alphadesk.pricefiles import load_price_frames, series_of
from alphadesk.tradingcalendar import TradingCalendar

ap = argparse.ArgumentParser()
ap.add_argument("--events", default="data/reference/earnings_announcements.csv")
ap.add_argument("--prices-dir", default="data/raw/prices")
ap.add_argument("--universe", default="config/universe.csv")
a = ap.parse_args()

raw = load_announcements(a.events)
blocking, warn = [], []
d = pd.to_datetime(raw["announce_date"], errors="coerce")
for i in raw.index[d.isna()]:
    blocking.append((i + 2, "unparseable announce_date"))
for i in raw.index[raw["source_url"].isna() | (raw["source_url"].astype(str).str.strip() == "")]:
    blocking.append((i + 2, "no source_url (every event must be traceable)"))
for i in raw.index[raw["time_source"].isna()]:
    warn.append((i + 2, "no time_source"))
if d.max() > pd.Timestamp.now().normalize():
    for i in raw.index[d > pd.Timestamp.now().normalize()]:
        blocking.append((i + 2, "announce_date in the future"))
if Path(a.universe).exists():
    uni = set(pd.read_csv(a.universe)["ticker"])
    for i in raw.index[~raw["ticker"].isin(uni)]:
        blocking.append((i + 2, f"ticker {raw.at[i, 'ticker']} not in universe"))
frames = load_price_frames(a.prices_dir)
for i in raw.index[~raw["ticker"].isin(frames)]:
    blocking.append((i + 2, f"no price file for {raw.at[i, 'ticker']}"))
cal = TradingCalendar(series_of(frames, "^NSEI", "close").dropna().index)
ok = raw[d.notna()]
inside = (pd.to_datetime(ok["announce_date"]) >= cal.first) & (pd.to_datetime(ok["announce_date"]) <= cal.last)
for i in ok.index[~inside]:
    blocking.append((i + 2, "announce_date outside the price calendar"))
for i in ok.index[inside]:
    dt = pd.Timestamp(ok.at[i, "announce_date"]).normalize()
    if dt.weekday() < 5 and not cal.is_session(dt):
        warn.append((i + 2, f"{dt.date()} is a weekday with no session (holiday or data gap): "
                            "the event rolls to the next session; confirm it is a real NSE holiday"))
ev, dropped = align_events(ok[inside], cal)
print(f"rows: {len(raw)}  after dedup: {len(ev)}  duplicates logged: {len(dropped)}")
print("timing classes:\n" + ev["timing_class"].value_counts().to_string())
print(f"eligible for the primary study: {int(ev['eligible_primary'].sum())}")
print(f"companies: {ev['ticker'].nunique()}  distinct day-0 dates: {ev.loc[ev['eligible_primary'], 'day0'].nunique()}")
for tag, items in (("BLOCKING", blocking), ("warning", warn)):
    for line, msg in items:
        print(f"{tag}: csv line {line}: {msg}")
print("RESULT:", "FIX BLOCKING ROWS" if blocking else "OK to run the study")
sys.exit(1 if blocking else 0)
