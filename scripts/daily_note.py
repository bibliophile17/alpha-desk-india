"""Daily note: `draft` writes notes/drafts/<date>.md; `publish <file>` refuses unless the
author has replaced every TODO(author) and the data is from the latest session.

  python scripts/daily_note.py draft --prices-dir data/raw/prices
  python scripts/daily_note.py publish notes/drafts/2026-11-13.md --prices-dir data/raw/prices
"""
import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from alphadesk.notes import market_snapshot, publish_problems, render_note
from alphadesk.pricefiles import load_price_frames, series_of
from alphadesk.tradingcalendar import TradingCalendar

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["draft", "publish"])
ap.add_argument("file", nargs="?")
ap.add_argument("--prices-dir", default="data/raw/prices")
ap.add_argument("--universe", default="config/universe.csv")
ap.add_argument("--announcements", default="data/reference/earnings_announcements.csv")
a = ap.parse_args()

frames = load_price_frames(a.prices_dir)
cal = TradingCalendar(series_of(frames, "^NSEI", "close").dropna().index)
uni = pd.read_csv(a.universe) if Path(a.universe).exists() else None
ann = pd.read_csv(a.announcements, dtype={"announce_time": str}) if Path(a.announcements).exists() else None
snap = market_snapshot(frames, cal, uni, ann)

if a.cmd == "draft":
    out = Path("notes/drafts") / f"{snap['asof'].date()}.md"
    if out.exists():
        sys.exit(f"{out} exists; refusing to overwrite the author's work")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_note(snap), encoding="utf-8")
    print(f"Draft written: {out}. Fill every TODO(author), then publish.")
else:
    src = Path(a.file)
    text = src.read_text(encoding="utf-8")
    m = re.search(r"^date: (\S+)", text, re.M)
    probs = publish_problems(text, m.group(1) if m else "1900-01-01", cal.last)
    if probs:
        print("NOT PUBLISHED:\n- " + "\n- ".join(probs))
        sys.exit(1)
    out = Path("notes/published") / src.name
    out.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out.write_text(text.replace("status: DRAFT", f"status: PUBLISHED\npublished_at_utc: {stamp}", 1),
                   encoding="utf-8")
    print(f"Published: {out}")
