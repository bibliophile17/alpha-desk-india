"""Earnings announcement schema, storage, and timestamp -> trading-session alignment.

Day 0 = the first session in which the market can react to the announcement:
  * non-trading day (weekend/holiday)  -> next session, whatever the time
  * before 09:15 IST                   -> same session
  * 09:15 <= t <= 15:30 IST            -> EXCLUDED from the primary study
        (a daily close cannot isolate an intraday reaction)
  * after 15:30 IST                    -> next session
  * time missing on a trading day      -> EXCLUDED (cannot classify; never guessed)
"""
from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from alphadesk.tradingcalendar import CalendarError, TradingCalendar

COLUMNS = [
    "ticker", "company", "sector", "fiscal_quarter", "announce_date",
    "announce_time", "time_source", "revenue", "pat", "eps",
    "prior_revenue", "prior_pat", "prior_eps", "source_url", "retrieved_at",
]
REQUIRED = ["ticker", "fiscal_quarter", "announce_date"]
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)


class AnnouncementSource(Protocol):
    """Any source returns the standard COLUMNS. Swap sources without touching the study."""
    name: str

    def fetch(self, tickers=None, start=None, end=None) -> pd.DataFrame: ...


def load_announcements(path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"announcement file not found: {p}")
    df = pd.read_csv(p, dtype={"announce_time": str, "ticker": str,
                               "fiscal_quarter": str})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"announcement file lacks columns {missing}")
    if len(df) == 0:
        raise ValueError("announcement file has no rows (not a valid empty dataset)")
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = np.nan          # absent stays missing; never 0
    return df[COLUMNS]


class CsvSource:
    """Curated CSV, e.g. results transcribed from exchange filings. Real data only."""
    name = "csv"

    def __init__(self, path):
        self.path = path

    def fetch(self, tickers=None, start=None, end=None):
        df = load_announcements(self.path)
        if tickers is not None:
            df = df[df["ticker"].isin(tickers)]
        d = pd.to_datetime(df["announce_date"])
        if start is not None:
            df = df[d >= pd.Timestamp(start)]
        if end is not None:
            df = df[pd.to_datetime(df["announce_date"]) < pd.Timestamp(end)]
        return df


def parse_time(x):
    if pd.isna(x):
        return None
    s = str(x).strip()
    if s == "" or s.lower() in {"nan", "none", "nat"}:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    raise ValueError(f"unparseable announce_time {x!r}")


def classify(announce_date, announce_time, cal: TradingCalendar):
    """Return (timing_class, day0, eligible_primary, reason)."""
    d = pd.Timestamp(announce_date).normalize()
    if not cal.is_session(d):
        return "non_session_day", cal.next_session_on_or_after(d), True, ""
    t = parse_time(announce_time)
    if t is None:
        return ("unknown_time", pd.NaT, False,
                "announcement time missing on a trading day")
    if t < MARKET_OPEN:
        return "pre_market", d, True, ""
    if t <= MARKET_CLOSE:
        return ("during_market_hours", pd.NaT, False,
                "intraday announcement; daily closes cannot isolate the reaction")
    return "after_market", cal.next_session_after(d), True, ""


def align_events(df: pd.DataFrame, cal: TradingCalendar):
    """Deduplicate and classify. Returns (events, dropped_log). Nothing vanishes silently."""
    df = df.copy()
    bad = df[df[REQUIRED].isna().any(axis=1)]
    if len(bad):
        raise ValueError(f"{len(bad)} rows lack ticker/fiscal_quarter/announce_date")
    df["announce_date"] = pd.to_datetime(df["announce_date"]).dt.normalize()
    df["_t"] = df["announce_time"].fillna("99:99")      # unknown time sorts last
    df = df.sort_values(["ticker", "fiscal_quarter", "announce_date", "_t"],
                        kind="stable")
    dup = df.duplicated(["ticker", "fiscal_quarter"], keep="first")
    dropped = df[dup].drop(columns="_t").assign(
        drop_reason="duplicate_ticker_quarter_kept_earliest")
    kept = df[~dup].drop(columns="_t").copy()

    cls = []
    for r in kept.itertuples(index=False):
        try:
            cls.append(classify(r.announce_date, r.announce_time, cal))
        except CalendarError as exc:
            cls.append(("calendar_out_of_range", pd.NaT, False, str(exc)))
    kept["timing_class"] = [c[0] for c in cls]
    kept["day0"] = pd.to_datetime([c[1] for c in cls])
    kept["eligible_primary"] = [c[2] for c in cls]
    kept["exclusion_reason"] = [c[3] for c in cls]
    return kept.sort_values(["ticker", "announce_date"]).reset_index(drop=True), dropped


def yoy_growth(current, prior):
    """(current - prior) / prior, only when comparable: both present and prior > 0.

    This is an earnings PERFORMANCE PROXY. It is not an earnings surprise,
    which needs analyst consensus.
    """
    c = pd.to_numeric(current, errors="coerce")
    p = pd.to_numeric(prior, errors="coerce")
    ok = c.notna() & p.notna() & (p > 0)
    return ((c - p) / p).where(ok)


def add_performance_proxy(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rev_yoy"] = yoy_growth(df["revenue"], df["prior_revenue"])
    df["pat_yoy"] = yoy_growth(df["pat"], df["prior_pat"])
    return df
